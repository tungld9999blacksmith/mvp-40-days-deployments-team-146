# Observability — Hướng dẫn setup (OTel Collector + Grafana Cloud + LangSmith)

Hướng dẫn dựng hệ thống quan sát cho EV Care: **traces, metrics, logs** của backend và worker đi qua **OpenTelemetry Collector** lên **Grafana Cloud**; trace của LLM/agent đi thẳng lên **LangSmith**.

Cách dùng hằng ngày (tìm trace, viết truy vấn, dashboard, alert): xem [OBSERVABILITY_USAGE.md](OBSERVABILITY_USAGE.md).

## Mục lục

1. [Tổng quan kiến trúc](#1-tổng-quan-kiến-trúc)
2. [Trạng thái triển khai](#2-trạng-thái-triển-khai)
3. [Các quyết định thiết kế](#3-các-quyết-định-thiết-kế)
4. [Bước 1 — Tạo Grafana Cloud stack](#bước-1--tạo-grafana-cloud-stack)
5. [Bước 2 — Lấy thông tin OTLP của Grafana Cloud](#bước-2--lấy-thông-tin-otlp-của-grafana-cloud)
6. [Bước 3 — Tạo tài khoản & Service Key LangSmith](#bước-3--tạo-tài-khoản--service-key-langsmith)
7. [Bước 4 — Biến môi trường](#bước-4--biến-môi-trường)
8. [Bước 5 — Kiểm tra kết nối](#bước-5--kiểm-tra-kết-nối)
9. [Bước 6 — OTel Collector](#bước-6--otel-collector)
10. [Bước 7 — Instrument backend & worker](#bước-7--instrument-backend--worker)
11. [Bước 8 — Deploy lên Railway](#bước-8--deploy-lên-railway)
12. [Bảo mật, PII & chi phí](#bảo-mật-pii--chi-phí)
13. [Xử lý sự cố](#xử-lý-sự-cố)
14. [Reference docs & tutorial](#reference-docs--tutorial)

---

## 1. Tổng quan kiến trúc

```text
                         Railway project (staging) — private network
┌──────────────────────────────────────────────────────────────────────────────┐
│  ┌─────────────────────┐   Celery task (traceparent đi kèm message Redis)    │
│  │ backend (FastAPI)   │──────────────►┌──────────────────┐                  │
│  │ OTel SDK            │               │ worker (Celery)  │                  │
│  └──┬──────────┬───────┘               │ OTel SDK         │                  │
│     │ HTTP + traceparent               └────────┬─────────┘                  │
│     ▼          │                                │                            │
│  ┌─────────────┴───┐                            │                            │
│  │ mock-ev-system  │ (giai đoạn 2)               │                            │
│  └────────┬────────┘                            │                            │
│           │        OTLP/HTTP :4318 (nội bộ, không public)                    │
│           └──────────────┬──────────────────────┘                            │
│                          ▼                                                   │
│        ┌──────────────────────────────────────┐                              │
│        │ otel-collector (contrib)             │  ← chỉ service này giữ token │
│        │ receive → lọc/che → batch → export   │    Grafana                   │
│        └──────────────────┬───────────────────┘                              │
└───────────────────────────┼──────────────────────────────────────────────────┘
                            │ OTLP/HTTPS + Basic auth (instance ID : token)
                            ▼
            Grafana Cloud (stack eagerscone770, ap-southeast-1)
            ├─ Metrics → Prometheus (Mimir) ─┐
            ├─ Traces  → Tempo              ─┼─► Grafana: dashboard, alert,
            └─ Logs    → Loki               ─┘   nhảy trace ↔ log ↔ metric

  backend/worker ──(LLM run, gửi trực tiếp)──► LangSmith (region APAC)
       metadata chứa OTel trace_id ⇄ span chứa LangSmith run id
```

| Tín hiệu | Nguồn | Thu thập bằng | Lưu ở |
|---|---|---|---|
| Traces | HTTP request, DB, Redis, HTTP ra ngoài, Celery task, bước agent chính | OTel auto-instrumentation + span thủ công | Grafana Tempo |
| Metrics | Latency/lỗi theo route, DB, Celery; metric nghiệp vụ (token LLM, guardrail, booking) | OTel instrumentation + OTel Meter | Grafana Prometheus |
| Logs | structlog / stdlib (đã che PII) | OTel `LoggingHandler` → OTLP; stdout vẫn giữ cho Railway | Grafana Loki |
| LLM traces | LangChain / LangGraph (prompt, tool call, token, chi phí) | LangSmith SDK (tự động qua LangChain) | LangSmith |

---

## 2. Trạng thái triển khai

| Hạng mục | Trạng thái |
|---|---|
| Grafana Cloud stack + OTLP token | ✅ Xong |
| LangSmith (APAC) + Service Key dev/staging | ✅ Xong |
| Biến môi trường trong `.env`, `.railway.env`, file mẫu | ✅ Xong |
| Gỡ chỗ ép tắt LangSmith tracing trong `orchestrator.py` | ⏳ Chưa làm |
| Config OTel Collector + service trong docker-compose (profile `observability`) | ✅ Xong |
| Instrument backend & worker | ⏳ Chưa làm |
| Service `otel-collector` trên Railway: script deploy, CI/CD | ✅ Xong (tạo service: [Bước 5c](../deployments/RAILWAY_BACKEND_DEPLOYMENT.MD#bước-5c--tạo-service-otel-collector-observability)) |
| Dashboard & alert | ⏳ Chưa làm |

> Bước 7 mô tả thiết kế đích. Khi code xong, cập nhật bảng trên.

---

## 3. Các quyết định thiết kế

| # | Quyết định | Chọn | Lý do |
|---|---|---|---|
| 1 | App gửi thẳng Grafana hay qua Collector | **Qua Collector** | Token chỉ ở một chỗ; lọc/che tập trung; đổi backend (tự host, AWS) chỉ sửa config |
| 2 | Đường đi của logs | **OTLP từ app**, giữ stdout | Railway không có log drain đơn giản; OTLP log có sẵn `trace_id` |
| 3 | Nguồn `trace_id` | **Span context của OTel**; `CorrelationIdMiddleware` đọc lại | Tránh hai `trace_id` lệch nhau giữa log và trace |
| 4 | Định danh service | `service.name` = `ev-care-backend` / `ev-care-worker` / `mock-ev-system`; `deployment.environment` = `dev` / `staging`; `service.version` = git SHA | Lọc theo môi trường và theo lần deploy |
| 5 | Sampling | **100%**, bỏ `/health` | Traffic MVP nhỏ; free tier 50 GB traces/tháng |
| 6 | Cardinality metric | Label chỉ `http.route` (template), method, status. **Không** `user_id`, `vehicle_id`, URL thô | Free tier giới hạn 10k active series |
| 7 | Bật/tắt | `OTEL_SDK_DISABLED=true` mặc định ở test; app chạy bình thường khi collector chết | Test không phụ thuộc hạ tầng |
| 8 | Mạng Railway | Collector không có domain public; app gửi `http://otel-collector.railway.internal:4318`; collector nghe `[::]` | Private network Railway dùng IPv6 |
| 9 | Grafana Cloud thay vì tự host | Free tier, $0 | Railway free tier không chứa nổi 5 service LGTM (3 service, 0,5 GB RAM mỗi service) |

---

## Bước 1 — Tạo Grafana Cloud stack

1. Vào [grafana.com](https://grafana.com) → **Create free account** (đăng nhập Google/GitHub).
2. Tạo stack:
   - **Stack name**: thành subdomain, vd `eagerscone770` → `https://eagerscone770.grafana.net`.
   - **Region**: chọn gần Railway. Dự án dùng **Singapore (`prod-ap-southeast-1`)**. Không đổi được sau khi tạo.
3. Trang *Getting started* có thể bỏ qua.

Free tier: 10k metric series, 50 GB logs, 50 GB traces, 50 GB profiles, giữ 14 ngày, 3 user.

## Bước 2 — Lấy thông tin OTLP của Grafana Cloud

1. Trong Grafana của stack: **Connections → Add new connection** → tìm **OpenTelemetry (OTLP)**.
2. **Choose your infrastructure** → chọn **Serverless / Others**.
   - *Kubernetes* sinh Helm chart, *Linux* sinh script cài Grafana Alloy lên VM; dự án chạy container nên không dùng.
3. **Create token**: đặt tên `railway-otel-collector`. Token chỉ hiện **một lần**.
4. Wizard hiển thị:
   ```bash
   export OTEL_EXPORTER_OTLP_ENDPOINT="https://otlp-gateway-prod-ap-southeast-1.grafana.net/otlp"
   export OTEL_EXPORTER_OTLP_PROTOCOL="http/protobuf"
   export OTEL_EXPORTER_OTLP_HEADERS="Authorization=Basic <base64(instanceID:token)>"
   ```
   Instance ID = phần trước dấu `:` sau khi giải mã base64 chuỗi `Basic`.

### Instance ID là gì

Grafana Cloud xác thực OTLP bằng **HTTP Basic auth**: `username` = **Instance ID**, `password` = **token** (`glc_...`).

| Thành phần | Vai trò | Bí mật? |
|---|---|---|
| Instance ID (dãy số, vd `123456`) | Định danh *OTLP gateway* của stack — cho Grafana biết dữ liệu thuộc stack nào | Không (giống username) |
| Token `glc_...` | Chứng minh quyền ghi (`metrics:write`, `logs:write`, `traces:write`) | **Có** |

- Mỗi stack có nhiều ID khác nhau (Prometheus, Loki, Tempo, OTLP). Phải dùng **ID của OTLP**; dùng ID của Prometheus/Loki sẽ bị `401`.
- Instance ID **không** nằm trong token: payload của token chứa org ID (`"o":...`), không phải instance ID.
- Collector dùng cặp này trong extension `basicauth` (xem [bước 6](#bước-6--otel-collector)).

**Cách lấy** (chọn một):

1. **Cloud Portal**: [grafana.com](https://grafana.com) → **My Account** → chọn stack → ô **OpenTelemetry** → **Configure** → mục *Instance ID*.
2. **Từ wizard ở trên**: giải mã chuỗi sau `Basic`:
   ```bash
   echo '<chuỗi sau "Basic ">' | base64 -d | cut -d: -f1
   ```
   In ra một dãy số = Instance ID (phần sau `:` là token — đừng in ra màn hình chia sẻ).

## Bước 3 — Tạo tài khoản & Service Key LangSmith

1. Vào [smith.langchain.com](https://smith.langchain.com) → đăng ký, gói **Developer (free)**: 1 seat, 5k trace/tháng, giữ 14 ngày.
2. Xác định region theo URL giao diện, rồi suy ra API endpoint:

   | Giao diện | API endpoint (`LANGCHAIN_ENDPOINT`) |
   |---|---|
   | `smith.langchain.com` | `https://api.smith.langchain.com` |
   | `eu.smith.langchain.com` | `https://eu.api.smith.langchain.com` |
   | `apac.smith.langchain.com` (**dự án dùng**) | `https://apac.api.smith.langchain.com` |

3. **Settings → API Keys → Create API Key** → loại **Service Key** (`lsv2_sk_...`), **một key cho mỗi môi trường**:
   - `evcare-local-dev` → `.env`
   - `evcare-railway-staging` → `.railway.env`

   Không dùng PAT (`lsv2_pt_...`) cho app: PAT gắn với cá nhân, người tạo rời team thì app mất trace.
4. **Workspace ID**: Service Key ở cấp organization nên **bắt buộc** khai báo workspace, nếu không mọi call trả `403`. Lấy ở **Settings → Workspaces** (hoặc URL khi mở workspace).
5. **Project**: chỉ là tên tự đặt (`evcare-dev`, `evcare-staging`), LangSmith tự tạo khi nhận trace đầu tiên.

## Bước 4 — Biến môi trường

Secret gốc của người setup để trong `personal/<tên>/` (đã gitignore). Ba file dùng thật:

| File | Commit? | Vai trò |
|---|---|---|
| `.env` (gốc repo) | Không | Local dev |
| `infrastructure/backend/railway/.railway.env` | Không | Railway staging (Shared Variables) |
| `.env.example`, `infrastructure/backend/railway/.railway.example.env` | Có | Mẫu, giá trị để trống |

**Grafana Cloud** (chỉ OTel Collector dùng):

| Biến | Ví dụ |
|---|---|
| `GRAFANA_CLOUD_OTLP_ENDPOINT` | `https://otlp-gateway-prod-ap-southeast-1.grafana.net/otlp` |
| `GRAFANA_CLOUD_INSTANCE_ID` | `<instance-id>` (dãy số) |
| `GRAFANA_CLOUD_API_TOKEN` | `glc_...` |

**LangSmith** (backend & worker). Code dùng tên `LANGCHAIN_*`; SDK đọc được cả `LANGCHAIN_*` lẫn `LANGSMITH_*`.

| Biến | Local | Staging |
|---|---|---|
| `LANGCHAIN_ENDPOINT` | `https://apac.api.smith.langchain.com` | như local |
| `LANGCHAIN_API_KEY` | Service Key dev | Service Key staging |
| `LANGCHAIN_WORKSPACE_ID` | UUID workspace | như local |
| `LANGCHAIN_PROJECT` | `evcare-dev` | `evcare-staging` |
| `LANGCHAIN_TRACING_V2` | `true` | `true` |

**OpenTelemetry SDK** (backend & worker, thêm ở bước 7):

| Biến | Local | Staging |
|---|---|---|
| `OTEL_SDK_DISABLED` | `false` (`true` khi không chạy collector) | `false` |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `http://localhost:4318` | `http://otel-collector.railway.internal:4318` |
| `OTEL_EXPORTER_OTLP_PROTOCOL` | `http/protobuf` | `http/protobuf` |
| `OTEL_SERVICE_NAME` | `ev-care-backend` / `ev-care-worker` | đặt riêng từng service |
| `OTEL_RESOURCE_ATTRIBUTES` | `deployment.environment=dev` | `deployment.environment=staging` |
| `OTEL_SEMCONV_STABILITY_OPT_IN` | `http` | `http` |

`OTEL_SEMCONV_STABILITY_OPT_IN=http` bật tên metric HTTP ổn định (`http.server.request.duration`, đơn vị giây) thay cho tên cũ.

## Bước 5 — Kiểm tra kết nối

**Grafana Cloud** — gửi một span thử (Git Bash):

```bash
set -a; . personal/<tên>/.grafana.env; set +a
NOW=$(date +%s)000000000
curl -s -o /dev/null -w "%{http_code}\n" \
  -u "$GRAFANA_CLOUD_INSTANCE_ID:$GRAFANA_CLOUD_API_TOKEN" \
  -H "Content-Type: application/json" \
  "$GRAFANA_CLOUD_OTLP_ENDPOINT/v1/traces" \
  -d '{"resourceSpans":[{"resource":{"attributes":[{"key":"service.name","value":{"stringValue":"setup-test"}}]},"scopeSpans":[{"spans":[{"traceId":"5b8efff798038103d269b633813fc60c","spanId":"eee19b7ec3c1b174","name":"hello-grafana","kind":1,"startTimeUnixNano":"'$NOW'","endTimeUnixNano":"'$NOW'"}]}]}]}'
```

`200` = đúng. Xem: Grafana → **Explore** → datasource Tempo → *Search* → Service Name `setup-test`.

**LangSmith** — gửi một run thử:

```bash
cd backend
g() { grep "^$1=" ../.env | cut -d= -f2-; }
LANGSMITH_TRACING=true LANGSMITH_PROJECT=setup-test \
LANGSMITH_ENDPOINT=$(g LANGCHAIN_ENDPOINT) LANGSMITH_API_KEY=$(g LANGCHAIN_API_KEY) \
LANGSMITH_WORKSPACE_ID=$(g LANGCHAIN_WORKSPACE_ID) \
uv run --frozen python -c "
from langsmith import traceable, Client
@traceable(name='hello-langsmith')
def hello(x): return x.upper()
print(hello('ok')); Client().flush()
"
```

Không có lỗi `401/403` = đúng. Xem: LangSmith → **Tracing Projects** → `setup-test`.

## Bước 6 — OTel Collector

| File | Vai trò |
|---|---|
| [config.yaml](../../infrastructure/observability/otel-collector/config.yaml) | Config collector — dùng chung local và Railway, mọi giá trị đọc từ biến môi trường |
| [Dockerfile](../../infrastructure/observability/otel-collector/Dockerfile) | `otel/opentelemetry-collector-contrib:0.161.0` (pin version) + COPY config + `GOMEMLIMIT` |

### 6.1. Pipeline

```text
receivers: otlp (HTTP [::]:4318, gRPC [::]:4317)
    │
    ▼
processors: memory_limiter → filter/health (traces) → attributes/redact (traces, logs)
            → resource/defaults → batch
    │
    ▼
exporters: otlp_http/grafana_cloud (basicauth)  +  debug (log của collector)
extensions: health_check (:13133), basicauth/grafana_cloud
```

| Thành phần | Làm gì |
|---|---|
| `memory_limiter` | Từ chối dữ liệu trước khi container hết RAM (`OTEL_MEMORY_LIMIT_MIB`, mặc định 200) |
| `filter/health` | Bỏ span có `http.route == "/health"` (healthcheck của Railway / docker) |
| `attributes/redact` | Xoá `http.request.header.authorization`, `...cookie`, `http.response.header.set-cookie` |
| `resource/defaults` | Gán `deployment.environment` nếu app chưa gán (`OTEL_DEPLOYMENT_ENVIRONMENT`) |
| `batch` | Gom tối đa 1024 bản ghi / 5 giây mỗi lần gửi |

### 6.2. Biến môi trường của collector

| Biến | Bắt buộc | Mặc định | Ý nghĩa |
|---|---|---|---|
| `GRAFANA_CLOUD_OTLP_ENDPOINT` | ✅ | — | OTLP gateway của stack |
| `GRAFANA_CLOUD_INSTANCE_ID` | ✅ | — | Username Basic auth |
| `GRAFANA_CLOUD_API_TOKEN` | ✅ | — | Password Basic auth |
| `OTEL_DEPLOYMENT_ENVIRONMENT` | | `dev` | `deployment.environment` mặc định (Railway: `staging`, do `vars` đặt) |
| `OTEL_DEBUG_VERBOSITY` | | `basic` | Mức chi tiết của exporter `debug` (6.3) |
| `OTEL_MEMORY_LIMIT_MIB` | | `200` | Ngưỡng cứng của `memory_limiter` |
| `OTEL_COLLECTOR_LOG_LEVEL` | | `info` | Log của chính collector: `debug` / `info` / `warn` / `error` |

### 6.3. Exporter `debug` — các mức

Exporter `debug` in dữ liệu collector nhận được ra **log của collector** (stdout → Railway Logs / `docker logs`). Không gửi đi đâu.

| Mức | In ra | Ví dụ | Dùng khi |
|---|---|---|---|
| `basic` (**mặc định**) | 1 dòng mỗi batch, chỉ số lượng | `Traces {"resource spans": 1, "spans": 6}` | Luôn bật: biết collector có nhận dữ liệu không; vài dòng / 5 giây |
| `normal` | 1 dòng mỗi span / log / metric (tên, ID, thời gian) | `hello-grafana 5b8e… eee1…` | Soi xem span nào đi qua, tạm thời |
| `detailed` | Toàn bộ attribute của từng bản ghi, nhiều dòng | Mọi attribute, body log, resource | **Chỉ local**: log rất lớn, **có thể in PII** (đã redact header nhưng body log / attribute nghiệp vụ vẫn hiện) |

Đổi mức: local `OTEL_DEBUG_VERBOSITY=normal docker compose ... up -d otel-collector`; Railway đặt biến trên service `otel-collector` rồi redeploy. Không đặt `detailed` trên staging.

### 6.4. Chạy ở local

Collector nằm trong profile `observability` của cả [docker-compose.infra.yaml](../../docker-compose.infra.yaml) và [docker-compose.dev.yaml](../../docker-compose.dev.yaml) — chỉ chạy khi bật profile, dev không có token Grafana vẫn chạy stack bình thường.

```bash
# Cần GRAFANA_CLOUD_* trong .env
docker compose -f docker-compose.infra.yaml --profile observability up -d --build otel-collector

curl http://localhost:13133          # {"status":"Server available",...}
docker logs -f p146_otel_collector   # "Everything is ready. Begin running and processing data."
```

App gửi tới: backend chạy ở terminal → `http://localhost:4318`; backend trong `docker-compose.dev.yaml` → `http://otel-collector:4318`.

Image không có shell / curl nên compose không khai báo healthcheck — kiểm tra từ máy host như trên.

### 6.5. Kiểm tra collector bằng `telemetrygen`

[`telemetrygen`](https://github.com/open-telemetry/opentelemetry-collector-contrib/tree/main/cmd/telemetrygen) sinh traces / metrics / logs giả — kiểm tra collector khi app chưa instrument (Git Bash cần `MSYS_NO_PATHCONV=1`):

```bash
IMG=ghcr.io/open-telemetry/opentelemetry-collector-contrib/telemetrygen:v0.161.0
NET=p146-infra_p146_infra_net        # p146-dev_p146_net nếu dùng docker-compose.dev.yaml
for sig in traces metrics logs; do
  docker run --rm --network $NET $IMG $sig --otlp-endpoint otel-collector:4318 \
    --otlp-http --otlp-insecure --service ev-care-setup-test --duration 3s --rate 2
done
docker logs p146_otel_collector 2>&1 | grep -E "Traces|Metrics|Logs|Exporting failed"
```

Đúng khi: log có dòng `Traces` / `Metrics` / `Logs` từ exporter `debug`, **không** có `Exporting failed`; Grafana Explore thấy service `ev-care-setup-test` ở Tempo, Loki, Prometheus.

### 6.6. Validate config

Chạy sau mỗi lần sửa `config.yaml` (CI job `collector-check` chạy đúng lệnh này):

```bash
docker build -t p146-otel-collector:dev infrastructure/observability/otel-collector
MSYS_NO_PATHCONV=1 docker run --rm \
  -e GRAFANA_CLOUD_OTLP_ENDPOINT=https://otlp.example.invalid/otlp \
  -e GRAFANA_CLOUD_INSTANCE_ID=0 -e GRAFANA_CLOUD_API_TOKEN=ci \
  p146-otel-collector:dev validate --config /etc/otelcol-contrib/config.yaml
```

Thoát mã `0` = config hợp lệ.

### 6.7. Nâng version collector

1. Chọn bản ổn định đã phát hành ≥ 2 tuần ([releases](https://github.com/open-telemetry/opentelemetry-collector-releases/releases)).
2. Sửa `ARG OTELCOL_VERSION` trong Dockerfile và tag `telemetrygen` ở 6.5.
3. Validate (6.6), chạy local + telemetrygen (6.4–6.5), xem log không có `deprecated` / `error`.

## Bước 7 — Instrument backend & worker

> ⏳ Thiết kế đích.

- Gói: `opentelemetry-sdk`, `opentelemetry-exporter-otlp-proto-http` và các instrumentation `fastapi`, `sqlalchemy`, `psycopg`, `redis`, `httpx`, `celery`, `logging`.
- Khởi tạo một lần lúc app/worker start (provider cho traces, metrics, logs), tắt hẳn khi `OTEL_SDK_DISABLED=true`.
- Logs: gắn OTel `LoggingHandler` **sau** bước che PII của structlog ([pii.py](../../backend/src/infrastructure/logging/pii.py)); stdout giữ nguyên.
- `trace_id` / `span_id` của OTel được đưa vào context structlog để log và trace khớp nhau.
- LangSmith: bỏ dòng ép `LANGCHAIN_TRACING_V2=false` trong [orchestrator.py](../../backend/src/agents/orchestrator.py); gắn OTel `trace_id` vào metadata của run, và LangSmith run id vào span.
- Metric nghiệp vụ: chỉ label có cardinality thấp (provider, model, kết quả guardrail).

## Bước 8 — Deploy lên Railway

Chi tiết từng bước: [RAILWAY_BACKEND_DEPLOYMENT.MD — Bước 5c](../deployments/RAILWAY_BACKEND_DEPLOYMENT.MD#bước-5c--tạo-service-otel-collector-observability). Tóm tắt:

1. Tạo service **`otel-collector`** trong environment `staging` (`railway add --service otel-collector`). **Không** Generate Domain.
2. Đẩy biến: `./tools/railway-deploy.sh vars` (hoặc `.ps1`). Script đặt `GRAFANA_CLOUD_*` + `OTEL_DEPLOYMENT_ENVIRONMENT` **chỉ** cho `otel-collector`, không cho `backend` / `worker`.
3. Kiểm tra: `./tools/railway-deploy.sh check` — có thêm phần kiểm tra collector.
4. Deploy: `./tools/railway-deploy.sh deploy collector` (hoặc `deploy all`: collector → mock → backend → worker).
5. Log service `otel-collector`: có `Everything is ready`, không có `Exporting failed`.
6. CI/CD (`.github/workflows/ci-cd.yml` của repo deploy, bản mẫu ở [.github/workflows/railway/ci-cd.yml](../../.github/workflows/railway/ci-cd.yml)):
   - Job `collector-check`: build image + `validate` config ở mọi PR / push.
   - Job `deploy-backend`: `railway up` collector **trước** mock / backend / worker.
   - Trigger thêm path `infrastructure/observability/**`.
   - GitHub Environment `staging` có thể thêm variable `RAILWAY_COLLECTOR_SERVICE` (trống → `otel-collector`).
7. Sau khi instrument app (bước 7): đặt `OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector.railway.internal:4318` cho `backend`, `worker`.

---

## Bảo mật, PII & chi phí

- **Secret**: token Grafana chỉ nằm ở service `otel-collector`. Không commit `.env`, `.railway.env`, `personal/`. Lộ key → revoke ngay (Grafana: *Access Policies*; LangSmith: *Settings → API Keys*).
- **PII**: log đã qua `PiiRedactor` trước khi xuất. Collector xoá thêm header `Authorization`, `Cookie`. Prompt gửi LangSmith có thể chứa tên, SĐT, biển số → che theo [mask inputs/outputs](https://docs.langchain.com/langsmith/mask-inputs-outputs).
- **Chi phí**:

  | Dịch vụ | Free tier | Rủi ro vượt |
  |---|---|---|
  | Grafana Cloud | 10k series, 50 GB logs/traces, 14 ngày | Label cardinality cao (user_id, URL thô) |
  | LangSmith | 5k trace/tháng, 14 ngày | Eval/benchmark chạy nhiều → dùng project riêng |
  | Railway | Collector ~50–100 MB RAM | Không đáng kể |

  Theo dõi mức dùng: Grafana → **Administration → Cost management / Usage**; LangSmith → **Settings → Usage**.

## Xử lý sự cố

| Triệu chứng | Nguyên nhân | Cách sửa |
|---|---|---|
| Grafana trả `401` | Sai instance ID / token | Kiểm tra lại `GRAFANA_CLOUD_INSTANCE_ID`, tạo token mới |
| Grafana trả `403` | Token thiếu scope | Token cần `metrics:write`, `logs:write`, `traces:write` |
| LangSmith `403` mọi call | Service Key thiếu workspace | Đặt `LANGCHAIN_WORKSPACE_ID` |
| LangSmith `401/403` dù đúng key | Sai region | Endpoint phải khớp region giao diện (APAC → `apac.api.smith...`) |
| Key LangSmith bắt đầu `llsv2_` | Copy thừa ký tự | Dán lại, key đúng bắt đầu `lsv2_sk_` |
| Agent không có trace LangSmith | Code ép tắt tracing | Xem bước 7 |
| Railway: app không gửi được tới collector | Collector nghe IPv4 / sai hostname | Nghe `[::]`; dùng `otel-collector.railway.internal` |
| Collector log `Exporting failed` | Sai credential / endpoint Grafana | Kiểm tra `GRAFANA_CLOUD_*` trên service collector, chạy lại curl ở bước 5 |
| Collector log `"otlphttp" alias is deprecated` | Config cũ | Exporter tên `otlp_http/...` (đã đổi) |
| `validate` báo `unknown ... level` | `OTEL_DEBUG_VERBOSITY` sai giá trị | Chỉ `basic` / `normal` / `detailed` |
| Git Bash: `unable to read the file file:C:/Program Files/Git/etc/...` | Git Bash đổi đường dẫn `/etc/...` | Thêm `MSYS_NO_PATHCONV=1` trước `docker run` |
| Collector bị Railway restart liên tục | Vượt RAM / `memory_limiter` | Tăng `OTEL_MEMORY_LIMIT_MIB` và `GOMEMLIMIT` (≈80%) cùng lúc |
| Có trace nhưng không có metric | Cardinality vượt giới hạn hoặc chưa đợi đủ chu kỳ export (~60s) | Xem *Usage*; đợi 1–2 phút |

---

## Reference docs & tutorial

**OpenTelemetry**

| Tài liệu | Nội dung |
|---|---|
| [OpenTelemetry docs](https://opentelemetry.io/docs/) | Trang chính |
| [Concepts](https://opentelemetry.io/docs/concepts/) | Traces, metrics, logs, context propagation — đọc đầu tiên |
| [Python — Getting started](https://opentelemetry.io/docs/languages/python/getting-started/) | Tutorial instrument app Python từng bước |
| [Python — Overview](https://opentelemetry.io/docs/languages/python/) | SDK Python: API, exporter, cấu hình |
| [Python zero-code instrumentation](https://opentelemetry.io/docs/zero-code/python/) | Auto-instrumentation không sửa code |
| [opentelemetry-python-contrib](https://opentelemetry-python-contrib.readthedocs.io/en/latest/) | Danh sách instrumentation: FastAPI, SQLAlchemy, Celery, Redis, httpx... |
| [SDK environment variables](https://opentelemetry.io/docs/specs/otel/configuration/sdk-environment-variables/) | Ý nghĩa các biến `OTEL_*` |
| [HTTP metrics semantic conventions](https://opentelemetry.io/docs/specs/semconv/http/http-metrics/) | Tên và label chuẩn của metric HTTP |
| [OpenTelemetry Demo](https://opentelemetry.io/docs/demo/) | Hệ thống mẫu đầy đủ để học |

**OpenTelemetry Collector**

| Tài liệu | Nội dung |
|---|---|
| [Collector overview](https://opentelemetry.io/docs/collector/) | Collector là gì, các mô hình triển khai |
| [Collector configuration](https://opentelemetry.io/docs/collector/configuration/) | receivers, processors, exporters, pipelines |
| [opentelemetry-collector-contrib](https://github.com/open-telemetry/opentelemetry-collector-contrib) | Danh sách component bản contrib (filter, transform, basicauth...) |
| [Collector releases](https://github.com/open-telemetry/opentelemetry-collector-releases/releases) | Danh sách version để nâng cấp |
| [telemetrygen](https://github.com/open-telemetry/opentelemetry-collector-contrib/tree/main/cmd/telemetrygen) | Sinh dữ liệu giả để test collector |

**Grafana Cloud**

| Tài liệu | Nội dung |
|---|---|
| [Grafana Cloud docs](https://grafana.com/docs/grafana-cloud/) | Trang chính |
| [Send data via OTLP](https://grafana.com/docs/grafana-cloud/send-data/otlp/) | Gửi OTel lên Grafana Cloud |
| [Send OTLP data — chi tiết](https://grafana.com/docs/grafana-cloud/send-data/otlp/send-data-otlp/) | Endpoint, auth, cấu hình collector |
| [Cost management & billing](https://grafana.com/docs/grafana-cloud/cost-management-and-billing/) | Theo dõi mức dùng free tier |
| [Grafana tutorials](https://grafana.com/tutorials/) | Tutorial chính thức |

**LangSmith**

| Tài liệu | Nội dung |
|---|---|
| [LangSmith docs](https://docs.langchain.com/langsmith/home) | Trang chính |
| [Create account & API key](https://docs.langchain.com/langsmith/create-account-api-key) | Tạo tài khoản, PAT vs Service Key |
| [Regions FAQ](https://docs.langchain.com/langsmith/regions-faq) | Region US / EU / APAC và endpoint |
| [Observability quickstart](https://docs.langchain.com/langsmith/observability-quickstart) | Tutorial gửi trace đầu tiên |
| [Mask inputs/outputs](https://docs.langchain.com/langsmith/mask-inputs-outputs) | Che PII trước khi gửi |
| [LangChain Academy](https://academy.langchain.com/) | Khoá học miễn phí (LangSmith, LangGraph) |

**Railway & logging**

| Tài liệu | Nội dung |
|---|---|
| [Railway private networking](https://docs.railway.com/guides/private-networking) | `*.railway.internal`, IPv6 |
| [Railway variables](https://docs.railway.com/guides/variables) | Shared / service variables, reference `${{...}}` |
| [Railway Dockerfiles](https://docs.railway.com/guides/dockerfiles) | Build service từ Dockerfile |
| [structlog](https://www.structlog.org/en/stable/) | Thư viện log đang dùng ở backend |
