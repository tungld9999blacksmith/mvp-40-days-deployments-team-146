# Grafana — Setup alert rule gửi Discord (EV Care)

Tạo alert trên Grafana Cloud cho `ev-care-backend` / `ev-care-worker` và gửi về kênh Discord của nhóm (kênh thông báo mặc định của dự án).

- Dùng Grafana, truy vấn, dashboard: [GRAFANA_GUIDE.md](GRAFANA_GUIDE.md)
- Setup hệ thống: [OBSERVABILITY_SETUP.md](OBSERVABILITY_SETUP.md)

> Tên metric / label *(kiểm tra)* — xác nhận bằng Metrics / Label browser trước khi tạo rule ([GRAFANA_GUIDE.md §4.4](GRAFANA_GUIDE.md#44-kiểm-tra-tên-metric--label-thật)).

## Mục lục

1. [Tổng quan luồng alert](#1-tổng-quan-luồng-alert)
2. [Bước 1 — Tạo webhook Discord](#bước-1--tạo-webhook-discord)
3. [Bước 2 — Contact point Discord](#bước-2--contact-point-discord)
4. [Bước 3 — Mẫu tin nhắn gọn (notification template)](#bước-3--mẫu-tin-nhắn-gọn-notification-template)
5. [Bước 4 — Tạo alert rule](#bước-4--tạo-alert-rule)
6. [Query & Expression: A, B, C là gì](#query--expression-a-b-c-là-gì)
7. [Bước 5 — Notification policy](#bước-5--notification-policy)
8. [Vòng đời alert & khi nào gửi lại](#vòng-đời-alert--khi-nào-gửi-lại)
9. [Rule import từ file Prometheus YAML](#rule-import-từ-file-prometheus-yaml)
10. [Bước 6 — Kiểm tra end-to-end](#bước-6--kiểm-tra-end-to-end)
11. [Bộ rule đề xuất](#bộ-rule-đề-xuất)
12. [Silence & bảo trì](#silence--bảo-trì)
13. [Xử lý sự cố](#xử-lý-sự-cố)
14. [Reference docs & tutorial](#reference-docs--tutorial)

---

## 1. Tổng quan luồng alert

```text
Alert rule (mỗi 1 phút)                         Notification policy             Contact point
┌───────────────────────────────┐   firing    ┌──────────────────────────┐    ┌────────────────┐
│ A Query → B Reduce → C Thresh. │ ──────────► │ group by alertname,      │ ─► │ discord-evcare │ ─► #evcare-alerts
│ vượt ngưỡng ≥ pending period   │  resolved   │ group wait / repeat      │    │ (webhook)      │
└───────────────────────────────┘             └──────────────────────────┘    └────────────────┘
```

| Thành phần | Vai trò |
|---|---|
| **Alert rule** | Truy vấn + điều kiện + thời gian chờ (pending) + label + nội dung |
| **Contact point** | Nơi nhận (Discord webhook) + mẫu tin nhắn |
| **Notification policy** | Gộp alert, khi nào gửi, nhắc lại bao lâu |
| **Silence** | Tắt alert tạm thời (deploy, bảo trì) |

Trạng thái rule: **Normal** → (vượt ngưỡng) **Pending** → (vượt liên tục hết pending period) **Firing** → gửi tin → (hết vượt) **Normal** + tin *resolved*. Ngoài ra **No data** (truy vấn rỗng), **Error** (truy vấn lỗi).

## Bước 1 — Tạo webhook Discord

1. Tạo kênh riêng, vd `#evcare-alerts` (không dùng kênh chat chung).
2. Chuột phải kênh → **Edit Channel** → **Integrations** → **Webhooks** → **New Webhook**.
3. Đặt tên `Grafana EV Care` (tuỳ chọn đổi avatar).
4. **Copy Webhook URL** — dạng `https://discord.com/api/webhooks/<id>/<token>`.

> Webhook URL là **bí mật**: ai có URL đều gửi được tin vào kênh. Không commit, không dán vào chat. Lộ → xoá webhook, tạo cái mới, cập nhật contact point.

## Bước 2 — Contact point Discord

1. Grafana → **Alerting** → **Contact points** → **+ Add contact point**.
2. Điền:
   - **Name**: `discord-evcare`
   - **Integration**: **Discord**
   - **Webhook URL**: URL ở bước 1
3. **Test** → **Send test notification** → kênh Discord nhận tin thử.
4. **Save contact point**.

## Bước 3 — Mẫu tin nhắn gọn (notification template)

Tuỳ chọn nhưng nên làm — mẫu mặc định dài.

1. **Alerting** → **Contact points** → tab **Notification Templates** → **+ Add notification template** → tên `evcare-discord`:

```gotemplate
{{ define "evcare.title" -}}
{{ if eq .Status "firing" }}🔥 FIRING{{ else }}✅ RESOLVED{{ end }} · {{ .CommonLabels.alertname }}
{{- end }}

{{ define "evcare.message" -}}
{{ range .Alerts -}}
**[{{ .Labels.severity | toUpper }}]** {{ .Labels.service }}
{{ .Annotations.summary }}
{{ if .Annotations.description }}{{ .Annotations.description }}{{ end }}
{{ if .DashboardURL }}📊 Dashboard: {{ .DashboardURL }}{{ end }}
{{ if .SilenceURL }}🔕 Silence: {{ .SilenceURL }}{{ end }}
{{ end -}}
{{- end }}
```

2. Contact point `discord-evcare` → **Edit** → *Optional Discord settings*:
   - **Title**: `{{ template "evcare.title" . }}`
   - **Message Content**: `{{ template "evcare.message" . }}`
3. **Test** lại → **Save**.

Ví dụ tin nhận được:

```text
🔥 FIRING · API 5xx error rate high
[CRITICAL] ev-care-backend
Tỉ lệ lỗi 5xx của API là 7.5% (> 5%)
Kiểm tra trace lỗi: Explore → Tempo { resource.service.name="ev-care-backend" && status = error }
📊 Dashboard: https://eagerscone770.grafana.net/d/...
```

## Bước 4 — Tạo alert rule

Hai cách vào:

- **Từ panel**: dashboard → menu ⋮ của panel → **More…** → **New alert rule** (truy vấn điền sẵn).
- **Tạo mới**: **Alerting** → **Alert rules** → **+ New alert rule**.

Ví dụ rule **tỉ lệ lỗi 5xx của API**:

| Mục | Điền |
|---|---|
| **1. Name** | `API 5xx error rate high` (tiếng Anh, ngắn — làm tiêu đề tin Discord) |
| **2. Query A** (datasource **prom**) | xem khối dưới |
| **2. Reduce (B)** | Input `A`, Function **Last** |
| **2. Threshold (C)** | Input `B`, **IS ABOVE** `0.05` — **Set as alert condition** |
| **3. Folder** | `EV Care` |
| **3. Labels** | `severity = critical`, `service = ev-care-backend` |
| **4. Evaluation group** | `api`, interval `1m` |
| **4. Pending period** | `5m` (vượt ngưỡng liên tục 5 phút mới báo) |
| **4. No data** | **Normal** (local thường tắt backend) |
| **4. Error** | **Error** |
| **5. Contact point** | `discord-evcare` |
| **6. Summary** | `Tỉ lệ lỗi 5xx của API là {{ humanizePercentage $values.B.Value }} (> 5%)` |
| **6. Description** | `Kiểm tra trace lỗi: Explore → Tempo { resource.service.name="ev-care-backend" && status = error }` |
| **6. Link dashboard and panel** | `EV Care — API overview` |

Query A:

```promql
(
  sum(rate(http_server_request_duration_seconds_count{job="ev-care-backend", http_response_status_code=~"5.."}[5m]))
  /
  sum(rate(http_server_request_duration_seconds_count{job="ev-care-backend"}[5m]))
) or vector(0)
```

`or vector(0)`: không có request → phép chia ra NaN → rule rơi vào *No data*; thay bằng 0.

Bấm **Preview** để xem giá trị hiện tại và trạng thái, rồi **Save rule and exit**.

## Query & Expression: A, B, C là gì

A, B, C là **Ref ID** — tên của từng bước. Trường **Input** của một Expression chọn bước phía trước làm đầu vào.

```text
 A (Query)           B (Reduce)              C (Threshold)
 ┌──────────────┐    ┌────────────────┐      ┌────────────────┐
 │ PromQL/LogQL │ ─► │ Input: A       │ ─►   │ Input: B       │ ─► FIRING / Normal
 │ → chuỗi giá  │    │ Last → 1 số    │      │ IS ABOVE 0.05  │
 │ trị theo thời│    │ cho mỗi series │      │ → 1 (vi phạm)  │
 │ gian         │    └────────────────┘      │   / 0          │
 └──────────────┘                            └────────────────┘
                                               ★ Alert condition
```

| Ref ID | Loại | Làm gì | Input |
|---|---|---|---|
| A | Query | Chạy PromQL / LogQL → chuỗi điểm theo thời gian | — (dữ liệu gốc) |
| B | Reduce | Rút cả chuỗi thành **một số** mỗi series: *Last* (mới nhất, dùng nhiều nhất), *Mean*, *Max* | A |
| C | Threshold | So với ngưỡng → 1 / 0 | B |

- Bước gắn **Alert condition** quyết định rule báo hay không — thêm / xoá bước thì kiểm tra lại nút **Set as alert condition** ở bước cuối.
- Các Expression khác:

  | Loại | Dùng khi | Ví dụ |
  |---|---|---|
  | **Math** | Tính giữa các bước bằng `$A`, `$B` | A = request lỗi, B = tổng → Math `$A / $B` |
  | **Classic condition** | Kiểu cũ, gộp Reduce + Threshold (`WHEN last() OF A IS ABOVE …`) | Rule cũ; rule mới dùng Reduce + Threshold |
  | **Resample** | Đồng bộ thời gian giữa series trước Math | Hiếm |

- Trong Summary / Description, `$values.<RefID>.Value` lấy giá trị của bước: dùng **B** (sau Reduce) để ra số thật (`7.5%`); dùng **C** chỉ ra `1` / `0`; `<no value>` = sai Ref ID.
- Query có `sum by (http_route)` → mỗi route là một series → mỗi route vượt ngưỡng thành **một alert riêng** (label `http_route`). Notification policy *Group by* `alertname` để gộp thành một tin.
- Đổi tên Ref ID (click vào chữ A / B / C) → sửa lại Input của bước sau và `$values.<tên>`.

## Bước 5 — Notification policy

**Alerting** → **Notification policies** → **Default policy** → **Edit**:

| Tuỳ chọn | Giá trị | Ý nghĩa |
|---|---|---|
| Default contact point | `discord-evcare` | Rule không chọn contact point riêng sẽ gửi về đây |
| Group by | `alertname`, `service` | Gộp alert giống nhau thành một tin |
| Group wait | `30s` | Chờ gộp trước tin đầu tiên |
| Group interval | `5m` | Khoảng giữa các tin bổ sung cho cùng nhóm |
| Repeat interval | `4h` | Lỗi còn thì nhắc lại sau 4 giờ |

Muốn tách kênh theo mức độ (vd `critical` → `#evcare-oncall`): thêm **child policy** với matcher `severity = critical` → contact point khác.

## Vòng đời alert & khi nào gửi lại

Một alert đi qua hai tầng, mỗi tầng có cấu hình riêng:

```text
Mỗi evaluation interval (1m): chạy Query → Condition
   │ điều kiện đúng liên tục đủ Pending period ──► Pending ──► Firing
   │ điều kiện hết đúng (+ Keep firing for) ──────► Normal  ──► gửi RESOLVED
   ▼
Firing ──► Notification policy: chờ Group wait ──► gửi tin đầu
          vẫn Firing, không đổi ──► nhắc lại sau Repeat interval
```

Firing **không** nghĩa là gửi tin mỗi phút: rule chỉ đổi trạng thái, tần suất gửi do policy quyết định.

**1. Notification policy** — *Alerting → Notification policies → policy → Edit → Timing options* (áp cho mọi rule đi qua policy đó):

| Tuỳ chọn | Mặc định | Ý nghĩa | Chỉnh khi |
|---|---|---|---|
| **Group wait** | 30s | Chờ sau alert đầu tiên của nhóm rồi mới gửi tin đầu (để gom alert cùng lúc) | Muốn nhận tin sớm hơn: giảm |
| **Group interval** | 5m | Nhóm đã gửi, có alert mới hoặc đổi trạng thái → đợi tối thiểu chừng này mới gửi cập nhật | Bị dồn tin: tăng |
| **Repeat interval** | 4h | Alert vẫn Firing và không đổi → nhắc lại sau chừng này | Muốn nhắc nhiều: giảm (vd 1h). Muốn gần như không nhắc: tăng (vd 24h) |

Muốn một rule có nhịp riêng (vd rule "Service started" chỉ báo một lần): tạo **nested policy** riêng cho rule đó (matcher `alertname = ...`) và đặt Timing options riêng, đứng **trên** policy chung.

**2. Rule** — *mở rule → Edit → Evaluation behavior*:

| Tuỳ chọn | Ý nghĩa |
|---|---|
| **Evaluation interval** | Bao lâu đánh giá một lần (group `agent`: 1m) |
| **Pending period** (`for`) | Điều kiện đúng liên tục bao lâu mới Firing — lọc nhiễu thoáng qua |
| **Keep firing for** | Điều kiện hết đúng vẫn giữ Firing thêm chừng này mới Resolved — chống nhấp nháy báo/hết liên tục |

**3. Tạm chặn / tắt hẳn**

| Công cụ | Tác dụng |
|---|---|
| **Silence** | Chặn *thông báo* theo label trong một khoảng thời gian; rule vẫn Firing |
| **Mute timing** | Khung giờ cố định không gửi (vd ban đêm), gắn vào policy |
| **Pause evaluation** (trên rule) | Ngừng đánh giá hoàn toàn; không còn trạng thái mới, cũng không có tin RESOLVED |

## Rule import từ file Prometheus YAML

Khi import file định dạng Prometheus (vd [agent-cost-latency.standard-alert-rules.yaml](../../infrastructure/observability/grafana/agent-cost-latency.standard-alert-rules.yaml)), Grafana chuyển mỗi rule thành chuỗi `query → math (is_number) → threshold (> 0)`, gắn nhãn `__converted_prometheus_rule__`. Hệ quả:

- **Điều kiện nằm trong PromQL** (`... > 15`), không nằm ở bước Threshold. Đổi ngưỡng = sửa số trong biểu thức.
- **Điều kiện sai → truy vấn trả rỗng → `Normal (NoData)`**. Đây là trạng thái bình thường, không phải lỗi. Cũng vì vậy, đổi ngưỡng ở bước Threshold (vd `-1`) không làm rule Firing.
- **Không có contact point trong rule** (định dạng Prometheus không có trường này). Phải có nested policy khớp label (vd `service = ev-care-backend` → `discord-evcare`), nếu không alert đi vào contact point mặc định và contact point Discord hiện *No delivery attempts*.
- Import đặt `execErrState: OK` (lỗi truy vấn bị im): đổi sang **Error** trong từng rule.
- Có thể bị tích sẵn **Pause imported alerting rules** lúc import: bỏ tích, hoặc *Resume evaluation* ở group.
- **Thử bắn tin:** sửa tạm biểu thức của một rule thành `vector(1)` (luôn có giá trị), lưu, chờ 1–2 phút, rồi **trả lại biểu thức gốc**.

## Bước 6 — Kiểm tra end-to-end

1. Sửa rule: tạm đặt threshold `IS ABOVE -1` (luôn đúng), pending `0s` → Save. *(Rule import từ Prometheus YAML: thay bằng biểu thức `vector(1)`, xem mục trên.)*
2. Chờ 1–2 phút → Discord nhận `🔥 FIRING`.
3. Trả rule về như cũ → sau 1–2 chu kỳ nhận `✅ RESOLVED`.
4. Thử lỗi thật: backend chạy `OTEL_ENABLED=true`, gọi liên tục một API trả 500.

## Bộ rule đề xuất

Đặt trong folder `EV Care`; evaluation group `api` (1m) cho backend, `worker` (1m) cho worker.

| Rule | Datasource | Query A | Condition | Pending | Severity |
|---|---|---|---|---|---|
| **API 5xx error rate high** | prom | Bước 4 | > `0.05` | 5m | critical |
| **API p95 latency high** | prom | `histogram_quantile(0.95, sum by (le) (rate(http_server_request_duration_seconds_bucket{job="ev-care-backend"}[5m]))) or vector(0)` | > `2` (giây) | 10m | warning |
| **Error logs burst** | logs | `sum(count_over_time({service_name=~"ev-care-(backend\|worker)"} \| severity_text=~"ERROR\|FATAL" [5m])) or vector(0)` | > `10` | 5m | warning |
| **Celery task failures** | logs | `sum(count_over_time({service_name="ev-care-worker"} \|= "raised unexpected" [10m])) or vector(0)` | > `3` | 0m | warning |
| **Backend stopped sending telemetry** | prom | `absent_over_time(http_server_request_duration_seconds_count{job="ev-care-backend"}[15m])` | > `0` | 5m | critical |

- **Stopped sending telemetry**: chỉ bật khi đã chạy trên staging (local hay tắt backend → báo liên tục); khi đó thêm điều kiện lọc môi trường staging vào truy vấn *(kiểm tra tên label môi trường)*.
- Rule trên **logs** dùng LogQL dạng metric (`count_over_time`) — chọn datasource **logs** cho Query A.
- Summary gợi ý:

  | Rule | Summary |
  |---|---|
  | p95 latency | `p95 latency của API là {{ humanizeDuration $values.B.Value }} (> 2s)` |
  | Error logs burst | `{{ $values.B.Value }} log lỗi trong 5 phút` |
  | Celery task failures | `{{ $values.B.Value }} task Celery lỗi trong 10 phút` |
  | Stopped telemetry | `Không nhận metric từ ev-care-backend trong 15 phút (backend hoặc otel-collector dừng?)` |

## Silence & bảo trì

- **Tắt tạm thời** (deploy, bảo trì): **Alerting** → **Silences** → **+ Add silence** → matcher `service = ev-care-backend` (hoặc `alertname = ...`) → thời lượng. Link *Silence* cũng có sẵn trong tin Discord.
- **Lịch tắt cố định** (vd ngoài giờ cho môi trường dev): **Alerting** → **Notification policies** → tab **Mute Timings** → tạo khoảng thời gian → gắn vào policy.

## Xử lý sự cố

| Hiện tượng | Nguyên nhân / cách sửa |
|---|---|
| Test không thấy tin Discord | Webhook URL sai / đã xoá — tạo lại webhook |
| Rule luôn **No data** | Truy vấn trả rỗng (sai metric / label) hoặc thiếu `or vector(0)` |
| Rule **Error** | Lỗi cú pháp hoặc sai datasource (LogQL trên prom) |
| Báo rồi tắt liên tục (flapping) | Ngưỡng quá sát — tăng pending period hoặc nới ngưỡng |
| Tin hiện `<no value>` | Sai Ref ID trong `$values.X.Value` |
| Một sự cố ra rất nhiều tin | Query chia theo label (`sum by (...)`) — Group by `alertname` trong policy |
| Không nhận tin *resolved* | Rule đã bị xoá / tạm dừng trước khi về Normal |
| Rule luôn `Normal (NoData)` dù đổi ngưỡng | Rule import từ Prometheus YAML: điều kiện nằm trong PromQL, xem [mục import](#rule-import-từ-file-prometheus-yaml) |
| Contact point ghi *No delivery attempts* | Chưa có nested policy trỏ tới contact point (hoặc rule chưa từng Firing) |
| Firing mà không thấy tin | Silence / mute timing đang chặn, hoặc policy khác khớp trước (không bật *Continue matching*); dùng *Preview routing* trong rule |
| Muốn nhắc lại thường xuyên / ít hơn | Chỉnh *Repeat interval* trong policy ([Vòng đời alert](#vòng-đời-alert--khi-nào-gửi-lại)) |

---

## Reference docs & tutorial

| Tài liệu | Nội dung |
|---|---|
| [Alerting fundamentals](https://grafana.com/docs/grafana/latest/alerting/fundamentals/) | Khái niệm: rule, contact point, policy, trạng thái |
| [Create Grafana-managed alert rules](https://grafana.com/docs/grafana/latest/alerting/alerting-rules/create-grafana-managed-rule/) | Từng mục khi tạo rule |
| [Queries and conditions](https://grafana.com/docs/grafana/latest/alerting/fundamentals/alert-rules/queries-conditions/) | Query, Reduce, Math, Threshold, Ref ID |
| [Alert rule evaluation](https://grafana.com/docs/grafana/latest/alerting/fundamentals/alert-rule-evaluation/) | Evaluation interval, pending period, No data / Error |
| [Configure Discord](https://grafana.com/docs/grafana/latest/alerting/configure-notifications/manage-contact-points/integrations/configure-discord/) | Contact point Discord |
| [Notification templates](https://grafana.com/docs/grafana/latest/alerting/configure-notifications/template-notifications/) | Mẫu tin nhắn (Go template) |
| [Templating labels & annotations](https://grafana.com/docs/grafana/latest/alerting/alerting-rules/templates/) | `$values`, `$labels`, `humanizePercentage`… |
| [Notification policies](https://grafana.com/docs/grafana/latest/alerting/configure-notifications/create-notification-policy/) | Group by, group wait / interval, repeat, child policy |
| [Silences](https://grafana.com/docs/grafana/latest/alerting/configure-notifications/create-silence/) | Tắt alert tạm thời |
| [Discord — Intro to Webhooks](https://support.discord.com/hc/en-us/articles/228383668-Intro-to-Webhooks) | Tạo webhook trên Discord |
| [PromQL functions](https://prometheus.io/docs/prometheus/latest/querying/functions/) · [LogQL](https://grafana.com/docs/loki/latest/query/) | Ngôn ngữ truy vấn cho Query A |
