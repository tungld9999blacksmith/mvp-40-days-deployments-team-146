# Observability — Hướng dẫn sử dụng (Grafana Cloud + LangSmith)

Cách dùng hằng ngày: tìm trace của một request, đọc log, xem metric, dựng dashboard, đặt alert và điều tra sự cố của AI agent.

Setup tài khoản, biến môi trường, collector: xem [OBSERVABILITY_SETUP.md](OBSERVABILITY_SETUP.md).

> Truy vấn mẫu bên dưới dựa trên thiết kế ở tài liệu setup (tên service, semantic conventions của OTel). Khi có dữ liệu thật, mở **Label browser** / **Metrics browser** trong Explore để kiểm tra lại tên label và metric, rồi sửa tài liệu nếu khác.

## Mục lục

1. [Truy cập](#1-truy-cập)
2. [Chọn công cụ nào cho câu hỏi nào](#2-chọn-công-cụ-nào-cho-câu-hỏi-nào)
3. [Traces — Grafana Tempo](#3-traces--grafana-tempo)
4. [Logs — Grafana Loki](#4-logs--grafana-loki)
5. [Metrics — Grafana Prometheus](#5-metrics--grafana-prometheus)
6. [Nhảy giữa trace ↔ log ↔ metric](#6-nhảy-giữa-trace--log--metric)
7. [LangSmith — trace của AI agent](#7-langsmith--trace-của-ai-agent)
8. [Dashboard](#8-dashboard)
9. [Alert](#9-alert)
10. [Kịch bản điều tra sự cố](#10-kịch-bản-điều-tra-sự-cố)
11. [Quy tắc khi thêm telemetry mới](#11-quy-tắc-khi-thêm-telemetry-mới)
12. [Reference docs & tutorial](#reference-docs--tutorial)

---

## 1. Truy cập

| Công cụ | URL | Ghi chú |
|---|---|---|
| Grafana Cloud | `https://eagerscone770.grafana.net` | Free tier có 3 user — xin owner mời vào stack |
| LangSmith | `https://apac.smith.langchain.com` | Region APAC. Gói free 1 seat — xin quyền từ owner |

Lọc theo môi trường: mọi tín hiệu có `deployment.environment` = `dev` (local) hoặc `staging` (Railway).

| Service | `service.name` |
|---|---|
| API FastAPI | `ev-care-backend` |
| Celery worker | `ev-care-worker` |
| Mock OEM (giai đoạn 2) | `mock-ev-system` |

## 2. Chọn công cụ nào cho câu hỏi nào

| Câu hỏi | Dùng | Ở đâu |
|---|---|---|
| Hệ thống có khoẻ không? Lỗi tăng? Chậm đi? | Metrics | Grafana → Dashboard / Explore (Prometheus) |
| Request này chậm ở bước nào (DB, Redis, OEM, LLM)? | Traces | Grafana → Explore (Tempo) |
| Lỗi cụ thể là gì, stacktrace ra sao? | Logs | Grafana → Explore (Loki) |
| Agent trả lời sai / gọi nhầm tool / tốn nhiều token? | LLM traces | LangSmith |
| Task Celery có chạy không, mất bao lâu? | Traces + metrics | Tempo (`ev-care-worker`) |

## 3. Traces — Grafana Tempo

**Explore → chọn datasource `grafanacloud-…-traces`.**

- **Search** (giao diện kéo thả): chọn *Service Name*, *Span Name*, *Status*, *Duration*.
- **TraceQL** (gõ truy vấn) — mẫu:

```traceql
// All 5xx requests of the backend
{ resource.service.name = "ev-care-backend" && span.http.response.status_code >= 500 }

// Slow requests (> 2s) in staging
{ resource.deployment.environment = "staging" && kind = server && duration > 2s }

// One route
{ span.http.route = "/api/v1/chat/messages" }

// Traces that contain an error anywhere
{ status = error }

// Slow DB queries
{ span.db.system = "postgresql" && duration > 500ms }

// Celery tasks
{ resource.service.name = "ev-care-worker" }
```

Đọc một trace:

- Thanh ngang = span; dài = tốn thời gian. Span con nằm thụt vào trong span cha.
- Click span → tab **Attributes** xem route, status, câu SQL (đã bỏ tham số), host gọi ra ngoài.
- Span đỏ = lỗi; tab **Events** chứa exception.
- Có `trace_id` từ log hoặc từ user báo lỗi? Dán thẳng vào ô tìm kiếm *TraceQL* / *Trace ID*.

## 4. Logs — Grafana Loki

**Explore → datasource `grafanacloud-…-logs`.** Dùng **Label browser** để chọn label, hoặc gõ LogQL:

```logql
# All backend logs in staging
{service_name="ev-care-backend", deployment_environment="staging"}

# Lines containing "error" (case-insensitive)
{service_name="ev-care-backend"} |~ "(?i)error"

# Logs of one trace
{service_name="ev-care-backend"} | trace_id="<trace-id>"

# Error rate per minute (turns logs into a metric)
sum by (service_name) (count_over_time({service_name=~"ev-care-.*"} |~ "(?i)error" [1m]))
```

Mẹo:

- Mở một dòng log → các trường `trace_id`, `span_id` có nút **Tempo** để nhảy sang trace.
- Log đã che PII (email, SĐT, token) trước khi gửi. Thấy PII lọt → báo lại để thêm luật vào `PiiRedactor`.
- Log local vẫn xem được trên stdout / file như cũ; Railway console vẫn có log.

## 5. Metrics — Grafana Prometheus

**Explore → datasource `grafanacloud-…-prom`.** Dùng **Metrics browser** để tìm tên metric.

Tên OTel được đổi sang kiểu Prometheus khi vào Grafana: `http.server.request.duration` (giây) → `http_server_request_duration_seconds_bucket` / `_count` / `_sum`. `service.name` thành label `job` (kiểm tra trong Metrics browser; có thể kèm `service_name`).

```promql
# Requests per second per route
sum by (http_route) (rate(http_server_request_duration_seconds_count{job="ev-care-backend"}[5m]))

# 5xx error ratio
sum(rate(http_server_request_duration_seconds_count{job="ev-care-backend", http_response_status_code=~"5.."}[5m]))
/
sum(rate(http_server_request_duration_seconds_count{job="ev-care-backend"}[5m]))

# p95 latency per route
histogram_quantile(0.95,
  sum by (le, http_route) (rate(http_server_request_duration_seconds_bucket{job="ev-care-backend"}[5m])))
```

Ba chỉ số nên nhìn đầu tiên (**RED**): **R**ate (số request), **E**rrors (tỉ lệ lỗi), **D**uration (p95/p99 latency).

## 6. Nhảy giữa trace ↔ log ↔ metric

| Từ | Đến | Cách |
|---|---|---|
| Log | Trace | Mở dòng log → nút **Tempo** cạnh `trace_id` |
| Trace | Log | Trong trace view → nút **Logs for this span** |
| Metric | Trace | Panel có *exemplar* (chấm nhỏ trên biểu đồ) → click → trace mẫu |
| Trace (OTel) | LangSmith | Span agent có attribute LangSmith run id → mở run trong LangSmith |
| LangSmith | Trace (OTel) | Metadata của run có `otel_trace_id` → dán vào Tempo |

Liên kết trace ↔ log và OTel ↔ LangSmith chỉ hoạt động khi phần instrument (bước 7 tài liệu setup) đã xong.

## 7. LangSmith — trace của AI agent

**Tracing Projects** → chọn `evcare-dev` (local) hoặc `evcare-staging` (Railway).

| Việc | Cách |
|---|---|
| Xem một lượt chat | Click run → cây bước: orchestrator → LLM call → tool call → RAG |
| Tìm lượt chat lỗi | Filter **Status = Error** |
| Tìm lượt chậm / tốn token | Sort theo **Latency** / **Tokens** |
| Lọc theo metadata | Filter **Metadata** (vd `otel_trace_id`, `thread_id`) |
| Biểu đồ tổng quan | Tab **Monitor**: số trace, tỉ lệ lỗi, p50/p99 latency, token, chi phí |
| Lưu ca hay để test | Chọn run → **Add to Dataset** → dùng cho eval (xem `eval/`) |
| Chấm điểm câu trả lời | **Annotation queues** hoặc feedback 👍/👎 |
| Cảnh báo / tự động | **Rules**: đưa run lỗi vào dataset, gửi webhook |

Quy ước:

- Script, benchmark, eval chạy tay → `LANGCHAIN_PROJECT` riêng (vd `evcare-eval`, `setup-test`), không ghi vào `evcare-dev` / `evcare-staging`.
- Free tier 5k trace/tháng: chạy eval lớn thì kiểm tra **Settings → Usage** trước.
- Không gửi PII thô: prompt chứa tên, SĐT, biển số cần được che.

## 8. Dashboard

Tạo: **Dashboards → New → Import** (dùng dashboard có sẵn) hoặc **New dashboard → Add visualization**.

Dashboard đề xuất cho dự án:

| Dashboard | Panel |
|---|---|
| **EV Care — API overview** | RPS, tỉ lệ 5xx, p95 latency theo route, top route chậm, log lỗi gần nhất |
| **EV Care — Worker** | Số task Celery, thời gian chạy, task lỗi |
| **EV Care — AI agent** | Token LLM theo model, latency LLM, số lần guardrail chặn, lỗi tool |

Mẹo:

- Thêm biến dashboard `env` (`dev` / `staging`) để đổi môi trường bằng dropdown.
- **Grafana Cloud → Application Observability** có thể tự dựng trang RED cho mỗi service từ trace — bật thử trước khi tự vẽ.
- Lưu JSON dashboard vào repo khi ổn định để không mất khi đổi stack.

## 9. Alert

**Alerting → Alert rules → New alert rule.** Đề xuất ban đầu:

| Alert | Điều kiện (gợi ý) | Mức |
|---|---|---|
| API lỗi nhiều | Tỉ lệ 5xx > 5% trong 5 phút | Critical |
| API chậm | p95 latency > 3s trong 10 phút | Warning |
| Mất telemetry | Không có metric từ `ev-care-backend` trong 10 phút (backend hoặc collector chết) | Critical |
| Worker lỗi | Task Celery lỗi > 3 trong 10 phút | Warning |
| LLM lỗi | Tỉ lệ run lỗi (LangSmith Rules / metric nghiệp vụ) tăng | Warning |

Kênh nhận: **Alerting → Contact points** → Discord webhook (kênh thông báo mặc định của dự án) hoặc email.

## 10. Kịch bản điều tra sự cố

**"Chat trả lời rất chậm"**

1. Dashboard *API overview* → p95 route chat có tăng không, từ lúc nào (trùng lần deploy?).
2. Tempo: `{ span.http.route = "/api/v1/chat/messages" && duration > 5s }` → mở một trace.
3. Span dài nhất là gì? DB → xem câu SQL; LLM → sang LangSmith qua run id; OEM → mock/OEM chậm.
4. LangSmith: run đó gọi bao nhiêu LLM call, bao nhiêu token, tool nào lặp lại.

**"User báo lỗi 500"**

1. Loki: `{service_name="ev-care-backend"} |~ "(?i)error"` quanh thời điểm user báo.
2. Mở dòng log → **Tempo** → xem span đỏ và exception.
3. Lỗi lặp lại? Viết regression test theo quy ước trong `CLAUDE.md`.

**"Không thấy dữ liệu trên Grafana"**

1. Collector còn sống? Railway → service `otel-collector` → Logs / health check.
2. App có `OTEL_SDK_DISABLED=true` không? `OTEL_EXPORTER_OTLP_ENDPOINT` đúng không?
3. Grafana **Usage**: có vượt giới hạn free tier không?

## 11. Quy tắc khi thêm telemetry mới

- **Span thủ công**: chỉ ở ranh giới có ý nghĩa (bước agent, gọi hệ thống ngoài). Tên span ngắn, cố định (`agent.orchestrate`), không chứa ID.
- **Metric**: label cardinality thấp. **Cấm** `user_id`, `vehicle_id`, `email`, URL thô, message. Cần theo dõi theo user → dùng trace/log.
- **Attribute / log**: không ghi token, mật khẩu, PII thô. Cần định danh → dùng ID nội bộ hoặc hash.
- **Đặt tên** theo [semantic conventions](https://opentelemetry.io/docs/specs/semconv/http/http-metrics/) và [Prometheus naming](https://prometheus.io/docs/practices/naming/).
- Thêm metric/dashboard mới → cập nhật mục 5 và 8 của tài liệu này.

---

## Reference docs & tutorial

**Grafana — truy vấn & giao diện**

| Tài liệu | Nội dung |
|---|---|
| [Grafana Explore](https://grafana.com/docs/grafana/latest/explore/) | Màn hình Explore: truy vấn, split view, nhảy giữa tín hiệu |
| [TraceQL](https://grafana.com/docs/tempo/latest/traceql/) | Ngôn ngữ truy vấn trace của Tempo |
| [LogQL](https://grafana.com/docs/loki/latest/query/) | Ngôn ngữ truy vấn log của Loki |
| [PromQL basics](https://prometheus.io/docs/prometheus/latest/querying/basics/) | Ngôn ngữ truy vấn metric |
| [Prometheus naming](https://prometheus.io/docs/practices/naming/) | Quy tắc đặt tên metric và label |
| [Dashboards](https://grafana.com/docs/grafana/latest/dashboards/) | Tạo và quản lý dashboard |
| [Alerting](https://grafana.com/docs/grafana/latest/alerting/) | Alert rule, contact point, notification policy |
| [Application Observability](https://grafana.com/docs/grafana-cloud/monitor-applications/application-observability/) | Trang RED tự động theo service |
| [Grafana tutorials](https://grafana.com/tutorials/) | Tutorial chính thức |
| [Grafana Play](https://play.grafana.org/) | Grafana demo có dữ liệu thật để tập truy vấn |

**OpenTelemetry**

| Tài liệu | Nội dung |
|---|---|
| [Concepts](https://opentelemetry.io/docs/concepts/) | Traces, metrics, logs, context propagation |
| [HTTP metrics semantic conventions](https://opentelemetry.io/docs/specs/semconv/http/http-metrics/) | Tên và label chuẩn của metric HTTP |
| [OpenTelemetry Demo](https://opentelemetry.io/docs/demo/) | Hệ thống mẫu để tập điều tra sự cố |

**LangSmith**

| Tài liệu | Nội dung |
|---|---|
| [LangSmith docs](https://docs.langchain.com/langsmith/home) | Trang chính |
| [Observability quickstart](https://docs.langchain.com/langsmith/observability-quickstart) | Đọc và lọc trace |
| [Add metadata & tags](https://docs.langchain.com/langsmith/add-metadata-tags) | Gắn metadata để lọc run |
| [Evaluation quickstart](https://docs.langchain.com/langsmith/evaluation-quickstart) | Dataset & experiment |
| [Mask inputs/outputs](https://docs.langchain.com/langsmith/mask-inputs-outputs) | Che PII |
| [LangChain Academy](https://academy.langchain.com/) | Khoá học miễn phí |
