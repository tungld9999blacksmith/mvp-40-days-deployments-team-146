# Câu hỏi chưa xử lý — Sprint 2

> Các điểm nghiệp vụ/kỹ thuật đã hoãn để giữ hệ thống đơn giản cho MVP. Hiện trạng ghi rõ ở từng mục.
>
> - **FEAT-VEH-001** (F3): nguồn [FF §24](feature-functional/us-017-sprint-2-spec.ff.md#24-open-questions).
> - **Conversation & Messaging** (nền tảng chat, F4): nguồn [platform API §14](../platform/conversation-messaging.api.md#14-open-questions), [FF F4 §24](feature-functional/us-025-sprint-2-spec.ff.md#24-open-questions).

## FEAT-VEH-001 (F3)

| ID | Trạng thái | Người xử lý |
| --- | --- | --- |
| `Q-301` | Tạm triển khai, chờ nghiên cứu | PO (Lê Đức Tùng) |
| `Q-302` | Chưa triển khai | PO + Team |

## Q-301 — Mốc kế tiếp sau mốc cuối của bảng định mức

**Vấn đề:** `maintenance_rule` chỉ có một số mốc hữu hạn (ví dụ VF6: 12.000 / 24.000 km). Xe làm xong mốc cuối thì mốc kế tiếp là gì?

**Hiện trạng (tạm thời):** mốc tăng theo bước cố định, cấu hình trong `.env`: `MAINTENANCE_RECURRING_KM=12000`, `MAINTENANCE_RECURRING_MONTHS=12`. Ví dụ sau 24.000 km / 24 tháng ⇒ 36.000 km / 36 tháng, rồi 48.000… Hạng mục lấy theo mốc đầu tiên. Code: `calculate_due_status` trong `backend/src/modules/user_vehicle/domain.py`.

**Cần làm:** PO nghiên cứu rule bảo hành để xác định chu kỳ và hạng mục thực sự của các mốc sau bảng (có thể khác nhau theo model/gói bảo hành). Sau khi có kết luận, thay bước cố định bằng nguồn từ rule bảo hành (BR-007).

## Q-302 — Cửa sổ "làm sớm" khi bảo dưỡng sớm hơn mốc

**Vấn đề:** chủ xe thường bảo dưỡng sớm hơn mốc một chút. Ví dụ mốc 12.000 km, xe làm ở 11.900 km.

**Hiện trạng:** **không triển khai** để giữ logic đơn giản. Một lần bảo dưỡng chỉ hoàn thành mốc M khi `km ≥ M.km` **hoặc** `ngày ≥ ngày đến hạn M`. Hệ quả cần biết: xe làm ở 11.900 km vẫn bị tính chưa xong mốc 12.000, còn 100 km và vẫn báo `DUE_SOON` cho tới khi qua mốc.

**Cần làm (khi team xử lý):** thêm dung sai làm sớm. Đề xuất ban đầu: 1.000 km hoặc 30 ngày, đặt trong `.env` (`MAINTENANCE_EARLY_KM`, `MAINTENANCE_EARLY_DAYS`); sửa `is_done` trong `domain.py`, BR-006, RM-401 §4 và AC-007 (đổi lại ví dụ 11.900 km).

---

## Conversation & Messaging (nền tảng chat, F4)

| ID | Trạng thái | Người xử lý |
| --- | --- | --- |
| `Q-620` | Chưa triển khai — giữ đơn giản | Backend + Team |
| `Q-621` | Chưa triển khai — bắt buộc trước prod | Backend |
| `Q-622` | Chưa triển khai | PO |

### Q-620 — Giới hạn vai trò khi ghi tin nhắn

**Vấn đề:** hợp đồng nói backend là nơi **duy nhất** ghi `chat_message` (FF F4 BR-602), nhưng code PROVISIONAL hiện cho client `POST /messages` (và WebSocket) với `role` bất kỳ, kể cả `assistant`/`system`.

**Hiện trạng:** **giữ nguyên logic đơn giản** — chưa siết. Tin nhắn vẫn đi qua route hiện có.

**Cần làm (khi team xử lý):** dồn mọi ghi tin qua `MessageService.append` (SVC-MSG-001); bỏ endpoint client ghi tin tự do; client chỉ gửi qua endpoint use case (F4 `API-CHAT-004`). Đóng cùng đợt với Q-621.

### Q-621 — Auth cho route conversation + WebSocket

**Vấn đề:** route conversation (REST + WS) hiện **không xác thực** trong dev (`TODO(auth)` trong `backend/src/modules/conversation/route.py`; AI-Q-104; memory *conversation routes no auth*).

**Hiện trạng:** **chưa xử lý** — để iterate nhanh khi dev.

**Cần làm (bắt buộc trước prod / trước khi đo AC-605):** thêm Firebase ID token + kiểm tra chủ sở hữu hội thoại cho REST; xác thực WebSocket bằng khung `auth` đầu tiên (platform API §API-MSG-001). Không đo được AC-605 (chặn đọc hội thoại người khác) tới khi làm.

### Q-622 — `conversation` có bắt buộc gắn một xe không?

**Vấn đề:** hiện `conversation.user_vehicle_id` **bắt buộc** (mọi hội thoại thuộc một xe). Use case sau này (chat chung với xưởng, chat không gắn xe cụ thể) có thể cần hội thoại không gắn xe. Trùng với Q-615 (entity `conversation`).

**Hiện trạng:** **chưa xử lý** — MVP mọi hội thoại thuộc một xe (đủ cho F4/F5/F6).

**Cần làm (khi có use case chat nhiều bên — memory *multi-party chat plan*):** cân nhắc cho `user_vehicle_id` nullable + bảng người tham gia; xem lại ADR-01.
