# API Technical Specification — Agent cùng tham gia luồng chat

> Backend cho Feature `FEAT-P2-MC02`.
>
> **Nguồn nghiệp vụ:** [Functional Spec](mc-02-phase2-spec.ff.md). **Entity:** [Entity Spec](mc-02-phase2-spec.entity.md).
>
> **Tái dùng:** luồng MC-01 (`booking_thread`, WS, gửi tin), orchestrator LangGraph với **bộ tool chỉ đọc** giới hạn theo lịch của luồng: AD-01 dự toán, AD-02 tư vấn sửa chữa, AD-03 bảo hành, HS-01 lịch sử, thông tin lịch hẹn; `SafetySignalDetector` (AD-02); guard đầu ra; RAG có nguồn. Cần AI-Agent Spec riêng khi làm kỹ thuật (giống TA-01).

---

# 0. Document Information

| Field | Value |
|---|---|
| Document ID | `API-SPEC-P2-MC02` |
| Version | `v0.1` |
| Status | `Draft` |
| Base URL | `/api/v1` |
| Module | `backend/src/agents/thread_agent/` (mới: prompt, tools, graph), `modules/booking_thread/agent_hook.py` |
| Created Date | `2026-10-12` |

---

# 1. API Group

| API ID | Method | Endpoint | Mục đích | FF |
|---|---|---|---|---|
| `HOOK-MC02-01` | Internal | Tin mới của chủ xe ⇒ quyết định agent có trả lời / gắn cờ | | UC-MC02-01..03, BR-MC02-01, 04 |
| `API-MC02-01` | `PUT` | `/workshop-owner/thread-agent` | Bật / tắt cho xưởng | FF §3.1 |
| `API-MC02-02` | `PUT` | `/booking-threads/{threadId}/agent` | Bật / tắt cho một luồng (chủ xưởng) | — |
| `API-MC02-03` | `POST` | `/booking-threads/{threadId}/summary` | Tóm tắt cho xưởng | UC-MC02-04, BR-MC02-05 |
| `API-MC02-04` | `GET` | `/workshop-owner/flagged-messages` | Câu gắn cờ cần trả lời | UC-MC02-02 |

---

# 2. HOOK-MC02-01 — quyết định

Chạy nền (Celery) sau khi tin của **chủ xe** được lưu (MC-01 §4 bước 5):

1. `booking_thread.agent_enabled = false` ⇒ dừng.
2. Giờ làm (theo `workshop_operating_hour`):
   - **Trong giờ** ⇒ chỉ trả lời khi tin có "@Trợ lý" (AF-MC02-01) **hoặc** là câu hỏi thuật ngữ ("… là gì", "nghĩa là gì") về nội dung tin của xưởng (BR-MC02-02, 04).
   - **Ngoài giờ** ⇒ xử lý mọi tin.
3. Chờ 20 giây rồi kiểm: xưởng / KTV đã trả lời sau tin này ⇒ dừng (EDGE-MC02-01). Ngoài giờ, chờ 0 giây.
4. **An toàn trước** (EF-MC02-01): `SafetySignalDetector` khớp ⇒ tin agent theo mẫu an toàn + hotline (AD-02), gắn cờ tin chủ xe `flagged`, `URGENT`, thông báo khẩn chủ xưởng (+ email).
5. Phân loại câu (router ý định có sẵn + danh sách mẫu cam kết):
   - **Trong phạm vi** (BR-MC02-01): giá ước tính mốc / sửa chữa, bảo hành theo xe / chính sách, lịch sử bảo dưỡng của xe, thông tin lịch hẹn (giờ, hạng mục, địa chỉ, trạng thái), thuật ngữ.
   - **Cần cam kết** (BR-MC02-03): giảm giá, giá chốt, giờ xong cụ thể, "có bảo hành cho tôi không" với hỏng hóc cụ thể, đổi / huỷ lịch, mọi yêu cầu xưởng làm gì.
6. Trong phạm vi ⇒ chạy agent (tool chỉ đọc, phạm vi = xe + lịch của luồng; không đọc bộ nhớ PS-01 — FF §16), trả lời ≤ 10 s (FF §18), lưu tin `participant = agent`, `agent_citations`; thẻ CH-02 khi có số liệu (`ESTIMATE`, `WARRANTY_STATUS`, `SERVICE_HISTORY_ITEM`).
7. Cần cam kết ⇒ tin chủ xe `flagged`; agent gửi "Câu này {xưởng} sẽ trả lời trong giờ làm việc (từ {giờ mở cửa kế tiếp})." (UC-MC02-02); thông báo xưởng. Yêu cầu đặt / đổi / huỷ ⇒ thêm hướng dẫn "Bạn có thể đổi lịch ngay ở vé lịch hẹn" + link (FF §3.2).
8. Guard đầu ra **bắt buộc** (AC-MC02-01): chặn câu có cam kết giá / giảm giá / thời gian hoàn thành / quyết định bảo hành (mẫu + phân loại); vi phạm ⇒ thay bằng câu gắn cờ (bước 7).

Tin của xưởng / KTV sau một tin `flagged` ⇒ tin đó `answered`, `answered_by_message_id`.

---

# 3. API-MC02-01/02 — bật / tắt

- `PUT /workshop-owner/thread-agent { "enabled": true }` ⇒ `workshop.thread_agent_enabled`; áp cho luồng **mở sau đó**, và tuỳ chọn `applyToOpenThreads: true` cho luồng đang mở.
- `PUT /booking-threads/{id}/agent { "enabled": false }` (chủ xưởng) ⇒ `booking_thread.agent_enabled`; thêm / bỏ người tham gia `agent` + tin hệ thống "Trợ lý EV Care đã tham gia / rời cuộc trò chuyện".

---

# 4. API-MC02-03 — tóm tắt cho xưởng

Chủ xưởng / KTV tham gia luồng. Có tóm tắt với `up_to_seq` = tin cuối ⇒ trả lại. Không ⇒ LLM tóm tắt ≤ 1.000 ký tự (yêu cầu chính của khách, câu đã trả lời, câu còn chờ, phát sinh / quyết định), lưu `booking_thread_summary`. **Không** gửi vào luồng (BR-MC02-05). Response `{ summary, upToSeq, createdAt }`.

---

# 5. API-MC02-04 — câu gắn cờ

`[{ threadId, messageId, bookingCode, customerDisplayName, content, urgency, flaggedAt }]` của xưởng, `URGENT` trước. Workshop Portal hiện nhãn trên danh sách luồng (MC-01 SCR-MC01-02).

---

# 6. Error Cases

| HTTP | Code | Khi |
|---|---|---|
| 403 | `FORBIDDEN` | Chủ xe gọi tóm tắt / bật tắt |
| 404 | `THREAD_NOT_FOUND` | |
| 409 | `THREAD_CLOSED` | Bật agent cho luồng đã đóng |

---

# 7. Eval & Test Checklist

| Layer | What | Count |
|---|---|---|
| Eval | 0 câu agent chứa cam kết giá / giảm giá / thời gian xong / quyết định bảo hành (AC-MC02-01) | 1 bộ (`eval/datasets/thread_agent_commitments`) |
| Eval | 100 % câu ngoài phạm vi được gắn cờ (AC-MC02-02) | 1 bộ |
| Service | Trong giờ không "@Trợ lý" ⇒ agent im lặng; có ⇒ trả lời | +2 |
| Service | Xưởng trả lời trước ⇒ agent không trả lời (EDGE-MC02-01) | +1 |
| Service | Câu an toàn ⇒ lời khuyên + gắn cờ khẩn | +1 |
| Service | Tóm tắt không xuất hiện trong luồng phía chủ xe | +1 |
| Perf | Trả lời ngoài giờ ≤ 10 s | +1 |

---

# 8. Change Log

| Version | Date | Change |
|---|---|---|
| `v0.1` | `2026-10-12` | Bản nháp đầu |
