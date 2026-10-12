# Grafana — Hướng dẫn sử dụng (EV Care)

Cách dùng Grafana Cloud để xem traces, logs, metrics của `ev-care-backend` / `ev-care-worker`, dựng dashboard và chọn visualization cho từng metric.

- Setup hệ thống (collector, biến môi trường, instrument): [OBSERVABILITY_SETUP.md](OBSERVABILITY_SETUP.md)
- Tham chiếu truy vấn, kịch bản điều tra, LangSmith: [OBSERVABILITY_USAGE.md](OBSERVABILITY_USAGE.md)
- Alert gửi Discord: [GRAFANA_ALERTING.md](GRAFANA_ALERTING.md)

> Tên metric / label dưới đây suy ra từ semantic conventions của OpenTelemetry khi vào Grafana Cloud. Chỗ đánh dấu *(kiểm tra)* nên xác nhận một lần bằng **Label browser** / **Metrics browser** (mục 4.4) rồi sửa tài liệu nếu khác.

## Mục lục

1. [Chuẩn bị dữ liệu](#1-chuẩn-bị-dữ-liệu)
2. [Bố cục giao diện](#2-bố-cục-giao-diện)
3. [Drilldown — xem dữ liệu không cần truy vấn](#3-drilldown--xem-dữ-liệu-không-cần-truy-vấn)
4. [Explore — viết truy vấn](#4-explore--viết-truy-vấn)
5. [Đọc một trace](#5-đọc-một-trace)
6. [Chọn visualization cho từng metric](#6-chọn-visualization-cho-từng-metric)
7. [Dựng dashboard "EV Care — API overview"](#7-dựng-dashboard-ev-care--api-overview)
8. [Quy trình điều tra sự cố](#8-quy-trình-điều-tra-sự-cố)
9. [Free tier & cardinality](#9-free-tier--cardinality)
10. [Xử lý sự cố](#10-xử-lý-sự-cố)
11. [Reference docs & tutorial](#reference-docs--tutorial)

---

## 1. Chuẩn bị dữ liệu

Grafana chỉ có dữ liệu khi app đang gửi. Local:

```bash
docker compose -f docker-compose.infra.yaml --profile observability up -d
cd backend
OTEL_ENABLED=true uv run uvicorn src.main:app --reload --port 8000 \
  --loop src.agents.checkpoint:selector_loop_factory
```

Gọi vài API (frontend hoặc Swagger `http://localhost:8000/docs`), có cả request lỗi. Đợi 1–2 phút — metric gửi mỗi 60 giây; traces / logs đến sau vài giây.

Truy cập: `https://eagerscone770.grafana.net` (free tier 3 user — xin owner mời vào stack).

| Service | `service.name` | Môi trường (`deployment.environment`) |
|---|---|---|
| API FastAPI | `ev-care-backend` | `dev` (local), `staging` (Railway) |
| Celery worker | `ev-care-worker` | như trên |

## 2. Bố cục giao diện

| Menu trái | Dùng để |
|---|---|
| **Drilldown** → Metrics / Logs / Traces | Xem dữ liệu bằng click, **không cần truy vấn** — bắt đầu ở đây |
| **Explore** | Viết PromQL / LogQL / TraceQL khi điều tra |
| **Dashboards** | Biểu đồ cố định theo dõi hằng ngày |
| **Alerting** | Alert rule, contact point (Discord) — xem [GRAFANA_ALERTING.md](GRAFANA_ALERTING.md) |
| **Observability → Application** | Trang RED tự dựng theo service từ trace |
| **Administration → Cost management / Usage** | Mức dùng free tier |

Góc trên phải mọi màn hình: **khoảng thời gian** (*Last 15 minutes*…). Không thấy dữ liệu → nới khoảng này trước tiên.

Ba datasource có sẵn (tên đầy đủ theo stack):

| Datasource | Dữ liệu | Ngôn ngữ truy vấn |
|---|---|---|
| `grafanacloud-…-prom` | Metrics | PromQL |
| `grafanacloud-…-logs` | Logs (Loki) | LogQL |
| `grafanacloud-…-traces` | Traces (Tempo) | TraceQL |

## 3. Drilldown — xem dữ liệu không cần truy vấn

| Drilldown | Cách dùng |
|---|---|
| **Traces** | Lọc `service.name = ev-care-backend` → tab **Breakdown** (chia theo `http.route`), **Errors** (chỉ span lỗi), **Duration** (phân bố thời gian) → click một trace để mở |
| **Logs** | Chọn service → biểu đồ số log theo level + danh sách log; click một dòng để xem chi tiết, nút sang trace |
| **Metrics** | Gõ `http_server` → click metric → Grafana tự vẽ và chia theo label |

Phần lớn câu hỏi "có lỗi không, chậm ở đâu" trả lời được ngay ở Drilldown.

## 4. Explore — viết truy vấn

**Explore** → chọn datasource góc trên trái. Nút **Builder / Code**: kéo thả có gợi ý ↔ gõ tay. Nút **Split**: chia đôi màn hình (vd trace trái, log phải cùng khoảng thời gian).

### 4.1. Traces (TraceQL)

```traceql
{ resource.service.name = "ev-care-backend" && span.http.response.status_code >= 500 }
{ resource.service.name = "ev-care-backend" && kind = server && duration > 1s }
{ span.http.route = "/api/v1/user-vehicles" }
{ resource.service.name = "ev-care-worker" }
{ status = error }
```

Có `trace_id` (từ log, header, LangSmith metadata `otel_trace_id`) → dán thẳng vào ô truy vấn.

### 4.2. Logs (LogQL)

Body mỗi dòng log là JSON (structlog, đã che PII); mức độ log nằm sẵn trong metadata `severity_text` / `detected_level`.

```logql
{service_name="ev-care-backend"}
{service_name=~"ev-care-(backend|worker)"} | severity_text=~"ERROR|FATAL"
{service_name="ev-care-worker"} |= "oem.sync_vehicle"
{service_name="ev-care-backend"} | json | trace_id="<trace-id>"
{service_name="ev-care-backend"} | json | line_format "{{.http_method}} {{.http_path}} — {{.event}}"
sum by (detected_level) (count_over_time({service_name="ev-care-backend"} [5m]))
```

- `| json` tách body thành trường (`event`, `http_path`, `trace_id`…).
- Lọc mức độ bằng `severity_text` / `detected_level`, **không** bằng `| json | level=...`: trường `level` trùng tên với metadata nên Loki đổi thành `level_extracted` và điều kiện không khớp.
- Mở một dòng log → cạnh `trace_id` có nút sang Tempo.

### 4.3. Metrics (PromQL)

Tên OTel → Prometheus: `http.server.request.duration` (giây) → `http_server_request_duration_seconds_bucket` / `_count` / `_sum`; `service.name` → label `job` *(kiểm tra)*.

```promql
# Requests per second per route
sum by (http_route) (rate(http_server_request_duration_seconds_count{job="ev-care-backend"}[$__rate_interval]))

# 5xx error ratio
sum(rate(http_server_request_duration_seconds_count{job="ev-care-backend", http_response_status_code=~"5.."}[$__rate_interval]))
/ sum(rate(http_server_request_duration_seconds_count{job="ev-care-backend"}[$__rate_interval]))

# p95 latency (seconds)
histogram_quantile(0.95, sum by (le) (rate(http_server_request_duration_seconds_bucket{job="ev-care-backend"}[$__rate_interval])))
```

### 4.4. Kiểm tra tên metric / label thật

```promql
group by (__name__) ({job=~"ev-care-.*"})
```

Chọn hiển thị **Table** để đọc danh sách metric. Trống → thử `{service_name=~"ev-care-.*"}`. Logs: **Label browser** trong Explore (datasource logs) liệt kê label thật (`service_name`, `deployment_environment`…).

## 5. Đọc một trace

```text
GET /api/v1/user-vehicles          ████████████████████ 480ms   ← span server (cả request)
├─ SELECT user_vehicle ...         ███                   60ms   ← truy vấn DB
├─ GET (redis)                     ▌                      2ms
└─ GET http://localhost:8100/...         ██████████     250ms   ← gọi mock OEM
```

- Thanh dài = tốn thời gian → tìm thanh dài nhất để biết chậm ở đâu.
- Click span → **Attributes**: `http.route`, status, câu SQL, URL gọi ra.
- Span **đỏ** = lỗi; tab **Events** chứa exception.
- **Logs for this span** → log của đúng request đó.
- Task Celery enqueue từ API nằm **chung trace** với request; worker hiện là service `ev-care-worker`.

## 6. Chọn visualization cho từng metric

### 6.1. Nhận diện loại metric qua tên

| Đuôi tên | Loại | Bản chất | Truy vấn đúng |
|---|---|---|---|
| `_total` | Counter | Chỉ tăng, cộng dồn | Luôn `rate(...)` / `increase(...)` — không vẽ giá trị thô |
| `_bucket` / `_count` / `_sum` | Histogram | Phân bố (thời gian, kích thước) | `histogram_quantile` → p95; `rate(_count)` → số lần; `_sum/_count` → trung bình |
| (không đuôi) | Gauge | Giá trị tức thời | Dùng trực tiếp hoặc `avg_over_time` / `max_over_time` |

### 6.2. Chọn kiểu panel

| Muốn thấy | Visualization |
|---|---|
| Xu hướng theo thời gian | **Time series** |
| Một con số KPI | **Stat** |
| Một số so với tối đa | **Gauge** |
| So sánh nhiều route / host | **Bar gauge** |
| Bảng chi tiết | **Table** |
| Phân bố latency theo thời gian | **Heatmap** |
| Log | **Logs** (datasource logs) |

Mẹo: sau khi nhập truy vấn, tab **Suggestions** trong ô chọn visualization tự đề xuất kiểu hợp dữ liệu.

### 6.3. Gợi ý theo metric của dự án

`H` = `http_server_request_duration_seconds` (histogram FastAPI — cho đủ cả 3 chỉ số RED).

| Panel | Truy vấn | Visualization | Cài đặt |
|---|---|---|---|
| Requests/s theo route | `sum by (http_route) (rate(H_count{job="ev-care-backend"}[$__rate_interval]))` | Time series | Unit `rps`; Legend `{{http_route}}`; Stack: Normal |
| Tỉ lệ lỗi 5xx | mục 4.3 | **Stat** | Unit `Percent (0.0-1.0)`; Thresholds xanh / vàng 0.01 / đỏ 0.05; Color mode Background |
| Request theo status | `sum by (http_response_status_code) (rate(H_count{job="ev-care-backend"}[$__rate_interval]))` | Time series (Bars) | Stack Normal; override màu 2xx / 4xx / 5xx |
| p95 / p99 | `histogram_quantile(0.95, sum by (le) (rate(H_bucket{…}[$__rate_interval])))` (+ query 0.99) | Time series | Unit `s`; threshold line 1s |
| Top route chậm | `topk(10, histogram_quantile(0.95, sum by (le, http_route) (rate(H_bucket{…}[$__rate_interval]))))` | **Bar gauge** | Horizontal; Unit `s` |
| Phân bố latency | `sum by (le) (rate(H_bucket{…}[$__rate_interval]))` | **Heatmap** | Query options → Format **Heatmap**; Y unit `s` |
| Tổng request 24h | `sum(increase(H_count{job="ev-care-backend"}[24h]))` | **Stat** | Calculation Last |
| Request đang xử lý | `sum(http_server_active_requests{job="ev-care-backend"})` | Stat (sparkline) | |
| p95 gọi ra ngoài theo host | `histogram_quantile(0.95, sum by (le, server_address) (rate(http_client_request_duration_seconds_bucket[$__rate_interval])))` | Time series | Legend `{{server_address}}`; Unit `s` — phân biệt chậm do mình hay do OEM / LLM |
| Kết nối DB *(kiểm tra tên `db_client…`)* | `sum by (state) (db_client_connections_usage)` | Time series (stack) / Gauge | |
| Log lỗi gần nhất | `{service_name=~"ev-care-(backend\|worker)"} \| severity_text=~"ERROR\|FATAL"` | **Logs** (datasource **logs**) | Time on; Enable log details; Newest first; Max lines 100 |

### 6.4. Cài đặt chung cho mọi panel

- `$__rate_interval` thay cho `[5m]` cố định: tự khớp zoom và chu kỳ gửi 60 giây.
- Luôn đặt **Unit** (*Standard options → Unit*).
- **Legend**: *Custom* `{{http_route}}`; chế độ Table + Mean / Max để so sánh.
- **Thresholds** ngay trên panel — tạo alert từ panel sau này dùng lại được.
- Panel logs phải đổi **Data source** sang `…-logs`; LogQL chạy trên datasource prom sẽ lỗi.

## 7. Dựng dashboard "EV Care — API overview"

```text
┌────────────┬────────────┬────────────┬────────────┐
│ Stat:      │ Stat:      │ Stat:      │ Stat:      │   ← hàng KPI
│ Req 24h    │ % lỗi 5xx  │ p95 now    │ Active req │
├────────────┴────────────┴────────────┴────────────┤
│ Time series: Requests/s theo route (stack)        │
├─────────────────────────┬─────────────────────────┤
│ Time series: p95 / p99  │ Bars: theo status code  │
├─────────────────────────┼─────────────────────────┤
│ Bar gauge: top route    │ Time series: p95 gọi    │
│ chậm nhất               │ ra ngoài theo host      │
├─────────────────────────┴─────────────────────────┤
│ Heatmap: phân bố latency                          │
├───────────────────────────────────────────────────┤
│ Logs: lỗi gần nhất (datasource logs)              │
└───────────────────────────────────────────────────┘
```

1. **Dashboards → New → New dashboard → Add visualization** → chọn datasource **prom**.
2. Mỗi panel: dán truy vấn mục 6.3 → chọn visualization → đặt Unit / Legend / Thresholds → **Back to dashboard**.
3. Kéo góc panel để chỉnh kích thước theo bố cục trên. Thêm **Row** để nhóm panel (vd "API", "Worker").
4. **Biến môi trường**: *Settings → Variables → New* → tên `env`, kiểu *Custom*, giá trị `dev,staging` → dùng `$env` trong truy vấn (label môi trường *(kiểm tra)*: một số resource attribute chỉ nằm trong `target_info`).
5. **Save** → tên `EV Care — API overview`, folder `EV Care`.
6. Khi ổn định: *Share → Export → JSON* → lưu vào repo để không mất khi đổi stack.

## 8. Quy trình điều tra sự cố

**"App chậm / lỗi"**

1. Dashboard: lỗi / latency tăng từ lúc nào (trùng lần deploy?).
2. Drilldown Traces: lọc route → tab Errors hoặc sort duration → mở trace.
3. Trong trace: span dài nhất / span đỏ (DB, OEM, LLM?) → **Logs for this span**.
4. Chậm do agent / LLM: copy `trace_id` → LangSmith filter *Metadata* `otel_trace_id`.

**Người dùng gửi `X-Request-ID`** (có ở header mọi response):

```logql
{service_name="ev-care-backend"} |= "<request-id>"
```

→ mở dòng log → nút sang trace.

## 9. Free tier & cardinality

| Giới hạn | Free tier |
|---|---|
| Metrics | 10k active series |
| Logs / Traces | 50 GB / tháng mỗi loại |
| Retention | 14 ngày |
| User | 3 |

- Theo dõi: **Administration → Cost management / Usage**.
- **Không** thêm label `user_id`, `vehicle_id`, email, URL thô vào metric — mỗi giá trị là một series mới. Cần theo user → dùng trace / log.

## 10. Xử lý sự cố

| Hiện tượng | Cách sửa |
|---|---|
| Không thấy dữ liệu | Nới khoảng thời gian; kiểm tra backend chạy `OTEL_ENABLED=true` và collector (`docker logs p146_otel_collector`) |
| Có trace nhưng chưa có metric | Đợi ≥ 60 giây (chu kỳ gửi metric) |
| Panel báo lỗi parse | Sai datasource (LogQL trên prom hoặc ngược lại) |
| Panel trống dù có dữ liệu | Sai tên metric / label → mục 4.4 |
| `\| json \| level="error"` không ra gì | Dùng `severity_text=~"ERROR\|FATAL"` (mục 4.2) |
| Biểu đồ răng cưa / trống ở zoom nhỏ | Dùng `$__rate_interval` thay cho khoảng cố định |

---

## Reference docs & tutorial

**Giao diện & truy vấn**

| Tài liệu | Nội dung |
|---|---|
| [Grafana Drilldown (simplified exploration)](https://grafana.com/docs/grafana/latest/explore/simplified-exploration/) | Tổng quan Drilldown |
| [Metrics Drilldown](https://grafana.com/docs/grafana/latest/explore/simplified-exploration/metrics/) · [Logs Drilldown](https://grafana.com/docs/grafana/latest/explore/simplified-exploration/logs/) · [Traces Drilldown](https://grafana.com/docs/grafana/latest/explore/simplified-exploration/traces/) | Từng loại Drilldown |
| [Explore](https://grafana.com/docs/grafana/latest/explore/) | Màn hình Explore, split view |
| [PromQL basics](https://prometheus.io/docs/prometheus/latest/querying/basics/) · [PromQL functions](https://prometheus.io/docs/prometheus/latest/querying/functions/) | `rate`, `increase`, `histogram_quantile`… |
| [Histograms & summaries](https://prometheus.io/docs/practices/histograms/) | Cách tính percentile từ histogram |
| [LogQL](https://grafana.com/docs/loki/latest/query/) | Truy vấn log |
| [Loki — OpenTelemetry](https://grafana.com/docs/loki/latest/send-data/otel/) | Label / structured metadata khi log đến qua OTLP |
| [TraceQL](https://grafana.com/docs/tempo/latest/traceql/) | Truy vấn trace |

**Dashboard & visualization**

| Tài liệu | Nội dung |
|---|---|
| [Dashboards](https://grafana.com/docs/grafana/latest/dashboards/) | Tạo, tổ chức dashboard |
| [Visualizations](https://grafana.com/docs/grafana/latest/panels-visualizations/visualizations/) | Danh sách kiểu panel |
| [Time series](https://grafana.com/docs/grafana/latest/panels-visualizations/visualizations/time-series/) · [Stat](https://grafana.com/docs/grafana/latest/panels-visualizations/visualizations/stat/) · [Bar gauge](https://grafana.com/docs/grafana/latest/panels-visualizations/visualizations/bar-gauge/) · [Heatmap](https://grafana.com/docs/grafana/latest/panels-visualizations/visualizations/heatmap/) · [Logs](https://grafana.com/docs/grafana/latest/panels-visualizations/visualizations/logs/) | Cài đặt từng kiểu panel |
| [Query & transform data](https://grafana.com/docs/grafana/latest/panels-visualizations/query-transform-data/) | Query options, transformations |
| [Variables](https://grafana.com/docs/grafana/latest/dashboards/variables/) | Biến dashboard (`$env`) |

**Học thêm**

| Tài liệu | Nội dung |
|---|---|
| [Grafana tutorials](https://grafana.com/tutorials/) | Tutorial chính thức |
| [Grafana Play](https://play.grafana.org/) | Grafana demo có dữ liệu thật để tập |
| [Application Observability](https://grafana.com/docs/grafana-cloud/monitor-applications/application-observability/) | Trang RED tự động theo service |
| [Grafana Cloud cost management](https://grafana.com/docs/grafana-cloud/cost-management-and-billing/) | Theo dõi mức dùng free tier |
