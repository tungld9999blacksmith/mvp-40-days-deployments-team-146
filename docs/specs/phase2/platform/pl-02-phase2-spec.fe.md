# Frontend Technical Specification — Chuyển sang người thật

> Frontend cho Feature `FEAT-P2-PL02` (SCR-PL02-01, SCR-PL02-02).
>
> **Nguồn nghiệp vụ:** [Functional Spec](pl-02-phase2-spec.ff.md). **API:** [API Spec](pl-02-phase2-spec.api.md) (`API-PL02-01..05`, thẻ `HANDOFF_STATUS`).
>
> **Nguyên tắc:** đây là **nhãn xử lý**, không phải phiếu hỗ trợ: không có màn "phiếu", không bình luận qua lại, không SLA hiển thị (BR-PL02-03).

---

## 1. Document Information

| Field | Value |
|---|---|
| Document ID | `FE-SPEC-P2-PL02` |
| Version | `v0.1` |
| Status | `Draft` |
| Screens | SCR-PL02-01 (thẻ chat + mục Thông báo chủ xe), SCR-PL02-02 (hàng "Cần liên hệ khách" trên Workshop Portal) |
| Routes | `/technician/handoffs` (mới, chủ xưởng) |
| Feature folder | `frontend/src/features/handoff/` (mới) |
| Created Date | `2026-10-12` |

---

# 2. Components

## 2.1 Chủ xe — yêu cầu và trạng thái (SCR-PL02-01)

| Chỗ | Hành vi |
|---|---|
| Chat | Chip "Gặp người của xưởng" luôn có trong menu "…" của composer; agent đề nghị (NO_SOURCE / FRUSTRATION) bằng chip cùng nhãn. Bấm ⇒ xác nhận ngắn "Chuyển cuộc trò chuyện cho xưởng {tên}? Xưởng sẽ liên hệ bạn." ⇒ `API-PL02-01` |
| Thẻ `HANDOFF_STATUS` | Tiến trình 4 bước: "Đã chuyển" → "Xưởng đã xem" → "Đã liên hệ" → "Đã xong" (bước hiện tại đậm + chữ, không chỉ màu); tên xưởng + hotline (dạng chữ chọn được + nút "Gọi"); "Huỷ yêu cầu" khi backend cho |
| `URGENT` | Thẻ có badge "Khẩn" và đặt dưới thẻ an toàn (AD-02) |
| Thông báo | Loại `HANDOFF_STATUS_CHANGED` trong `/notifications`; bấm mở hội thoại tại thẻ |

## 2.2 Chủ xưởng — "Cần liên hệ khách" (SCR-PL02-02)

Route `/technician/handoffs`; thẻ đếm trên `TechnicianDashboard` ("Cần liên hệ khách · {n}"); nhãn `needsContact` trên thẻ lịch ở `WorkshopBoard` (chip cảnh báo "Cần liên hệ khách" mở chi tiết).

| Vùng | Nội dung |
|---|---|
| Danh sách | `URGENT` trước; mỗi dòng: lý do (chữ), tóm tắt `issue` (2 dòng), xe (`PlateTile` che), lịch liên quan, "{giờ} trước", trạng thái |
| Chi tiết (drawer) | Bốn khối tóm tắt: Vấn đề · Xe · Lịch liên quan · Trợ lý đã trả lời; trích "Khách nói" nguyên văn; tên + SĐT khách theo quyền Board (nút "Gọi") |
| Hành động | "Đã liên hệ" (primary), "Đã xong" (secondary, ô ghi chú ngắn tuỳ chọn ≤ 300 ký tự, chỉ xưởng thấy) |

Mở drawer lần đầu ⇒ backend tự chuyển `seen`; UI cập nhật nhãn.

---

# 3. API Integration & Errors

`features/handoff/api.ts`: `requestHandoff`, `listMyHandoffs`, `cancelHandoff`, `listWorkshopHandoffs`, `updateHandoffStatus`.

| Lỗi | Xử lý |
|---|---|
| `HANDOFF_IN_PROGRESS` | Ẩn nút huỷ, toast "Xưởng đang liên hệ bạn" |
| `INVALID_STATUS_TRANSITION` | Tải lại |
| Tạo khi đã có yêu cầu mở | Backend trả yêu cầu cũ ⇒ hiện thẻ đó, toast "Bạn đã có yêu cầu đang xử lý" |

---

# 4. Acceptance Criteria (FE)

1. Không có màn / từ "phiếu hỗ trợ" trong UI.
2. Chủ xe không bao giờ thấy ghi chú nội bộ của xưởng.
3. Tiến trình trạng thái đọc được bằng trình đọc màn hình.
4. Hai theme, 390 px; `npm test`, `npx tsc --noEmit -p .` qua.

---

# 5. Tests (Vitest)

| File | What | Count |
|---|---|---|
| `handoff/statusSteps.test.ts` | `handoffSteps(status, timeline)` cho 5 trạng thái | +5 |
| `handoff/workshopList.test.ts` | Sắp `URGENT` trước, cũ nhất trước | +2 |
| `handoff/HandoffStatusCard.test.tsx` | `renderToStaticMarkup`: không có "phiếu"; hotline dạng chữ | +1 |

---

# 6. Truy vết FF → FE

| FF | FE |
|---|---|
| UC-PL02-01, SCR-PL02-01, BR-PL02-04, AF-PL02-01 | §2.1 |
| UC-PL02-03, SCR-PL02-02, BR-PL02-02, 03 | §2.2 |
| EF-PL02-02 | §2.1 (`URGENT`) |

---

# 7. Analytics

`handoff_requested` (`reason`, `entry`), `handoff_cancelled`, `ws_handoff_opened` (`ageMinutes`), `ws_handoff_status` (`status`).

---

# 8. Change Log

| Version | Date | Change |
|---|---|---|
| `v0.1` | `2026-10-12` | Bản nháp đầu |
