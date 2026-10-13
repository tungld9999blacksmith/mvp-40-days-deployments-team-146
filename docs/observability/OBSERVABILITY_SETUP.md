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
    - [Bước 7b — Telemetry của AI agent (Grafana + LangSmith)](#bước-7b--telemetry-của-ai-agent-grafana--langsmith)
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
| Metrics | Latency/lỗi theo route, DB, Celery; agent: tool, guardrail, RAG, độ trễ / token / chi phí LLM ([AGENT_COST_LATENCY.md](AGENT_COST_LATENCY.md)) | OTel instrumentation + OTel Meter | Grafana Prometheus |
| Logs | structlog / stdlib (đã che PII) | OTel `LoggingHandler` → OTLP; stdout vẫn giữ cho Railway | Grafana Loki |
| LLM / agent traces | Mỗi lượt chat = 1 trace: guard, LangGraph, LLM (prompt, token, chi phí), tool, RAG | LangSmith SDK + `step()` ([Bước 7b](#bước-7b--telemetry-của-ai-agent-grafana--langsmith)) | LangSmith |

---

## 2. Trạng thái triển khai

| Hạng mục | Trạng thái |
|---|---|
| Grafana Cloud stack + OTLP token | ✅ Xong |
| LangSmith (APAC) + Service Key dev/staging | ✅ Xong |
| Biến môi trường trong `.env`, `.railway.env`, file mẫu | ✅ Xong |
| Gỡ chỗ ép tắt LangSmith tracing; cấu hình LangSmith từ `Settings` | ✅ Xong |
| Config OTel Collector + service trong docker-compose (profile `observability`) | ✅ Xong |
| Instrument backend & worker (traces, metrics, logs) — chạy thử local | ✅ Xong |
| Service `otel-collector` trên Railway: script deploy, CI/CD | ✅ Xong (tạo service: [Bước 5c](../deployments/RAILWAY_BACKEND_DEPLOYMENT.MD#bước-5c--tạo-service-otel-collector-observability)) |
| Telemetry AI agent: trace + metric LangSmith, bộ ba traces / metrics / logs Grafana — chạy thử local | ✅ Xong ([Bước 7b](#bước-7b--telemetry-của-ai-agent-grafana--langsmith)) |
| Dashboard & alert | ⏳ Chưa làm |

> Chưa làm: metric nghiệp vụ (booking, onboarding, OEM, thông báo), instrument `mock-ev-system`, dashboard / alert, bật trên Railway (`OTEL_ENABLED=true` sau khi deploy collector).

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
| 10 | Chia vai agent | **LangSmith** (luôn bật): trace đầy đủ nội dung + token, chi phí, độ trễ LLM, tỉ lệ lỗi agent. **Grafana** (bật bằng `OTEL_AGENT_ENABLED`, mặc định tắt): span mỏng (không nội dung), metric tool / guardrail / RAG, độ trễ / token / chi phí (chỉ con số), log, alert Discord | LangSmith không gửi alert Discord có nội dung; Grafana không được chứa prompt (PII) |
| 11 | Quota LangSmith | Run của Celery worker sang project `<project>-jobs` | Project chat chỉ đếm lượt chat thật |
| 12 | PII trên LangSmith | `LANGCHAIN_REDACT_PII=true` ở staging, `false` ở local | Staging có dữ liệu thật; local cần thấy nguyên văn để debug |

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
| `LANGCHAIN_JOBS_PROJECT` | `evcare-dev-jobs` | `evcare-staging-jobs` (trống → `<LANGCHAIN_PROJECT>-jobs`) |
| `LANGCHAIN_REDACT_PII` | `false` | `true` — che email / SĐT trong mọi input / output gửi LangSmith |
| `LANGCHAIN_TRACING_V2` | `true` | `true` |

**OpenTelemetry — phía app** (backend & worker, đọc qua `Settings` trong [config.py](../../backend/src/config.py), nên đặt trong `.env` là đủ):

| Biến | Local (`.env`) | Compose `dev` | Railway (`.railway.env`) |
|---|---|---|---|
| `OTEL_ENABLED` | `false` (mặc định) — `true` khi chạy collector | theo `.env` | `false` cho tới khi deploy collector, rồi `true` |
| `OTEL_AGENT_ENABLED` | `false` (mặc định) — bật span / metric / log của AI agent trên Grafana (cần `OTEL_ENABLED=true`); không ảnh hưởng LangSmith | theo `.env` | `true` ở `backend` và `worker` khi muốn xem độ trễ / chi phí agent |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `http://localhost:4318` | `http://otel-collector:4318` (compose đè) | `http://otel-collector.railway.internal:4318` |
| `OTEL_DEPLOYMENT_ENVIRONMENT` | `dev` | `dev` | `staging` |
| `OTEL_METRIC_EXPORT_INTERVAL_MS` | `60000` (mặc định) | | |

- Tên service đặt trong code: `ev-care-backend` (API), `ev-care-worker` (Celery). `service.version` = 12 ký tự đầu của `RAILWAY_GIT_COMMIT_SHA` (local: `dev`).
- `APP_ENV=test` luôn tắt OTel (và LangSmith), bất kể `.env`.
- Code tự đặt `OTEL_SEMCONV_STABILITY_OPT_IN=http`: tên metric HTTP ổn định (`http.server.request.duration`, đơn vị giây).

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

### 7.1. Code

| File | Vai trò |
|---|---|
| [observability/telemetry.py](../../backend/src/infrastructure/observability/telemetry.py) | `setup_telemetry(service)`: TracerProvider + MeterProvider + LoggerProvider → OTLP/HTTP; instrument `httpx`, `requests`, `redis`, `celery`, `sqlalchemy` (engine có sẵn). `instrument_fastapi(app)`, `shutdown_telemetry()` |
| [observability/log_handler.py](../../backend/src/infrastructure/observability/log_handler.py) | Handler OTLP: body = dòng JSON **đã che PII**; attribute chỉ giữ vị trí code + `exception.type` (bỏ extras / message exception thô) |
| [observability/context.py](../../backend/src/infrastructure/observability/context.py) | `current_trace_ids()` — `trace_id` / `span_id` của span đang chạy |
| [observability/langsmith.py](../../backend/src/infrastructure/observability/langsmith.py) | `configure_langsmith(settings)` — chép `LANGCHAIN_*` từ `Settings` vào `os.environ` (cả tiền tố `LANGSMITH_*`) |
| [logging/config.py](../../backend/src/infrastructure/logging/config.py) | Processor `add_otel_trace_context` (gắn `trace_id`/`span_id` vào mọi dòng log); tham số `otel_logger_provider` thêm handler OTLP |
| [correlation_id.py](../../backend/src/infrastructure/fastapi/middlewares/correlation_id.py) | `trace_id` của request = trace OTel (khi bật) |
| [main.py](../../backend/src/main.py) | `configure_langsmith` → `setup_telemetry("ev-care-backend")` → `configure_logging(otel_logger_provider=...)` → `instrument_fastapi`; flush khi tắt |
| [celery_tasks.py](../../backend/src/celery_tasks.py) | Log worker **luôn JSON** (file `logs/worker.*`); telemetry `ev-care-worker` khởi tạo sau fork (prefork) hoặc ở `worker_init` (solo / threads) |
| [orchestrator.py](../../backend/src/agents/orchestrator.py) | Bỏ dòng ép tắt LangSmith; run có metadata `otel_trace_id`, `conversation_id` |

Thư viện (pin cùng một dòng phát hành — SDK `1.45.0` ↔ instrumentation `0.66b0`, nâng cùng lúc): `opentelemetry-api`, `-sdk`, `-exporter-otlp-proto-http`, `-instrumentation-fastapi`, `-sqlalchemy`, `-redis`, `-httpx`, `-celery`, `-requests`, `-logging`. Có trong cả `pyproject.toml` / `uv.lock` (Docker) và `requirements.txt` (CI).

### 7.2. Được gì

| Tín hiệu | Nội dung |
|---|---|
| Traces | Span server cho mọi request (trừ `/health`, `/api/v1/health/*`), span con cho SQL, Redis, HTTP ra ngoài (OEM, LLM, Firebase), Celery publish → run. `traceparent` đến từ ngoài được nối tiếp |
| Metrics | `http.server.request.duration` (histogram, theo `http.route`, method, status), `http.client.*`, `db.client.*` của SQLAlchemy… — xuất mỗi 60 giây |
| Logs | Mọi dòng log (structlog + stdlib, uvicorn, celery) — body JSON đã che PII, kèm `trace_id` / `span_id` |
| LangSmith | Run của agent có metadata `otel_trace_id` → dán vào Tempo để xem cả request |

### 7.3. Chạy thử ở local

```bash
# 1. Hạ tầng + collector
docker compose -f docker-compose.infra.yaml --profile observability up -d

# 2. Backend (terminal) — bật OTel cho phiên này, hoặc đặt OTEL_ENABLED=true trong .env
cd backend
OTEL_ENABLED=true uv run uvicorn src.main:app --reload --port 8000 \
  --loop src.agents.checkpoint:selector_loop_factory     # Windows: psycopg async cần SelectorEventLoop

# 3. Worker (terminal khác). Windows: -B không chạy được, chạy beat riêng nếu cần
OTEL_ENABLED=true uv run celery -A src.celery_tasks worker --loglevel=info --pool=solo
```

Kiểm tra:

1. Log backend có `OpenTelemetry enabled: exporting to http://localhost:4318 (dev)`.
2. Gọi vài API → `docker logs p146_otel_collector` có dòng `Traces` / `Logs` (ngay) và `Metrics` (sau ≤ 60 giây), không có `Exporting failed`.
3. Dòng log backend / worker có `trace_id`, `span_id`; header `X-Request-ID` vẫn trả về như cũ.
4. Grafana → Explore → Tempo: service `ev-care-backend`, `ev-care-worker`; Loki: `{service_name="ev-care-backend"}`.

> Windows + Git Bash: thêm `PYTHONIOENCODING=utf-8` nếu chuyển stdout vào file (log tiếng Việt lỗi `cp1252`).

### 7.4. Test

[test_observability.py](../../backend/tests/test_infrastructure/test_observability.py) dùng exporter in-memory, không cần collector: span server có `http.route`, `/health` không bị trace, log / middleware / span cùng `trace_id`, `traceparent` được nối tiếp, log OTLP đã che PII, bật / tắt LangSmith, worker log JSON, regression "import orchestrator không ép tắt tracing".

`tests/conftest.py` tắt LangSmith cho toàn bộ test (các module gọi `load_dotenv()` lúc import sẽ chép `LANGCHAIN_TRACING_V2=true` từ `.env`).

## Bước 7b — Telemetry của AI agent (Grafana + LangSmith)

Một điểm đo, hai nơi nhận ([tracing.py](../../backend/src/infrastructure/observability/tracing.py) — `step()`):

| | LangSmith | Grafana |
|---|---|---|
| Trace | Cây đầy đủ **có nội dung**: prompt, câu trả lời, tham số tool, tài liệu RAG | Span **mỏng**: tên, thời gian, trạng thái, attribute ít giá trị — **không** nội dung |
| Metric | Token, chi phí, độ trễ LLM, tỉ lệ lỗi agent (tab *Monitor*, tự tính từ run) | Tool, guardrail, RAG (bảng 7b.3) |
| Log | — | Dòng `Agent turn finished` mỗi lượt, kèm `trace_id` |
| Alert | — | Discord (Grafana Alerting) |
| Liên kết | metadata `otel_trace_id` | attribute `langsmith.run_id`, `langsmith.trace_id` |

### 7b.1. Cây trace của một lượt chat

```text
GRAFANA (Tempo)                                        LANGSMITH (project evcare-<env>)
POST /api/v1/conversations/{id}/messages   (auto)
└─ agent.turn  agent.outcome, agent.tools, ──────────  agent.turn  (root, 1 trace / lượt chat)
   │           langsmith.run_id                         │  metadata: thread_id, otel_trace_id, outcome
   ├─ agent.guard.input  guard.decision,                ├─ agent.guard.input   (message → report)
   │                     guard.pii_types                └─ LangGraph
   ├─ chat <model>  gen_ai.request.model, agent.node       ├─ ChatOpenRouter  [llm] prompt, token, chi phí
   │   POST openrouter.ai/...  (httpx auto)                 ├─ agent.guard.tool_calls
   ├─ agent.guard.tool_calls  guard.decision               ├─ <tool>  [tool] tham số, kết quả
   ├─ execute_tool <tool>  tool.status                      │   └─ rag.query → rag.retrieve / rag.rerank [retriever]
   │   ├─ SELECT ... (auto)                                 │                   chat <model> [llm] (rewrite / generate)
   │   └─ rag.query  rag.outcome, rag.cache                 └─ ChatOpenRouter  [llm]
   │       ├─ rag.retrieve  rag.hits
   │       ├─ rag.rerank    rag.hits
   │       └─ chat <model>  (rewrite / generate)
   └─ ...
```

### 7b.2. Code

| File | Vai trò |
|---|---|
| [observability/tracing.py](../../backend/src/infrastructure/observability/tracing.py) | `step(name, run_type, attributes, inputs, metadata, langsmith_run)` — span OTel + run LangSmith, tự liên kết hai chiều. `use_tracer_provider()` cho test |
| [observability/metrics.py](../../backend/src/infrastructure/observability/metrics.py) | Metric agent cho Grafana (`get_agent_metrics()`); `use_meter_provider()` cho test |
| [observability/agent_hooks.py](../../backend/src/infrastructure/observability/agent_hooks.py) | `agent_callbacks()` — callback LangChain tạo span `chat <model>` (model, node, số token) + metric độ trễ / token / chi phí ([llm_usage.py](../../backend/src/infrastructure/observability/llm_usage.py), giá ở [model_prices.json](../../backend/src/infrastructure/observability/model_prices.json)); chỉ chạy khi `OTEL_AGENT_ENABLED=true`; `instrument_tools()` — bọc thân tool: span `execute_tool <name>` + metric |
| [observability/langsmith.py](../../backend/src/infrastructure/observability/langsmith.py) | Client LangSmith dùng chung (+ anonymizer khi `LANGCHAIN_REDACT_PII`); `jobs_project()` |
| [llm/traced.py](../../backend/src/infrastructure/llm/traced.py) | `TracedLLMProvider` — LLM gọi ngoài LangChain (RAG rewrite / generate, review booking, follow-up): run `llm` có token trên LangSmith, span mỏng trên Grafana. Gắn trong [llm/dependency.py](../../backend/src/infrastructure/llm/dependency.py) |
| [agents/telemetry.py](../../backend/src/agents/telemetry.py) | `TurnRecorder` (outcome, tool, log tổng kết), ghi nhận guard input / tool-call |
| [agents/orchestrator.py](../../backend/src/agents/orchestrator.py) | `run_agent_turn` = root `agent.turn` bọc `_run_turn`; `agent.guard.input`; callback trong `_run_config` |
| [agents/graph.py](../../backend/src/agents/graph.py) | `instrument_tools(bound_tools)`; `agent.guard.tool_calls`; `stream_usage=True` (token của lượt chat stream) |
| [RAG/query/rag_pipeline.py](../../backend/src/agents/tools/RAG/query/rag_pipeline.py) | `rag.query` (outcome, cache), `rag.retrieve`, `rag.rerank` (run `retriever` hiện danh sách tài liệu) |
| [celery_tasks.py](../../backend/src/celery_tasks.py) | Worker trace vào project `-jobs` (đặt ở `worker_init` / `worker_process_init`, không ảnh hưởng process API) |

`agent.turn.outcome`: `answered` · `fallback` (RAG / agent trả `fallback_required`) · `error` (exception trong graph — người dùng vẫn nhận câu xin lỗi) · `cancelled` (client ngắt).

### 7b.3. Metric agent trên Grafana

| Metric | Loại | Label | Ý nghĩa |
|---|---|---|---|
| `evcare.agent.tool.calls` | Counter | `gen_ai.tool.name`, `tool.status` (`ok` / `empty` / `error` / `exception`) | Tool nào hay lỗi |
| `evcare.agent.guardrail.decisions` | Counter | `guard.stage` (`input` / `tool_calls`), `guard.decision` (`pass` / `flag` / `modify`), `guard.reason` (`injection` / `pii` / `tool_call_rewrite` / `none`) | Guardrail chặn / sửa bao nhiêu |
| `evcare.rag.queries` | Counter | `rag.outcome` (`answered` / `fallback` / `empty` / `out_of_scope` / `error`), `rag.cache` (`hit` / `miss`) | Tỉ lệ RAG không tìm thấy tài liệu |
| `evcare.rag.stage.duration` | Histogram (s) | `rag.stage` (`retrieve` / `rerank`) | Độ trễ phần không phải LLM của RAG |
| `evcare.agent.turn.duration`, `evcare.agent.turn.cost.usd`, `evcare.llm.call.duration`, `evcare.llm.tokens`, `evcare.llm.cost.usd`, `evcare.llm.unpriced.calls`, `evcare.agent.tool.duration` | Histogram / Counter | model, node, tool, outcome | Độ trễ, token, chi phí — xem [AGENT_COST_LATENCY.md](AGENT_COST_LATENCY.md) |

Trên Prometheus, dấu `.` thành `_` và counter có hậu tố `_total`, vd `evcare_agent_tool_calls_total`. Toàn bộ phần Grafana của agent (span, metric, dòng log tổng kết lượt chat) chỉ chạy khi `OTEL_AGENT_ENABLED=true` (mặc định `false`); LangSmith không phụ thuộc biến này. Token và chi phí trên Grafana chỉ là con số — nội dung prompt vẫn chỉ ở LangSmith *Monitor*.

### 7b.4. LangSmith — xem gì, cấu hình gì

- **Threads**: metadata `thread_id = conversation_id` → gom các lượt của một cuộc hội thoại.
- **Monitor** (trong project): số trace, tỉ lệ lỗi, p50 / p99 latency, token, chi phí theo thời gian.
- **Chi phí**: LangSmith tính từ token × bảng giá model. Model OpenRouter (vd `google/gemini-2.5-flash`) có thể chưa có giá → *Settings → Model pricing* → thêm model + giá / 1M token.
- **Project**: `evcare-<env>` chỉ có lượt chat; `evcare-<env>-jobs` cho Celery (summary, follow-up...).
- **Anonymizer** (`LANGCHAIN_REDACT_PII=true`): email / SĐT trong mọi chuỗi thành `***` trước khi gửi (cùng luật với log). Biển số, tên **không** bị che.

### 7b.5. Chạy thử ở local

Bật collector + `OTEL_ENABLED=true` như 7.3, LangSmith bật trong `.env`. Gửi một tin nhắn chat, rồi:

1. LangSmith → project `evcare-dev` → trace `agent.turn` mới: có `agent.guard.input`, LangGraph, model, tool; metadata `otel_trace_id`.
2. Grafana → Explore → Tempo → TraceQL `{ trace:id = "<otel_trace_id>" }` (hoặc `{ name = "agent.turn" }`): span `agent.turn` có `agent.outcome`, `langsmith.run_id`.
3. Prometheus: `sum by (gen_ai_tool_name, tool_status) (evcare_agent_tool_calls_total)` sau ≤ 60 giây.
4. Loki: `{service_name="ev-care-backend"} |= "Agent turn finished"`.

### 7b.6. Test

[test_agent_observability.py](../../backend/tests/test_infrastructure/test_agent_observability.py) — exporter OTel in-memory + client LangSmith giả (không gọi mạng): `step` liên kết span ↔ run, lỗi đánh dấu hai phía, một lượt chat = một trace LangSmith (guard + graph nằm dưới root), lượt lỗi → `outcome=error`, span tool / metric / trạng thái, guard tool-call, span `chat <model>`, `TracedLLMProvider` (token chỉ ở LangSmith), RAG (cache, outcome, stage), anonymizer, project `-jobs`, regression `stream_usage`. Mọi test kiểm tra **không có email / biển số trong attribute span**.

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
7. Bật app: trong `.railway.env` đặt `OTEL_ENABLED=true` (endpoint `http://otel-collector.railway.internal:4318` đã có sẵn) → `vars` → `deploy`.

---

## Bảo mật, PII & chi phí

- **Secret**: token Grafana chỉ nằm ở service `otel-collector`. Không commit `.env`, `.railway.env`, `personal/`. Lộ key → revoke ngay (Grafana: *Access Policies*; LangSmith: *Settings → API Keys*).
- **PII**: log đã qua `PiiRedactor` trước khi xuất. Collector xoá thêm header `Authorization`, `Cookie`. Span agent trên Grafana **không** chứa nội dung (có test). Prompt gửi LangSmith: staging bật `LANGCHAIN_REDACT_PII` (email / SĐT bị che — [mask inputs/outputs](https://docs.langchain.com/langsmith/mask-inputs-outputs)); tên, biển số vẫn còn.
- **Chi phí**:

  | Dịch vụ | Free tier | Rủi ro vượt |
  |---|---|---|
  | Grafana Cloud | 10k series, 50 GB logs/traces, 14 ngày | Label cardinality cao (user_id, URL thô) |
  | LangSmith | 5k trace/tháng, 14 ngày (1 lượt chat = 1 trace) | Job Celery / eval → project `-jobs` / project riêng |
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
| Agent không có trace LangSmith | `LANGCHAIN_TRACING_V2` / `LANGCHAIN_API_KEY` trống, hoặc `APP_ENV=test` | Kiểm tra `.env`; LangSmith luôn tắt khi chạy test |
| Backend không gửi gì tới collector | `OTEL_ENABLED` vẫn `false` | Đặt `true` (`.env` hoặc biến môi trường), khởi động lại |
| Backend log `Exporting failed` / `Connection refused :4318` | Collector chưa chạy | `docker compose ... --profile observability up -d otel-collector`, hoặc tắt `OTEL_ENABLED` |
| Windows: backend khởi động lỗi `PoolTimeout` / `ProactorEventLoop` | psycopg async không chạy trên ProactorEventLoop | Thêm `--loop src.agents.checkpoint:selector_loop_factory` cho uvicorn |
| Windows: `-B option does not work on Windows` | Celery không cho chạy beat kèm worker trên Windows | Bỏ `-B`, chạy `celery -A src.celery_tasks beat` ở terminal riêng nếu cần |
| Railway: app không gửi được tới collector | Collector nghe IPv4 / sai hostname | Nghe `[::]`; dùng `otel-collector.railway.internal` |
| Collector log `Exporting failed` | Sai credential / endpoint Grafana | Kiểm tra `GRAFANA_CLOUD_*` trên service collector, chạy lại curl ở bước 5 |
| Collector log `"otlphttp" alias is deprecated` | Config cũ | Exporter tên `otlp_http/...` (đã đổi) |
| `validate` báo `unknown ... level` | `OTEL_DEBUG_VERBOSITY` sai giá trị | Chỉ `basic` / `normal` / `detailed` |
| Git Bash: `unable to read the file file:C:/Program Files/Git/etc/...` | Git Bash đổi đường dẫn `/etc/...` | Thêm `MSYS_NO_PATHCONV=1` trước `docker run` |
| Collector bị Railway restart liên tục | Vượt RAM / `memory_limiter` | Tăng `OTEL_MEMORY_LIMIT_MIB` và `GOMEMLIMIT` (≈80%) cùng lúc |
| LangSmith: các bước của một lượt chat thành nhiều trace rời | Gọi graph ngoài `run_agent_turn` (script, eval) | Bình thường — chỉ `run_agent_turn` tạo root `agent.turn` |
| LangSmith: lượt chat không có token / chi phí | Model stream không trả usage, hoặc chưa có giá model | `stream_usage=True` (đã bật cho OpenRouter / OpenAI); thêm giá ở *Settings → Model pricing* |
| Log `Failed to detach context` khi lượt chat bị bỏ dở | Generator `run_agent_turn` bị đóng trong context khác (GC) | Luôn tiêu thụ bằng `async with aclosing(...)` như `ConversationService` |
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
