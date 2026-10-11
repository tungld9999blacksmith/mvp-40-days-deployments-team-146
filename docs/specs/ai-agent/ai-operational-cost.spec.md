# Đặc tả Chi phí Vận hành AI-Agent — EV Care

> **D7** trong [work-scope-clarification.md](work-scope-clarification.md). Bóc tách chi phí mỗi lượt hội thoại và mỗi lần chạy eval, các đòn bẩy giảm chi phí, và ngân sách đề xuất.
>
> ⚠️ **Đơn giá là GIẢ ĐỊNH** (đánh dấu 🔸) tại thời điểm 2026-10-05. Thay số thật vào §2 khi có hợp đồng/billing chính thức. Công thức & cấu trúc giữ nguyên.

| Field | Value |
| --- | --- |
| Loại | Operational Cost Spec |
| Version | v1.0 (số liệu giả định) |
| Ngày | 2026-10-05 |
| Generator | Gemini flash-lite (`gemini-3.5-flash-lite`) |
| Embedding | `gemini-embedding-001` |
| Judge (chỉ khi eval) | Claude Sonnet/Opus 5.x |
| Hạ tầng | Qdrant Cloud, Redis, PostgreSQL |

---

## 1. Các thành phần phát sinh chi phí

Một lượt chat đi qua nhiều lần gọi model, không chỉ 1:

| # | Thành phần | Khi nào gọi | Token điển hình |
| --- | --- | --- | --- |
| 1 | **Query rewriter** (LLM) | mỗi câu hỏi có RAG | in ~400 / out ~150 |
| 2 | **Embedding query** | mỗi lần search RAG | ~50 token |
| 3 | **Reranker** (cross-encoder) | mỗi lần search RAG | ~25 cặp (query,doc) |
| 4 | **Orchestrator/Generator** (LLM, ReAct) | mỗi lượt, có thể **nhiều vòng** | in ~2.5k–6k / out ~300–800 |
| 5 | **Embedding ingest** | offline, 1 lần/tài liệu | theo kích thước corpus |
| 6 | **LLM-as-Judge** | **chỉ khi chạy eval**, không ở production | in ~1.5k / out ~300 per case |

> **Điểm mấu chốt:** chi phí 1 lượt chat ≈ (rewriter + embedding + reranker + **generator × số vòng ReAct**). Số vòng ReAct là **đòn bẩy lớn nhất** vì generator là token đắt nhất và lặp lại.

---

## 2. Đơn giá giả định (🔸 thay số thật)

| Model | $/1M input 🔸 | $/1M output 🔸 | Nguồn |
| --- | --- | --- | --- |
| Gemini flash-lite | 0.10 | 0.40 | 🔸 giả định tier lite |
| Gemini embedding | 0.015 | — | 🔸 |
| Reranker (hosted) | ~0.02 / 1k docs 🔸 | — | 🔸 hoặc self-host GPU |
| Claude Sonnet 5.x (judge) | 3.00 | 15.00 | 🔸 tra bảng giá hiện hành |
| Claude Opus 5.x (judge, anchor) | 15.00 | 75.00 | 🔸 |

> Dùng skill `claude-api` để lấy đơn giá Claude chính xác khi cần; Gemini tra bảng giá Google. **Không hardcode vào code** — để trong config/`.env` và file giá này.

---

## 3. Chi phí một lượt hội thoại (mô hình)

**Kịch bản điển hình** (1 câu hỏi RAG + 2 vòng ReAct):

| Thành phần | Token in | Token out | Chi phí 🔸 |
| --- | --- | --- | --- |
| Rewriter | 400 | 150 | $0.00010 |
| Embedding | 50 | — | $0.0000008 |
| Reranker 25 docs | — | — | $0.0000005 |
| Generator vòng 1 (tool-calling) | 3,000 | 400 | $0.00046 |
| Generator vòng 2 (final answer) | 3,500 | 600 | $0.00059 |
| **Tổng / lượt** | | | **≈ $0.0012 🔸** |

- **Lượt "nặng"** (3–4 vòng, context dài): ≈ $0.003–0.005.
- **Lượt "nhẹ"** (small-talk, không RAG): ≈ $0.0003.
- **Ước tính tháng** (🔸): `cost/conv × conv/ngày × 30`. Ví dụ 1.000 conv/ngày × $0.0015 × 30 ≈ **$45/tháng** chi phí LLM (chưa gồm hạ tầng).

---

## 4. Chi phí hạ tầng (cố định/bán cố định)
| Hạng mục | Ghi chú | $/tháng 🔸 |
| --- | --- | --- |
| Qdrant Cloud | theo dung lượng vector + RPS | 🔸 ~$0–50 (free→starter) |
| Redis | GEO + lock + cache | 🔸 ~$0–30 |
| PostgreSQL | checkpoint + chat_message | 🔸 theo hosting |
| Reranker GPU (nếu self-host) | thay cho hosted API | 🔸 tuỳ chọn |

---

## 5. Chi phí chạy Eval (D4)
Eval tốn riêng, chủ yếu do **LLM-as-Judge**:

| Bộ | #case | Judge token/case | Chi phí/lần chạy 🔸 (Sonnet) |
| --- | --- | --- | --- |
| RAG full (faithfulness + answer) | 120 | 1.8k in / 300 out | ≈ $0.65 + generator |
| Tool-calling | 60 | rule-based (0) | ~$0 (chỉ generator) |
| Trajectory (LLM-judge) | 40 | 2k in / 400 out | ≈ $0.48 |
| Red-team | 50 | rule + judge | ≈ $0.30 |
| **Tổng / lần chạy full** | | | **≈ $1.5–2.5 🔸** |

- **Khuyến nghị:** CI chạy **subset nhanh** (rule-based + retrieval, ~$0) mỗi PR; chạy **full (có judge)** theo lịch (nightly/ pre-release) để kiểm chi phí.
- Anchor set dùng **Opus** (~30 case) định kỳ hiệu chỉnh judge → chi phí nhỏ nhưng quan trọng.

---

## 6. Đòn bẩy giảm chi phí (ưu tiên)
1. **Giảm số vòng ReAct** — prompt rõ, context xe nạp sẵn (đã làm), tránh tool thừa (đo bằng §4.2 trajectory của D8).
2. **Prompt caching** — cache system prompt + context xe ổn định (xem skill `claude-api` / Gemini context cache).
3. **Chọn tier model theo intent** — small-talk/routing dùng model rẻ; chỉ câu khó mới full context.
4. **Giảm context nhồi** — top-k vừa đủ (A/B k=3 vs 5 ở D8), nén context.
5. **Judge rẻ hơn ở diện rộng** — Sonnet cho mass, Opus chỉ anchor.
6. **Cache embedding** cho câu lặp; **batch** ingest.
7. **Rule-based thay LLM** nơi có thể (tool-calling check, EM) để eval gần như miễn phí.

---

## 7. Theo dõi & ngân sách
- **Metric business (D8 §8):** `cost / conversation` là KPI vận hành; log token in/out mỗi lượt vào trace.
- **Ngân sách gate:** cost/conv ≤ 🔸 $0.003 (cảnh báo nếu vượt) — nối vào CI gate D8 §11.
- **Dashboard:** p50/p95 token, số vòng ReAct trung bình, chi phí/ngày (Langfuse post-MVP).

---

## 8. Việc cần bạn cấp để chốt số thật
1. Tier & đơn giá Gemini thực tế đang dùng.
2. Có dùng Claude cho judge không, model nào (ảnh hưởng chi phí eval).
3. Gói Qdrant/Redis/Postgres hiện tại.
4. Lưu lượng dự kiến (conv/ngày) để ước tính tháng.
