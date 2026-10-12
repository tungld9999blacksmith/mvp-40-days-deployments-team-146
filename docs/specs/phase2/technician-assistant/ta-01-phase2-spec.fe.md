# Frontend Technical Specification — Trợ lý tra cứu và nhắc việc cho kỹ thuật viên

> Frontend cho Feature `FEAT-P2-TA01` (SCR-TA01-01..03).
>
> **Nguồn nghiệp vụ:** [Functional Spec](ta-01-phase2-spec.ff.md). **API:** [API Spec](ta-01-phase2-spec.api.md) (`API-TA01-01..05`, thẻ `VEHICLE_BRIEF`).
>
> **Tái dùng:** khung chat của `features/assistant` (danh sách tin, composer, SSE parser `sse.ts`, `CardShell` CH-02) — tách thành component dùng chung, tham số hoá transport. Không dùng `RobotAvatar` của chủ xe cho trợ lý xưởng (mascot là gương mặt trợ lý chủ xe, DESIGN.md); trợ lý xưởng dùng icon `Wrench` trong vòng `bg-emerald-dim`.

---

## 1. Document Information

| Field | Value |
|---|---|
| Document ID | `FE-SPEC-P2-TA01` |
| Version | `v0.1` |
| Status | `Draft` |
| Screens | SCR-TA01-01 (panel / trang trợ lý xưởng), SCR-TA01-02 (thẻ tóm tắt xe), SCR-TA01-03 (thông báo nhắc) |
| Routes | `/ktv/assistant` (KTV), `/technician/assistant` (chủ xưởng, prefix hiện tại) |
| Feature folder | `frontend/src/features/workshop-assistant/` (mới), `frontend/src/shared/chat/` (mới: phần dùng chung tách từ `features/assistant`) |
| Created Date | `2026-10-12` |

---

# 2. Components

## 2.1 Tách phần chat dùng chung

`shared/chat/`: `MessageListView`, `ComposerView`, `useSseTurn(transport)`, `CardShell`. `features/assistant` (chủ xe) và `features/workshop-assistant` cùng dùng; mỗi bên có transport riêng (`/conversations/*` vs `/workshop/assistant/*`). Việc tách không đổi hành vi chat chủ xe (test hồi quy `chatReducer` có sẵn phải qua).

## 2.2 Trợ lý xưởng (SCR-TA01-01)

| Nơi | Dạng |
|---|---|
| App KTV | Trang `/ktv/assistant` (full màn trên 390 px); nút nổi "Hỏi trợ lý" ở `/ktv` và `/ktv/jobs/:id` (khi có `USE_ASSISTANT`) |
| Workshop Portal chủ xưởng | Panel trượt phải (`xl`: rail 1/3, < `xl`: drawer) mở từ topbar; trang `/technician/assistant` cho màn nhỏ |

Nội dung: tiêu đề "Trợ lý xưởng"; chip mở đầu (`API-TA01-05`) dạng `ChipRow` (CH-01 component, chế độ "gửi câu"); danh sách tin; composer (≤ 1.000 ký tự). Thread: mở thread gần nhất trong ngày, nút "Cuộc trò chuyện mới".

## 2.3 Thẻ `VEHICLE_BRIEF` (SCR-TA01-02)

| Vùng | Nội dung |
|---|---|
| Đầu | `PlateTile` biển số, model, "Khách {tên rút gọn}", giờ hẹn (`font-mono`), KTV |
| Số liệu | ODO (`font-mono`) + "tính đến {ngày}", mốc + hạng mục |
| Khách mô tả | Khối trích dẫn nguyên văn với nhãn "Khách mô tả" (BR-TA01-05) |
| Đã duyệt | Danh sách hạng mục (không giá với KTV) |
| Lần trước chưa làm | Danh sách + ngày đề xuất |
| Triệu hồi | "Không có" / danh sách / "Chưa có dữ liệu" |
| Thiếu dữ liệu | Dòng muted cho từng mục trong `missing` |
| Nút | "Cập nhật tiến độ" → `/ktv/jobs/{bookingId}` (KTV) hoặc Board (chủ xưởng) |

Các thẻ khác: `JOB_LIST` (danh sách lịch theo giờ, chạm mở việc), `SERVICE_HISTORY_LIST` (dùng hàng mục lịch sử HS-01 chế độ gọn).

## 2.4 Nhắc (SCR-TA01-03)

- Loại thông báo `TA_ARRIVAL` và `TA_STAGE_OVERDUE` trong mục Thông báo của KTV (app `/ktv`, chuông topbar với badge) và của chủ xưởng (`/technician/notifications`).
- Bấm `TA_ARRIVAL` ⇒ mở trợ lý với câu "Tóm tắt xe {HH:mm}" đã gửi sẵn (thẻ tóm tắt hiện ngay); `TA_STAGE_OVERDUE` ⇒ `/ktv/jobs/{id}`.
- Web Push: hỏi quyền thông báo trình duyệt **một lần** trên `/ktv` sau lần đăng nhập đầu (nút "Bật thông báo"), không hỏi tự động khi tải trang.

---

# 3. API Integration & Errors

`features/workshop-assistant/transport.ts`: `createThread`, `listThreads`, `listMessages`, `sendMessage` (SSE), `getChips`.

| Lỗi | Xử lý |
|---|---|
| `ASSISTANT_BUSY` | Toast "Trợ lý đang trả lời" |
| `RATE_LIMITED` | Đếm ngược như chat chủ xe |
| `PERMISSION_DENIED` | Ẩn nút trợ lý |
| SSE đứt | Cơ chế resume / lấy lại tin của `sse.ts` |

---

# 4. States

| State | UI |
|---|---|
| Đang trả lời | Bong bóng trợ lý với chỉ báo đang gõ (không dùng mascot) |
| Không có thread | Màn chào + chip |
| 390 px | Composer dính đáy, chip cuộn ngang |

---

# 5. Acceptance Criteria (FE)

1. Chat chủ xe không đổi hành vi sau khi tách `shared/chat` (bộ test hiện có qua).
2. Thẻ tóm tắt không hiển thị giá khi người dùng là KTV.
3. Nhắc `TA_ARRIVAL` mở trợ lý với thẻ tóm tắt đúng lịch.
4. Không hỏi quyền thông báo trình duyệt khi chưa bấm "Bật thông báo".
5. Hai theme, 390 px; `npm test`, `npx tsc --noEmit -p .` qua; không thêm dependency.

---

# 6. Tests (Vitest)

| File | What | Count |
|---|---|---|
| `workshop-assistant/briefView.test.ts` | `vehicleBriefView(card, actorKind)` → mục `missing`, ẩn giá với KTV, nhãn "Khách mô tả" | +4 |
| `workshop-assistant/notificationRoute.test.ts` | Loại nhắc → route / câu gửi sẵn | +2 |
| `shared/chat/useSseTurn.test.ts` | Dùng chung cho hai transport (mock) | +2 |
| `assistant/state/chatReducer.test.ts` | Hồi quy sau khi tách | có sẵn |

---

# 7. Truy vết FF → FE

| FF | FE |
|---|---|
| SCR-TA01-01, UC-TA01-01..04, FF §3.1 chip | §2.2 |
| SCR-TA01-02, BR-TA01-05, BR-TA01-06 | §2.3 |
| SCR-TA01-03, UC-TA01-05 | §2.4 |

---

# 8. Analytics

`ws_assistant_opened` (`actor`, `entry`), `ws_assistant_chip_clicked` (`label`), `ws_assistant_card_action` (`type`), `ta_reminder_opened` (`kind`). Sự kiện PL-03 `technician_assistant_used` ghi ở backend.

---

# 9. Change Log

| Version | Date | Change |
|---|---|---|
| `v0.1` | `2026-10-12` | Bản nháp đầu |
