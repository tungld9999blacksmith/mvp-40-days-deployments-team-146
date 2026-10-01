# Báo cáo rà soát logic nghiệp vụ — EV Care MVP

| Mục | Giá trị |
|---|---|
| Thời điểm lập | **30/09/2026 11:02 (GMT+7, Asia/Ho_Chi_Minh)** |
| Người lập | Claude Code (theo yêu cầu của Lê Đức Tùng) |
| Nhánh | `develop` (commit gốc `baf049a`) |
| Phạm vi | PRD v3.6 ↔ `docs/specs/**` (FF, API, Entity, Agent) ↔ một phần code `backend/src`, `frontend/src` |
| Báo cáo đi kèm | [Các phần chưa xử lý](2026-09-30_1102_bao-cao-phan-chua-xu-ly.md) |

**Mức độ:** 🔴 Cao — sai nghiệp vụ, mâu thuẫn Acceptance Criteria, hoặc gây sai dữ liệu · 🟠 Trung bình — mâu thuẫn giữa tài liệu, dễ làm FE/BE hiểu khác nhau · 🟢 Thấp — tài liệu lỗi thời / trình bày.

> Theo [INSTRUCTION.MD §8](../specs/INSTRUCTION.MD), báo cáo **không tự sửa logic** ở tài liệu gốc. Các điểm dưới đây cần owner xác nhận rồi cập nhật tài liệu. Riêng các tài liệu mới tạo hôm nay (us-045/049/053/057) đã áp dụng hướng đề xuất và đánh dấu `[Đề xuất]`.

---

## 1. Tóm tắt

| Mức | Số lượng | Mã |
|---|---:|---|
| 🔴 Cao | 7 | L-01 → L-07 |
| 🟠 Trung bình | 11 | L-08 → L-17, L-22 |
| 🟢 Thấp | 4 | L-18 → L-21 |
| ✅ Đã xử lý trong lần này | 1 | L-23 |

Ba vấn đề cần chốt sớm nhất (ảnh hưởng Demo 1–2):

1. **Vòng đời booking `pending` trong PRD đã lỗi thời** so với quyết định mới của us-029 (L-01, L-02) và tạo ra một tình huống chủ xe bị "kẹt" không huỷ được (L-03).
2. **Booking không lưu mốc bảo dưỡng** (L-04) và **dòng báo giá không có cờ bảo hành** (L-06) ⇒ Ticket, nhắc mốc, báo giá và dự toán không nhất quán với nhau.
3. **AC-F7-01 mâu thuẫn với quy tắc "nhắc trước 2 ngày"** của chính PRD v3.6 (L-07) ⇒ không thể nghiệm thu F7 như đang viết.

---

## 2. 🔴 Mức cao

### L-01 — PRD vẫn quy định booking `pending` hết hạn giữ chỗ thì tự huỷ

| | |
|---|---|
| Bằng chứng | PRD `docs/product/PRD_EV_Care_MVP.md:228` ("Hết hạn → `cancelled` (EF-001)"), `:234` (AC-F6-03); `core.entity.md:196-200` (EF-001) ⟷ `us-029 FF` BR-007, BR-010, BR-014, BR-015 và `booking.entity.md` BR-ENT-402 v1.2 |
| Mâu thuẫn | us-029 (quyết định AI-Q-401/402) đổi nghĩa `hold_expires_at` thành **cửa sổ 10' để chủ xe tự huỷ**; hết cửa sổ thì booking **vẫn `pending`** chờ xưởng (`manual`), chỉ tự huỷ sau 12h hoặc tới giờ hẹn. PRD và core vẫn nói hết hạn là huỷ. |
| Tác động | AC-F6-03 không còn kiểm thử được theo nghĩa cũ; QA/BE đọc PRD sẽ làm job huỷ sai. |
| Đề xuất | PRD v3.7: viết lại F6 "Giữ chỗ" và AC-F6-03 theo us-029 (chế độ `auto`/`manual`, cửa sổ huỷ 10', hạn chót xưởng 12h); cập nhật core EF-001. |
| Owner | PO |

### L-02 — PRD F8 không có bước xưởng chấp nhận / từ chối giữ chỗ

| | |
|---|---|
| Bằng chứng | PRD `:262` — state machine chỉ `confirmed → checked_in → in_progress → completed` ⟷ `us-037 FF` BR-802, BR-803, BR-804, BR-811 (chấp nhận/từ chối `pending`, đổi chế độ `auto`/`manual`) |
| Tác động | Phạm vi F8 trong PRD nhỏ hơn thực tế đặc tả; ước lượng M5 thiếu việc. |
| Đề xuất | PRD v3.7 bổ sung vào F8: xử lý yêu cầu giữ chỗ, chế độ xác nhận của xưởng, lý do từ chối/huỷ, no-show. |
| Owner | PO |

### L-03 — Chủ xe không huỷ được yêu cầu `pending` sau 10 phút

| | |
|---|---|
| Bằng chứng | `us-029 FF` BR-010 ("Sau `hold_expires_at`… chủ xe **không** tự thay đổi/huỷ được"), BR-015 (tự huỷ sau 12h); `us-029 API` `API-BK-04` trả `409 HOLD_WINDOW_CLOSED`; `us-033` `API-BR-03` chỉ huỷ `confirmed` |
| Mâu thuẫn | PRD F6b `:239` "Huỷ → giải phóng chỗ ngay"; mục tiêu G5 "cho phép huỷ/đổi sớm để giải phóng slot"; us-029 BR-013 chỉ cho 1 booking mở/xe. |
| Tác động | Ở xưởng `manual`, chủ xe đổi ý sau 10' thì **bị kẹt tới 12h**: không huỷ được, không đặt được xưởng khác (BR-013), slot của xưởng vẫn bị chiếm. |
| Đề xuất | Cho chủ xe huỷ `pending` **bất kỳ lúc nào trước khi xưởng quyết định** (mở rộng `API-BK-04` hoặc `API-BR-03`, lý do `OWNER_CANCELLED_REQUEST`). Đã nêu thành Q-1208 trong us-053. |
| Owner | PO + Backend |

### L-04 — Booking không lưu mốc bảo dưỡng (`milestoneRef` bị bỏ)

| | |
|---|---|
| Bằng chứng | `us-029 API` §5.2–5.3 nhận `milestoneRef`; `booking.entity.md` §5 không có cột mốc; model `backend/src/common/core/maintenance/booking.py` cũng không có |
| Tác động | (1) Ticket không biết hạng mục khi đặt không kèm báo giá (PRD F6b yêu cầu "hạng mục"); (2) PRD F7 "dừng nhắc khi **mốc** đã có booking" chỉ làm được ở mức "xe có booking" (us-021); (3) không truy vết được booking phục vụ mốc nào khi hoàn tất. |
| Đề xuất | Thêm `booking.odo_milestone integer NULL` và lưu `milestoneRef` khi tạo — đã đặc tả ở [us-053 Entity §3](../specs/sprint-3/entity/us-053-sprint-3-spec.entity.md). |
| Owner | Backend |

### L-05 — Agent báo giá nhận danh sách dòng + giá từ trạng thái LLM

| | |
|---|---|
| Bằng chứng | `ai-005` §10.1 TOOL-501 `create_draft_quote(…, items[])`, §10.2 "items[] lấy nguyên từ `estimate.items`" |
| Mâu thuẫn | PRD §7 "Deterministic rules" và F5 "LLM không tự cộng hay sửa số". Khi `items[]` đi qua tham số tool do LLM sinh, LLM có thể làm sai/bịa giá mà backend không phát hiện. |
| Đề xuất | TOOL-501 chỉ nhận `(user_vehicle_id, workshop_id, odo_milestone)`; backend tự tính lại dự toán và snapshot — đã quy định ở [us-049 BR-1101](../specs/sprint-3/feature-functional/us-049-sprint-3-spec.ff.md), cần sửa AI-005 theo. |
| Owner | AI Team |

### L-06 — `quote_item` không phân biệt dòng bảo hành với dòng tính phí

| | |
|---|---|
| Bằng chứng | `quote_item.entity.md` §5 (không có cờ bảo hành); `quote.entity.md` BR-ENT-414 `estimated_total = Σ estimated_price` ⟷ PRD F5 "tổng = tổng các mục tính phí", AI-003 `chargeable_total` |
| Tác động | Nếu dòng bảo hành được ghi với giá tham khảo thì tổng báo giá ≠ tổng dự toán (vi phạm AC-F5-01 khi đi từ F5 sang F5b); nếu ghi giá 0 thì không phân biệt được "miễn phí bảo hành" với "xưởng cho giá 0". Chủ xưởng có thể vô tình tính phí dòng bảo hành. |
| Đề xuất | Thêm `quote_item.is_covered_by_warranty`, `price_source` (snapshot từ F5), khoá giá 0 cho dòng bảo hành — đã đặc tả ở [us-049 Entity](../specs/sprint-3/entity/us-049-sprint-3-spec.entity.md). |
| Owner | Backend + PO (Q-1103) |

### L-07 — AC-F7-01 mâu thuẫn với "nhắc trước ngày đến hạn 2 ngày"

| | |
|---|---|
| Bằng chứng | PRD `:256` AC-F7-01 "**Mọi** xe `DUE_SOON` chưa có booking nhận nhắc trong lần chạy job kế tiếp" ⟷ PRD `:245` (v3.6) "mặc định nhắc trước ngày đến hạn 2 ngày"; `us-017` `DUE_SOON` = còn ≤ 14 ngày; `us-021 FF` BR (`remaining_days ≤ reminder_lead_days`) |
| Tác động | Xe còn 10 ngày là `DUE_SOON` nhưng theo us-021 chỉ được nhắc khi còn ≤ 2 ngày (hoặc ≤ 500 km) ⇒ AC-F7-01 luôn trượt với cấu hình mặc định. |
| Đề xuất | Viết lại AC-F7-01: "Xe chưa có booking thoả điều kiện nhắc của us-021 (còn ≤ `lead_days` ngày, hoặc ≤ `DUE_SOON_KM`, hoặc quá hạn) nhận nhắc trong lần chạy job kế tiếp, không quá 1 lần/tuần." |
| Owner | PO |

---

## 3. 🟠 Mức trung bình

### L-08 — us-029 mâu thuẫn nội bộ sau khi đổi quyết định giữ chỗ

| Vị trí | Nội dung sai | Nên là |
|---|---|---|
| `us-029 FF:435` BR-001 | "ghi booking `confirmed`" trong thao tác nguyên tử | "ghi booking `pending` (giữ chỗ)" |
| `us-029 FF:423` EF-005 | "job giữ chỗ sẽ thu hồi khi hết hạn" | Không có job thu hồi theo `hold_expires_at`; chỉ job BR-015 |
| `us-029 API:380` | "`holdExpiresAt` hết hạn ⇒ hold huỷ (BR-010)" | "hết hạn ⇒ chủ xe hết quyền tự huỷ" |
| `us-029 API:318, 363, 550` | `bookingId: "bk_20261004_0012"` | `uuid` (entity ENT-402) |
| `us-029 API` §8.2 | Mã lỗi `HOLD_EXPIRED` dùng cho "token thẻ hết hạn" | `CONFIRMATION_TOKEN_EXPIRED` (tránh nhầm với cửa sổ giữ chỗ) |

Owner: Backend (tài liệu us-029).

### L-09 — Hạn chót xưởng xác nhận ghi hai kiểu

`us-029 FF:528` BR-015 vẫn ghi "`[Đề xuất]` mặc định: trước giờ hẹn, hoặc cấu hình theo giờ", trong khi cùng tài liệu `:885` Q-404 đã **Resolved** "12 giờ kể từ khi giữ chỗ và không muộn hơn giờ hẹn", và `booking.entity.md:181` theo Q-404. ⇒ Sửa BR-015 theo Q-404.

### L-10 — `booking_code`: ba định dạng, hai đường dẫn QR, một quy tắc sinh mã chưa ghi

| Nguồn | Định dạng / quy tắc |
|---|---|
| `booking.entity.md` §3 | `BK-20261003-0012`; cột `NOT NULL` |
| `us-029 API`, `us-033 API` | `EVC-7K2M`; "phát hành mã khi `confirmed`" |
| Code `booking/service.py` `_new_booking_code()` | `EVC-` + 8 hex (docstring lại ghi ví dụ `EVC-7K2M9Q`); **sinh ngay khi tạo `pending`**, chỉ trả khi `confirmed` |
| QR | Code: `/api/v1/bookings/qr/{code}.png` (theo mã, không kiểm chủ sở hữu) ⟷ us-033 và us-053: `/api/v1/bookings/{bookingId}/qr` |

Đề xuất: giữ cách của code (sinh khi tạo, chỉ lộ khi `confirmed` — không cần đổi schema), chốt một định dạng (Q-1204), đổi endpoint QR của code theo spec. Đã ghi ở [us-053 BR-1203](../specs/sprint-3/feature-functional/us-053-sprint-3-spec.ff.md) và [us-053 API §9](../specs/sprint-3/api/us-053-sprint-3-spec.api.md).

### L-11 — AI-004 chưa đồng bộ với quyết định của us-029

- `ai-004` §29: AI-Q-401/402/403 vẫn **Open**, và đề xuất của AI-Q-402 ("giữ chỗ khi hiển thị thẻ, TTL 10'") **trái** với quyết định đã áp dụng ở us-029 BR-007 ("chỉ giữ chỗ khi bấm Xác nhận").
- `ai-004` §10.1 TOOL-406 `reschedule_booking` trả "booking mới" — us-053 quy định đổi lịch **tại chỗ**, giữ nguyên `booking_id`, mã và QR.

Đề xuất: đóng 3 câu hỏi theo us-029, sửa output TOOL-406. Owner: AI Team.

### L-12 — Dữ liệu bảo hành không đủ để xác định "xe hết bảo hành"

`vehicle_warranty.component ∈ {battery, motor, chassis, electronics}` (us-001 entity ENT-004) và `maintenance_rule.is_covered_by_warranty` không gắn component nào. PRD F7 ("Xe hết bảo hành → bỏ nội dung cảnh báo bảo hành") và F5 (tách miễn phí/tính phí) đều cần khái niệm "còn bảo hành" nhưng không có quy tắc. AI-Q-302 vẫn Open.
Đề xuất tạm: dùng component `chassis`; phase sau thêm `maintenance_rule.warranty_component` (us-045 Q-1001). Owner: PO.

### L-13 — `service_progress.updated_by` không lưu được người cập nhật

`service_progress.entity.md` giữ `updated_by integer` (Q-403 **Resolved** "giữ nguyên, không FK"), nhưng người cập nhật trong MVP là chủ xưởng có `workshop_owner.id` kiểu `uuid`, hoặc hệ thống ⇒ cột luôn phải để `NULL`, mất truy vết. Đề xuất mở lại Q-403, thêm `actor_type`, `actor_workshop_owner_id` như `booking_status_event` — [us-057 Entity](../specs/sprint-4/entity/us-057-sprint-4-spec.entity.md).

### L-14 — Onboarding còn dropdown chọn model, trái PRD F1

PRD `:147` "hãng xác thực và trả về model… **Không có dropdown chọn model**" ⟷ `us-001 API` `API-004 GET /onboarding/vehicle-models` "Danh sách mẫu xe cho dropdown", `us-001 FF` trường `vehicle_model` "User input". Cần chọn một: bỏ API-004/field hoặc sửa PRD. Owner: PO.

### L-15 — `booking.estimated_cost` khi không có báo giá chưa rõ công thức

`booking.entity.md` §6: "lấy tổng `maintenance_rule.estimated_cost` / `service_price.price` của mốc hoặc để `NULL`" — không nói có loại dòng bảo hành không, ưu tiên nguồn giá nào. Đề xuất: `estimated_cost = chargeable_total` của F5 (us-045 BR-1001) cho đúng xưởng + mốc tại thời điểm đặt.

### L-16 — Chưa có ràng buộc DB chống chồng lấn hiệu lực giá

`service_price` BR-ENT-412 chỉ kiểm ở service ⇒ dữ liệu seed/nhập tay có thể ra hai giá cho một hạng mục, dự toán không tất định. Đề xuất exclusion constraint (`btree_gist`) — us-045 Entity Q-ENT-1002.

### L-17 — Màn mock duyệt báo giá cho phép thao tác trái quy tắc

`frontend/src/features/quotes/pages/QuoteReview.tsx` cho chủ xưởng **thêm/xoá dịch vụ** và ghi nhãn "Ghi chú **kỹ thuật viên**" ⟷ `quote_item.entity.md` BR-ENT-417 (chỉ sửa dòng khi `draft`; người duyệt chỉ đặt `approved_price`), `quote.entity.md` Q-411 (người duyệt là **chủ xưởng**). Khi nối API cần làm theo [us-049 FE §3.2](../specs/sprint-3/frontend/us-049-sprint-3-spec.fe.md).

### L-22 — Route hội thoại chưa có xác thực trong khi pilot có người thử thật

`backend/src/modules/conversation/route.py` không có dependency xác thực (đã biết, chủ động cho dev) ⟷ `us-025 API` §2 yêu cầu `require_active_vehicle_owner`; PRD §8 "Mọi API xác minh Firebase ID token"; AC-F4-05 (đọc hội thoại người khác phải bị từ chối). PRD §11 M7 cho người thử dùng từ 26/10 ⇒ phải gắn auth **trước khi deploy staging**, không chỉ trước prod.

---

## 4. 🟢 Mức thấp — PRD lỗi thời / trình bày

| Mã | Vị trí | Vấn đề | Đề xuất |
|---|---|---|---|
| L-18 | PRD `:16`, `:189`, §15 | Bảng thông tin ghi **v3.5** nhưng change log đã có v3.6; F4 vẫn nói "cần một entity spec mới" (đã có ENT-421…423); §15 Truy vết thiếu us-021/025/029/033/037/041 và các spec mới | Nâng v3.7, cập nhật §0, F4, §15 |
| L-19 | PRD `:134`, `:483` | Danh sách **Out of scope** chứa cụm "khung cài đặt kênh và số ngày nhắc trước đã có (v3.6)" (là phạm vi **trong** MVP); Phụ lục B NOTI-01 vẫn ghi "không có màn cài đặt" | Chuyển cụm đó khỏi Out of scope; sửa cột "Hiện trạng MVP" của NOTI-01 |
| L-20 | PRD `:322` | Frontend ghi **Next.js**; thực tế `frontend/package.json` là **Vite + React 19 + React Router 7** | Sửa §9 |
| L-21 | `backend/src/config.py` | Mặc định `llm_provider = "openai"`, `embedding_provider = "openai"` (`text-embedding-3-small`) ⟷ PRD §9: Gemini Flash-tier, `bge-m3` | Đặt mặc định theo PRD hoặc ghi rõ lựa chọn trong Tech Spec (xem báo cáo chưa xử lý U-01) |

---

## 5. ✅ Đã xử lý trong lần này

| Mã | Vấn đề | Xử lý |
|---|---|---|
| L-23 | AI-002, AI-008 ghi "FF F4 `[Chưa có]`" dù us-025 đã có; AI-003/004/005 ghi FF F5/F6/F6b/F5b "[Chưa có]"; us-029/us-033 trỏ "F6b — tài liệu riêng" | Đã cập nhật link tới us-025, us-029, us-045, us-049, us-053 (chỉ sửa link, không đổi logic) |

---

## 6. Những điểm đã kiểm tra và **nhất quán**

- Công thức sức chứa `total_technicians − emergency_slots_reserved − blocked − occupied`, tập trạng thái chiếm chỗ `pending | confirmed | checked_in | in_progress`: PRD F6 = us-029 BR-005 = us-037 BR-809.
- Ngưỡng `DUE_SOON` 500 km / 14 ngày, cấu hình qua `.env`: PRD F3 = us-017.
- ODO chỉ đến từ hãng (job + webhook), không nhập tay: PRD F3 = us-017.
- Hỏi thăm 12h sau `completed`, tối đa 1 lần/booking: PRD F9 = us-037 BR-807 = us-041.
- Nội dung Discord không chứa VIN/SĐT/CCCD, biển số che: PRD F7 = us-021 = us-033 BR-706.
- "Một service dùng chung cho Agent và UI": PRD F6 = us-029 BR-011; áp dụng tương tự cho F5 (us-045) và F5b (us-049).
- Người duyệt báo giá là chủ xưởng; báo giá có `expires_at`; đặt lịch không bắt buộc báo giá: PRD F5b = quote.entity Q-410/Q-411 = us-029 AF-004.

---

## 7. Đề xuất hành động

| Ưu tiên | Việc | Mã | Hạn gợi ý |
|---|---|---|---|
| 1 | PO chốt: huỷ `pending` sau 10' (L-03), viết lại AC-F6-03 (L-01) và AC-F7-01 (L-07); nâng PRD v3.7 (L-01, L-02, L-18 → L-20) | L-01, L-02, L-03, L-07 | 04/10 (M3) |
| 2 | Backend: thêm `booking.odo_milestone`; mở rộng `quote_item`; sửa tài liệu us-029 | L-04, L-06, L-08, L-09 | trước M5 (12/10) |
| 3 | AI Team: sửa AI-005 TOOL-501, AI-004 câu hỏi mở + TOOL-406 | L-05, L-11 | trước M5 |
| 4 | Chốt định dạng mã + endpoint QR; `service_progress` actor | L-10, L-13 | trước M5 |
| 5 | Gắn auth route hội thoại trước staging | L-22 | trước M7 (26/10) |
| 6 | PO: bảo hành theo component, dropdown model | L-12, L-14 | 04/10 |
