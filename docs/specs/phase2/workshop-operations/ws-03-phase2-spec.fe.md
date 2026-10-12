# Frontend Technical Specification — Tài khoản kỹ thuật viên và tự phân công

> Frontend cho Feature `FEAT-P2-WS03` (SCR-WS03-01..03).
>
> **Nguồn nghiệp vụ:** [Functional Spec](ws-03-phase2-spec.ff.md). **API:** [API Spec](ws-03-phase2-spec.api.md) (`API-WS03-01..12`).
>
> **PO chốt 2026-10-12:** có vai trò KTV thứ ba; tài khoản KTV do xưởng tạo (tên đăng nhập + mật khẩu), đổi mật khẩu lần đầu. DESIGN.md (mục *Roles*) cần cập nhật theo trước khi merge. Spec này đề xuất cách làm ít xáo trộn nhất (mục 2.1); tên route cuối cùng chờ **P2Q-01**.

---

## 1. Document Information

| Field | Value |
|---|---|
| Document ID | `FE-SPEC-P2-WS03` |
| Version | `v0.2` |
| Status | `Draft` |
| Screens | SCR-WS03-01 (trang chủ xưởng), SCR-WS03-02 (app KTV, mobile-first), SCR-WS03-03 (Board), SCR-WS03-04 (đăng nhập / đổi mật khẩu KTV) |
| Routes | Chủ xưởng: `/technician/staff` (theo prefix hiện tại); KTV: `/ktv`, `/ktv/login`, `/ktv/change-password`, `/ktv/jobs/:bookingId` (mới) |
| Feature folder | `frontend/src/features/technician-app/` (mới, app KTV), `features/workshop-board/` (sửa) |
| Created Date | `2026-10-12` |

---

# 2. Components

## 2.1 Đặt tên route và nhãn (P2Q-01)

| Bước | Việc | Ghi chú |
|---|---|---|
| R1 (cùng WS-03) | App KTV đặt dưới prefix **`/ktv/*`** — không đụng `/technician/*` đang là của chủ xưởng | Không phá bookmark / link thông báo của chủ xưởng |
| R2 (cùng WS-03) | Đổi **nhãn** giao diện chủ xưởng từ "Kỹ thuật viên" sang "Chủ xưởng" / "Xưởng" (FF §23) ở sidebar, tiêu đề, email | Chỉ đổi chữ, không đổi layout |
| R3 (khi P2Q-01 chốt đề xuất) | Chuyển route chủ xưởng `/technician/*` → `/workshop/*` (giữ redirect 301 phía client từ đường cũ, theo vai trò đăng nhập); khi đó `/technician/*` có thể thành alias của `/ktv/*` | Các spec Phase 2 khác ghi route chủ xưởng theo hiện trạng `/technician/*`; đổi 1:1 |

## 2.2 Quản lý KTV (SCR-WS03-01) — chủ xưởng

Route `/technician/staff`; mục mới "Nhân viên" trong sidebar Workshop Portal là thay đổi điều hướng ⇒ cần duyệt cùng DESIGN.md; trong lúc chờ, vào từ `TechnicianDashboard` (thẻ "Kỹ thuật viên của xưởng") và từ Board.

| Vùng | Nội dung |
|---|---|
| Danh sách | Hàng `divide-y`: tên, tên đăng nhập (`font-mono`), badge trạng thái (`Chưa kích hoạt` / `Đang làm` / `Đã vô hiệu`; `Mật khẩu tạm hết hạn` khi quá hạn), kỹ năng (chip), ngày làm (T2…CN), tải hôm nay "{n} xe · {phút}" |
| Hành động hàng | "Nghỉ hôm nay" (xác nhận ngắn: "Các xe của {tên} hôm nay sẽ được phân lại"), "Sửa", "Đặt lại mật khẩu" (`alertdialog`: "{tên} sẽ bị đăng xuất và phải đổi mật khẩu khi đăng nhập lại"), "Vô hiệu" (danger, `alertdialog`) / "Bật lại" |
| Nút "Tạo tài khoản KTV" | `CreateTechnicianDialog`: tên đăng nhập (điền sẵn tiền tố slug xưởng, ví dụ `xuongminhphat.`), tên gọi, mật khẩu tạm (mặc định "Tạo tự động"; tuỳ chọn tự nhập), kỹ năng (checkbox theo nhóm), ngày làm, quyền (checkbox: Xem toàn bộ lịch xưởng, Check-in và đánh dấu lỡ hẹn) — các quyền mặc định bật hiện dạng chữ, không cho tắt `VIEW_ASSIGNED` |
| Sau tạo / đặt lại | `TemporaryPasswordPanel`: tên đăng nhập + mật khẩu tạm (`font-mono`), nút "Sao chép", câu "Mật khẩu chỉ hiện một lần. Hãy đưa trực tiếp cho KTV; KTV sẽ phải đổi khi đăng nhập lần đầu. Hết hạn sau 7 ngày." Đóng panel ⇒ không xem lại được |
| Kết quả nghỉ đột xuất | Toast tóm tắt "Đã phân lại 3 xe · 1 xe chưa có người · 1 xe đã chuyển phương án cho khách" + link Board lọc các xe đó |
| Cài đặt | Trong `BookingSettingsPage`: công tắc "Tính sức chứa theo số KTV đang làm" (`technicianCapacityEnabled`) + câu "Chưa có KTV nào đang làm thì vẫn dùng số thợ đã khai" |

## 2.3 Board (SCR-WS03-03)

`WorkshopBoard` / `BoardBookingDetail`:
- Mỗi lịch hiện tên KTV (avatar chữ cái + tên) hoặc badge "Chưa phân công" (màu cảnh báo + chữ).
- "Đổi KTV": select KTV làm ngày đó (hiện tải, cảnh báo thiếu kỹ năng) ⇒ `API-WS03-07`. Kéo thả **không** làm ở v0.1 (FF cho phép "kéo thả hoặc chọn"; chọn đủ dùng, kéo thả cần thư viện).
- Bộ lọc "Theo KTV".

## 2.4 App KTV (SCR-WS03-02)

Layout riêng `TechnicianAppLayout` (mobile-first, không sidebar 240 px): topbar 56 px với logo `variant="mark"`, tên KTV, menu (Đổi mật khẩu, Đăng xuất). Cùng token màu, font, bo góc của DESIGN.md.

| Route | Màn |
|---|---|
| `/ktv/login` | Ô "Tên đăng nhập", ô "Mật khẩu" (nút hiện / ẩn), nút "Đăng nhập" ⇒ Firebase `signInWithEmailAndPassword(toTechnicianEmail(username), password)` ⇒ `API-WS03-08`. Link "Quên mật khẩu?" ⇒ dòng chữ "Liên hệ chủ xưởng để đặt lại mật khẩu" (không có luồng email). Không có nút Google |
| `/ktv/change-password` | Bắt buộc khi `mustChangePassword` (guard chuyển hướng mọi route `/ktv/*` về đây): mật khẩu mới + nhập lại, gợi ý quy tắc (≥ 8 ký tự, có chữ và số); gửi `API-WS03-13` rồi đăng nhập lại bằng mật khẩu mới. KTV `active` vào từ menu "Đổi mật khẩu" |
| `/ktv` | **Việc của tôi**: chọn ngày (hôm nay mặc định, `DayStrip`), danh sách theo giờ: giờ bắt đầu–kết thúc (`font-mono`), `PlateTile` biển số che, model, hạng mục, badge tiến độ; nút "Cập nhật tiến độ" và "Phát sinh" (AD-04, khi có quyền); nút trợ lý (TA-01, khi có quyền) |
| `/ktv/jobs/:bookingId` | Chi tiết việc: hạng mục (không giá), ghi chú, tóm tắt lịch sử; stepper tiến độ 6 bước (tái dùng component tiến độ của Board, chế độ KTV) |

- Bị vô hiệu giữa phiên (`401 TECHNICIAN_INACTIVE`) ⇒ đăng xuất + màn "Tài khoản đã bị tắt".
- `403 PERMISSION_DENIED` ⇒ ẩn nút tương ứng (frontend cũng ẩn trước theo `permissions` của `/technician/me`; backend vẫn là cổng).
- Hiệu năng (FF §18): route `/ktv` lazy chunk riêng, không tải code app chủ xe / Board; danh sách ≤ 1 request.

---

# 3. API Integration & Errors

`features/technician-app/api.ts`: `createSession`, `changePassword`, `getMe`, `listJobs`, `getJob`, `updateProgress`; `features/workshop-board/api.ts`: `listTechnicians`, `createTechnician`, `updateTechnician`, `resetTechnicianPassword`, `disableTechnician`, `enableTechnician`, `addAbsence`, `removeAbsence`, `assignBooking`.

| Lỗi | Xử lý |
|---|---|
| `USERNAME_TAKEN` | Dưới ô tên đăng nhập: "Tên này đã có người dùng" + chip gợi ý từ `details.suggestions` |
| Firebase `auth/invalid-credential` | "Tên đăng nhập hoặc mật khẩu không đúng" (không nói trường nào sai) |
| Firebase `auth/too-many-requests` | "Bạn nhập sai nhiều lần. Thử lại sau ít phút hoặc nhờ chủ xưởng đặt lại mật khẩu." |
| `TEMP_PASSWORD_EXPIRED` | "Mật khẩu tạm đã hết hạn, nhờ chủ xưởng đặt lại." |
| `WEAK_PASSWORD` | Dưới ô mật khẩu mới, theo quy tắc |
| `REAUTH_REQUIRED` | Đăng xuất, về `/ktv/login` với câu "Đăng nhập lại để đổi mật khẩu" |
| `403 PASSWORD_CHANGE_REQUIRED` | Chuyển `/ktv/change-password` |
| `TECHNICIAN_UNAVAILABLE` | Trong select: "KTV không làm ngày này" / "Trùng giờ với xe khác" |
| `MISSING_SKILL` (warning) | Hộp xác nhận "KTV chưa có kỹ năng {nhóm}. Vẫn giao?" |
| `401 TECHNICIAN_INACTIVE` | §2.4 |

---

# 4. States

| State | UI |
|---|---|
| KTV không có việc ngày đó | "Hôm nay bạn chưa được giao xe nào." |
| Đang tải danh sách | Skeleton 3 thẻ |
| 390 px | App KTV thiết kế cho 390 px trước; nút ≥ 44 px |

---

# 5. Acceptance Criteria (FE)

1. App KTV không có link / route nào tới trang chủ xưởng (bảng giá, luật, KTV).
2. KTV không thấy giá trong mọi màn.
3. Nút theo quyền: không có `DRAFT_EXTRA` ⇒ không có "Phát sinh".
4. Nhãn "Kỹ thuật viên" cho chủ xưởng đã đổi trước khi bật WS-03 (R2).
5. Hai theme, 390 px; `npm test`, `npx tsc --noEmit -p .` qua; không thêm dependency.

---

# 6. Tests (Vitest)

| File | What | Count |
|---|---|---|
| `technician-app/jobView.test.ts` | `jobRowView(job, permissions)` → nút theo quyền, không giá | +3 |
| `technician-app/authErrors.test.ts` | Ánh xạ lỗi đăng nhập / đổi mật khẩu → thông điệp; `toTechnicianEmail(username)` | +4 |
| `technician-app/passwordRules.test.ts` | Quy tắc mật khẩu mới (độ dài, chữ + số, khác tên đăng nhập) | +3 |
| `technician-app/guard.test.ts` | `mustChangePassword` ⇒ mọi route `/ktv/*` chuyển về đổi mật khẩu | +2 |
| `workshop-board/technicianRow.test.ts` | Badge trạng thái, tải hôm nay, hành động theo trạng thái | +4 |
| `workshop-board/assignSelect.test.ts` | Lọc KTV làm ngày đó, đánh dấu thiếu kỹ năng | +2 |
| `app/routes.test.ts` | `/ktv/*` không nằm dưới guard chủ xưởng; `/technician/*` không vào được bằng vai trò KTV | +2 |

---

# 7. Truy vết FF → FE

| FF | FE |
|---|---|
| UC-WS03-01, 05, 06, SCR-WS03-01 | §2.2 |
| UC-WS03-02, UC-WS03-07, AF-WS03-01, EF-WS03-01/04, BR-WS03-08, AC-WS03-05 | §2.2 (đặt lại), §2.4 (`/ktv/login`, `/ktv/change-password`) |
| UC-WS03-03/04, SCR-WS03-03 | §2.3 |
| SCR-WS03-02, BR-WS03-03 | §2.4 |
| FF §23, P2Q-01 | §2.1 |

---

# 8. Analytics

`ws_technician_created`, `ws_technician_password_reset`, `ktv_password_changed` (`firstTime`), `ws_technician_absence_marked` (`kind`), `ws_assignment_changed` (`source`), `ktv_login`, `ktv_jobs_viewed` (`count`), `ktv_progress_updated` (`stage`).

---

# 9. Change Log

| Version | Date | Change |
|---|---|---|
| `v0.1` | `2026-10-12` | Bản nháp đầu |
| `v0.2` | `2026-10-12` | PO chốt: tạo tài khoản tên đăng nhập + mật khẩu tạm, đổi mật khẩu lần đầu, đặt lại mật khẩu (thay mời Google) |
