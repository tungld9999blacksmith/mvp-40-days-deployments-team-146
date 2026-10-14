# AI agent — độ trễ & chi phí (Grafana)

Cách đo thời gian phản hồi và chi phí LLM của agent cho **từng tin nhắn**, **từng node của graph**, **từng tool**, **từng lời gọi LLM**; cách dựng dashboard, tạo alert Discord và xuất báo cáo CSV.

## Mục lục

1. [Tổng quan](#1-tổng-quan)
2. [Bật / tắt](#2-bật--tắt)
3. [Đo cái gì](#3-đo-cái-gì)
4. [Công thức chi phí & bảng giá token](#4-công-thức-chi-phí--bảng-giá-token)
5. [Dựng dashboard](#5-dựng-dashboard)
6. [Alert gửi Discord](#6-alert-gửi-discord)
7. [Báo cáo chi phí (CSV)](#7-báo-cáo-chi-phí-csv)
8. [Giới hạn đã biết](#8-giới-hạn-đã-biết)
9. [Xử lý sự cố](#9-xử-lý-sự-cố)

## 1. Tổng quan

```text
tin nhắn người dùng
  └─ agent.turn ───────────── tổng thời gian · tổng token · tổng chi phí (span + metric)
       ├─ agent.guard.input
       ├─ node "agent"  ── chat <model>   thời gian · token vào/ra · chi phí
       ├─ node "tools"  ── execute_tool <tên>   thời gian · trạng thái
       │                     └─ RAG: retrieve · rerank · (LLM rewrite / generate = node "direct")
       └─ agent.guard.tool_calls
```

- Nguồn token: `usage_metadata` của LangChain (đã bật `stream_usage=True`); LLM gọi ngoài LangChain lấy từ `LLMResponse.usage`.
- Chỉ có **con số**, không có nội dung prompt / câu trả lời. Nội dung nằm ở LangSmith.
- Không lưu DB. Xem trên Grafana, xuất CSV khi cần báo cáo ([mục 7](#7-báo-cáo-chi-phí-csv)).
- "Từng agent" hiện = từng **node của LangGraph** (`agent`, `tools`) và từng **tool**. Nhãn `agent_node` = `direct` cho LLM gọi ngoài LangChain (RAG rewrite / generate, review booking, follow-up).

## 2. Bật / tắt

| Biến | Mặc định | Tác dụng |
|---|---|---|
| `OTEL_ENABLED` | `false` | Bật OpenTelemetry của cả app (HTTP, DB, Celery…) |
| `OTEL_AGENT_ENABLED` | `false` | Bật phần **Grafana của AI agent**: span agent, mọi metric trong tài liệu này, dòng log tổng kết lượt chat |

- Muốn thấy dữ liệu agent trên Grafana cần **cả hai** `=true` (đặt trên `backend` và `worker` ở Railway).
- `OTEL_AGENT_ENABLED=false` **không ảnh hưởng LangSmith**: LangSmith vẫn theo `LANGCHAIN_TRACING_V2` và luôn ghi trace đầy đủ.
- Khi tắt, các hàm ghi metric / span là no-op nên gần như không tốn tài nguyên.

## 3. Đo cái gì

Tên Prometheus: dấu `.` → `_`, đơn vị `s` → `_seconds`, counter thêm `_total`, histogram thêm `_bucket` / `_sum` / `_count`.

| Metric OTel | Loại | Label | Ý nghĩa |
|---|---|---|---|
| `evcare.agent.turn.duration` | Histogram (s) | `agent.outcome` | **Cả tin nhắn**: từ lúc nhận đến câu trả lời cuối |
| `evcare.agent.turn.cost.usd` | Histogram (USD) | `agent.outcome` | Chi phí LLM của **một** lượt chat |
| `evcare.llm.call.duration` | Histogram (s) | `gen_ai.request.model`, `agent.node`, `llm.status` | Mỗi lời gọi LLM |
| `evcare.llm.tokens` | Counter | `gen_ai.request.model`, `agent.node`, `gen_ai.token.type` (`input` / `output`) | Token |
| `evcare.llm.cost.usd` | Counter | `gen_ai.request.model`, `agent.node` | Chi phí ước tính (USD) |
| `evcare.llm.unpriced.calls` | Counter | `gen_ai.request.model`, `agent.node` | Lời gọi của model chưa có giá (chi phí **không** được tính) |
| `evcare.agent.tool.duration` | Histogram (s) | `gen_ai.tool.name`, `tool.status` | Mỗi lần chạy tool |
| `evcare.agent.tool.calls` | Counter | `gen_ai.tool.name`, `tool.status` | Số lần gọi tool |
| `evcare.rag.stage.duration` | Histogram (s) | `rag.stage` | RAG retrieve / rerank |

**Theo từng tin nhắn cụ thể** (không đưa vào label metric — quá nhiều giá trị): xem thuộc tính của span `agent.turn` trong Tempo: `agent.duration_ms`, `llm.calls`, `llm.duration_ms`, `llm.tokens.input`, `llm.tokens.output`, `llm.cost_usd`, `llm.unpriced_calls`. Dòng log tổng kết `Agent turn finished` (Loki) có cùng số liệu và `trace_id`.

TraceQL ví dụ — 10 lượt chat tốn kém nhất:

```text
{ name = "agent.turn" && span.llm.cost_usd > 0.01 }
```

Quy tắc label: chỉ giá trị hữu hạn (model, node, tool, outcome). **Không** gắn user / vehicle / conversation id (free tier giới hạn 10k series).

## 4. Công thức chi phí & bảng giá token

Chi phí một lời gọi LLM:

```text
cost_usd = (input_tokens × giá_input_per_1M + output_tokens × giá_output_per_1M) / 1.000.000
```

- Chi phí một lượt chat = tổng chi phí mọi lời gọi LLM trong lượt (kể cả RAG rewrite / generate).
- Chi phí theo node = tổng theo nhãn `agent_node`.
- Model không có trong bảng giá: token vẫn được đếm, chi phí **không** được tính, `evcare_llm_unpriced_calls_total` tăng và log cảnh báo một lần.

Ví dụ: `gpt-4o-mini`, 1.000 token vào + 500 token ra → `(1000 × 0,15 + 500 × 0,60) / 1.000.000 = 0,00045 USD`.

### Bảng giá (USD / 1 triệu token)

Nguồn duy nhất: [model_prices.json](../../backend/src/infrastructure/observability/model_prices.json). Bảng dưới là bản sao để đọc — khi lệch, file JSON là đúng.

| Model | Input | Output | Trạng thái |
|---|---|---|---|
| `google/gemini-3.5-flash-lite` | 0,30 | 2,50 | OpenRouter, lấy ngày 13/10/2026 |
| `mistralai/mistral-small-2603` | 0,15 | 0,60 | OpenRouter, lấy ngày 13/10/2026 |
| `openai/gpt-4o` | 2,50 | 10,00 | OpenRouter, lấy ngày 13/10/2026 |
| `gpt-4o-mini` | 0,15 | 0,60 | Model OpenAI trực tiếp (`MODEL_NAME`) |

Nguồn giá OpenRouter: `https://openrouter.ai/api/v1/models` (trường `pricing`, đổi sang USD / 1 triệu token). Giá có thể đổi — kiểm tra lại định kỳ. Model gọi trực tiếp qua Google (`gemini-3.5-flash-lite`, `GEMINI_MODEL`) chưa có giá: hiện chỉ là fallback và đang tắt (`LLM_FALLBACK_PROVIDER=""`).

Model nào chưa có giá thì panel "Lời gọi LLM chưa có giá" sẽ > 0.

### Thêm / đổi giá

1. Mở [model_prices.json](../../backend/src/infrastructure/observability/model_prices.json), thêm dòng:

   ```json
   "gemini-3.5-flash-lite": {"input_per_1m": 0.10, "output_per_1m": 0.40}
   ```

   (số trên chỉ là ví dụ định dạng). Khóa viết thường, tiền tố nhà cung cấp (`google/`) là tuỳ chọn — `google/gemini-x` khớp với khóa `gemini-x`.
2. Cập nhật bảng ở trên.
3. Deploy lại `backend` và `worker`. Chi phí lịch sử đã ghi **không** tính lại.

## 5. Dựng dashboard

### Cách nhanh: import file có sẵn

1. Grafana → **Dashboards** → **New** → **Import**.
2. **Upload dashboard JSON file** → chọn [agent-cost-latency.dashboard.json](../../infrastructure/observability/grafana/agent-cost-latency.dashboard.json).
3. **Import**. Biến **Prometheus** (góc trên) chọn datasource `grafanacloud-…-prom`.
4. **Save** vào folder `EV Care`, rồi **Share** → mời các thành viên (Viewer là đủ để xem và xuất CSV).

Dashboard gồm 4 hàng:

| Hàng | Panel |
|---|---|
| Tổng quan | Chi phí, số lượt chat, chi phí / lượt, token, p95 lượt chat, số lời gọi chưa có giá |
| Độ trễ | Lượt chat p50 / p95; LLM p95 theo node; tool p95 theo tool; RAG p95 theo stage |
| Chi phí & token | Chi phí theo node; token theo model; chi phí / lượt p50 / p95; tỉ lệ lỗi LLM |
| Báo cáo | 2 bảng (model × node, tool) để xuất CSV |

Time range chọn góc trên phải (mặc định 24 giờ); các panel tổng quan và bảng báo cáo tính theo khoảng đó.

### Cách thủ công: thêm một panel

1. Dashboard → **Add** → **Visualization** → datasource Prometheus → chế độ **Code**.
2. Dán một truy vấn, chọn visualization và đơn vị:

| Muốn xem | PromQL | Visualization / unit |
|---|---|---|
| Chi phí trong khoảng đang chọn | `sum(increase(evcare_llm_cost_usd_total[$__range]))` | Stat · `currencyUSD` |
| p95 độ trễ cả tin nhắn | `histogram_quantile(0.95, sum by (le) (rate(evcare_agent_turn_duration_seconds_bucket[$__rate_interval])))` | Time series · `s` |
| Chi phí theo node | `sum by (agent_node) (increase(evcare_llm_cost_usd_total[1h]))` | Time series (stacked) |
| Tool chậm nhất | `histogram_quantile(0.95, sum by (le, gen_ai_tool_name) (rate(evcare_agent_tool_duration_seconds_bucket[$__rate_interval])))` | Time series · `s` |

Chi tiết cách chọn visualization: [GRAFANA_GUIDE.md](GRAFANA_GUIDE.md).

> Tên Prometheus ở trên suy ra từ quy tắc đổi tên của OTel. Nếu panel trống: **Explore** → Metrics browser → gõ `evcare_` để xem tên và label thật.

## 6. Alert gửi Discord

Dùng lại contact point `discord-evcare` và template `evcare-discord`: làm **Bước 1–3** trong [GRAFANA_ALERTING.md](GRAFANA_ALERTING.md#bước-1--tạo-webhook-discord) nếu chưa có. Tạo rule theo **Bước 4** (cùng bảng điền, đổi Name / Query / ngưỡng). Tần suất gửi và gửi lại: [Vòng đời alert](GRAFANA_ALERTING.md#vòng-đời-alert--khi-nào-gửi-lại).

### Cách nhanh: import file YAML (định dạng Prometheus)

File [agent-cost-latency.standard-alert-rules.yaml](../../infrastructure/observability/grafana/agent-cost-latency.standard-alert-rules.yaml) chứa 7 rule (group `agent`, interval `1m`, label `service = ev-care-backend`, kèm summary và description).

1. **Alerting** → **Alert rules** → **New** (hoặc menu *More*) → **Import to Grafana-managed rules** → chọn **Prometheus YAML**, datasource Prometheus `grafanacloud-prom`, folder đích `EV Care`.
2. Dán hoặc tải lên file, bỏ tích **Pause imported alerting rules** (nếu có), rồi **Import**.
3. **Bắt buộc: tạo notification policy.** Định dạng Prometheus không chứa contact point, nên rule nào cũng đi theo cây policy. Vào **Alerting → Notification policies** → *Default policy* ⋮ → **New nested policy**: label `service` `=` `ev-care-backend`, contact point `discord-evcare`, lưu. Thiếu bước này, Discord sẽ không nhận tin (cột *Last delivery attempt* của contact point ghi "No delivery attempts").
4. Mở từng rule, đổi **Alert state if execution error** từ `OK` sang **Error** (import đặt `OK`, lỗi truy vấn sẽ bị im), chỉnh ngưỡng nếu cần.

Cách rule hoạt động: điều kiện nằm ngay trong PromQL (`... > 15`). Điều kiện sai hoặc metric chưa có thì truy vấn trả rỗng và rule hiện **Normal (NoData)** — đây là trạng thái bình thường, không phải lỗi. Rule chỉ chuyển Pending/Firing khi truy vấn có giá trị. **Thử bằng cách đổi tạm biểu thức của một rule thành `vector(1)`** (đổi ngưỡng ở bước Threshold không có tác dụng).

### Hoặc tạo tay từng rule

Folder `EV Care`, evaluation group `agent` (interval `1m`), contact point `discord-evcare`, label `service = ev-care-backend`.

| Rule (Name) | Query A (datasource prom) | Condition (C) | Pending | Severity |
|---|---|---|---|---|
| **Agent p95 latency high** | `histogram_quantile(0.95, sum by (le) (rate(evcare_agent_turn_duration_seconds_bucket[10m]))) or vector(0)` | > `15` (giây) | 10m | warning |
| **Agent LLM error rate high** | `(sum(rate(evcare_llm_call_duration_seconds_count{llm_status="error"}[10m])) / sum(rate(evcare_llm_call_duration_seconds_count[10m]))) or vector(0)` | > `0.1` | 5m | critical |
| **Agent tool slow** | `histogram_quantile(0.95, sum by (le) (rate(evcare_agent_tool_duration_seconds_bucket[10m]))) or vector(0)` | > `8` | 10m | warning |
| **LLM cost per hour high** | `sum(increase(evcare_llm_cost_usd_total[1h])) or vector(0)` | > `1` (USD) | 0m | warning |
| **LLM cost per day high** | `sum(increase(evcare_llm_cost_usd_total[24h])) or vector(0)` | > `10` (USD) | 0m | critical |
| **Agent cost per turn high** | `(sum(increase(evcare_agent_turn_cost_usd_sum[1h])) / sum(increase(evcare_agent_turn_cost_usd_count[1h]))) or vector(0)` | > `0.02` (USD) | 15m | warning |
| **LLM model has no price** | `sum(increase(evcare_llm_unpriced_calls_total[15m])) or vector(0)` | > `0` | 0m | warning |

### Rule thứ 8: thông báo deploy / restart (Loki)

`backend` và `worker` ghi một dòng log `Service started` (kèm `service`, `service_version` = 12 ký tự đầu của commit Railway, `deployment_environment`) mỗi lần process khởi động ([telemetry.py](../../backend/src/infrastructure/observability/telemetry.py), `log_service_started`). Rule **Service started (deploy or restart)** (severity `info`) báo Discord khi thấy dòng này trong 5 phút. Import file [agent-cost-latency.loki-alert-rules.yaml](../../infrastructure/observability/grafana/agent-cost-latency.loki-alert-rules.yaml) như trên nhưng chọn datasource **Loki** (`grafanacloud-logs`); cần cùng notification policy ở bước 3:

```logql
sum by (service_name) (count_over_time({service_name=~"ev-care-(backend|worker)"} |= "Service started" [5m]))
```

- Chỉ báo khi service **lên được**: deploy lỗi hoặc crash trước khi khởi động xong sẽ không có log. Để biết deploy thất bại, dùng thêm webhook của Railway (Project Settings → Webhooks → Discord).
- Báo lặp lại nhiều lần trong vài phút nghĩa là service đang crash-loop.
- Worker prefork ghi một dòng cho mỗi tiến trình con nên có thể thấy nhiều dòng cho một lần deploy; rule đã gom theo `service_name`.
- Xem version đã deploy: Explore → Loki `{service_name="ev-care-backend"} |= "Service started"`, đọc `service_version`.
- Tên datasource Loki mặc định là `grafanacloud-logs`; chọn đúng datasource khi import.

- Ngưỡng ở trên là điểm khởi đầu — chỉnh theo số thực tế sau vài ngày chạy (xem p95 và chi phí / ngày trên dashboard rồi đặt ngưỡng cao hơn ~30–50%).
- Mỗi rule: **Reduce (B)** = `A`, **Last**; **Threshold (C)** = `B`, **IS ABOVE**; **No data** = **Normal** (không có lượt chat thì không có số liệu).
- Summary gợi ý:

  | Rule | Summary |
  |---|---|
  | p95 latency | `p95 một lượt chat là {{ humanizeDuration $values.B.Value }} (> 15s)` |
  | LLM error rate | `{{ humanizePercentage $values.B.Value }} lời gọi LLM lỗi trong 10 phút` |
  | Cost per hour / day | `Chi phí LLM {{ printf "%.2f" $values.B.Value }} USD (vượt ngưỡng)` |
  | Cost per turn | `Chi phí trung bình một lượt chat là {{ printf "%.4f" $values.B.Value }} USD` |
  | No price | `Có model chưa khai báo giá trong model_prices.json — chi phí đang bị thiếu` |

- Description gợi ý: `Tìm lượt chat tốn kém: Explore → Tempo { name = "agent.turn" && span.llm.cost_usd > 0.01 }`.
- Kiểm tra: **Preview** trong form rule, và **Send test notification** ở contact point.
- Tắt tạm khi deploy / chạy test tải: **Silences** như trong [GRAFANA_ALERTING.md](GRAFANA_ALERTING.md#silence--bảo-trì).

## 7. Báo cáo chi phí (CSV)

1. Mở dashboard **EV Care — Agent: độ trễ & chi phí**, chọn time range (vd. *Last 7 days*, hoặc tháng trước).
2. Kéo xuống hàng **Báo cáo**; menu ⋮ của bảng → **Inspect** → **Data**.
3. Tuỳ chọn *Apply panel transformations* bật, rồi **Download CSV**.

Cột bảng model × node: `gen_ai_request_model`, `agent_node`, `cost_usd`, `input_tokens`, `output_tokens`, `calls`, `avg_seconds`. Muốn chia theo ngày: sửa truy vấn thành `increase(...[1d])` và dùng *Time series* thay vì *Table*, rồi xuất CSV.

Lưu ý: thời gian giữ metric của gói Grafana Cloud đang dùng là có hạn (xem *Administration → Cost management / Usage*) — xuất CSV định kỳ nếu cần lưu báo cáo lâu hơn.

## 8. Giới hạn đã biết

- **Luồng `chat_stream` của LLM ngoài LangChain** (`TracedLLMProvider.chat_stream`) chưa có số token nên chưa tính vào chi phí. Lượt chat chính của agent (LangChain, stream) **có** token.
- Chi phí là **ước tính** theo bảng giá trong repo; hoá đơn nhà cung cấp là số chính thức (OpenRouter có thể tính thêm phí / chiết khấu cache).
- Token cache / reasoning chưa tách giá riêng — tính như input / output thường.
- Model fallback (Gemini khi lỗi) được tính theo tên model thực sự trả lời, cần có giá riêng trong bảng.
- Metric ghi theo chu kỳ export 60 giây (`OTEL_METRIC_EXPORT_INTERVAL_MS`): số mới xuất hiện sau ≤ 1–2 phút.

## 9. Xử lý sự cố

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Dashboard trống | `OTEL_AGENT_ENABLED` chưa `true` (hoặc chỉ đặt ở `backend`, quên `worker`) | Đặt biến, redeploy, gửi vài tin nhắn |
| Có token, không có chi phí | Model chưa có giá | Panel *chưa có giá* > 0 → thêm vào `model_prices.json` |
| Chi phí = 0 mà có lượt chat | Model không trả `usage_metadata` | Kiểm tra `stream_usage=True` và tab *Explore* → `evcare_llm_tokens_total` |
| Panel báo "No data" nhưng Explore có | Sai datasource trong biến **Prometheus** | Chọn lại datasource |
| Alert không bắn | Rule ở trạng thái *Pending* hoặc sai contact point | Xem **Alerting → Alert rules** (trạng thái, Preview), kiểm tra policy |
| Tên metric khác trong tài liệu | Quy tắc đổi tên của Grafana Cloud | Dùng Metrics browser, sửa truy vấn |

Liên quan: [OBSERVABILITY_SETUP.md](OBSERVABILITY_SETUP.md#bước-7b--telemetry-của-ai-agent-grafana--langsmith) · [OBSERVABILITY_USAGE.md](OBSERVABILITY_USAGE.md) · [GRAFANA_GUIDE.md](GRAFANA_GUIDE.md) · [GRAFANA_ALERTING.md](GRAFANA_ALERTING.md).
