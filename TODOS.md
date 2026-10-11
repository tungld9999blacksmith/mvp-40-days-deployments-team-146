# TODOS

## Backend (from /review on develop, 2026-10-06)

- [x] **P1 · Connection pool** Async booking paths (`create_hold`, `reschedule`, `find_nearby`, `check_availability`) kept the request `Session` idle in transaction while waiting on Redis locks and tokens. Fixed on develop, 2026-10-10 (not yet deployed): `end_read_transaction` / `run_then_release` in `infrastructure/supabase/db.py` end the transaction with a commit that does not expire loaded rows (`rollback()` would expire `user`/`vehicle`, and the next attribute read on the event loop would reopen a transaction). Used by every `BookingService` threadpool read and write, the geo index reads, and both `require_active_vehicle_owner` guards. Test: `test_booking_paths_wait_on_redis_without_an_open_transaction` records any Redis command sent while `session.in_transaction()`.

## Quote / booking_line (from /plan-eng-review on develop, 2026-10-09)

- [x] **P2 · Kênh ghi quyết định phát sinh qua điện thoại** — Done on develop, 2026-10-10 (5bec775, 51c2d0e; migration `a7e3c1f9d4b2` đã chạy trên DB dùng chung), theo quy tắc tối giản người dùng chọn trước khi có kết quả The Assignment: xưởng ghi `decided_via = PHONE` + tên người xác nhận, chủ xe được báo ngay, "Tôi không đồng ý" trước khi hoàn tất đưa dòng về PROPOSED (không tính tiền, chặn COMPLETE) để chủ xe tự quyết trên app. Xem lại nếu phỏng vấn cho thấy cần quy tắc khác (ví dụ xưởng giữ dòng khi tranh chấp). Đã deploy lên staging (fa11f84); chưa bấm thử trên giao diện: làm trong smoke test 12/10.
- [x] **P2 · Design review màn Bảng giá + nhãn giá đặt lịch** — Fixed by /design-review on develop, 2026-10-10: tên dòng xe thay mã MDL, "Miễn phí" thay "0 ₫", nhãn ô %, bỏ "Chi phí ước tính" ở booking two_tier, nhãn "Bảo hành" trên board, ẩn menu/ô "Báo giá" khi two_tier và thay bằng "Phát sinh chờ chủ xe" (D1 = A). Nhãn ở bước xác nhận đặt lịch không cần sửa.
- [x] **P2 · Hạng mục an toàn theo tài liệu** — Done on develop, 2026-10-11: `maintenance_rule.is_safety_critical` (migration `b9d4f2a6c8e1`, đã chạy và gắn cờ 77 rule trên DB dùng chung) từ nhóm phanh, lốp/bánh xe, lái, đèn/còi/gạt nước, dây an toàn của `lich_bao_duong_ALL.md`; bỏ đoán theo từ khoá bỏ dấu ("lại" bị hiểu là "lái").
- [x] **P2 · Nhắc gọi chủ xe sau 10 phút + hiện hạn trả lời** — Done on develop, 2026-10-11: `booking_line.asked_at` (migration `c3e7a1d5f9b2`, đã chạy trên DB dùng chung), hạn hiện cho chủ xe và xưởng, nhãn "Cần gọi" ở Dashboard xưởng. Chưa xem giao diện thật (hai theme, 390px).
- [ ] **P3 · Báo chủ động cho xưởng khi quá 10 phút** Hiện xưởng chỉ thấy "Cần gọi" khi đang mở bảng điều phối/Dashboard (tải lại 15 giây). Nếu xưởng không ngồi trước màn hình: thêm job nền gửi thông báo cho xưởng lúc quá hạn (một lần mỗi `asked_at`).
- [ ] **P3 · Tên dòng xe chưa có xe nào liên kết** Bảng giá lấy tên ("VF8 Plus") từ xe đã xác minh; mẫu chưa có xe (staging: MDL-02, MDL-03) vẫn hiện mã. Nếu cần đủ tên: đồng bộ danh mục `/models` của hãng vào một bảng (job), không gọi hãng trong request (giữ transaction mở, xem P1 Connection pool).

## Two-tier pricing (from /qa on develop, 2026-10-10)

Reports: `.gstack/qa-reports/run-20261009T201844Z/` and `.gstack/qa-reports/run-20261010T080327Z/`.

- [x] **P1 · Smoke test two_tier trên staging tới Hoàn tất** — Done 2026-10-10 trên EVC-D94187B3 (đã dời ngày sang 10/10 trong DB để check-in được, người dùng đồng ý): check-in → Bắt đầu → 2 phát sinh (1 có ảnh) → ghi qua điện thoại → chủ xe "Tôi không đồng ý" → quyết lại trên app → Hoàn tất, `actual_cost` 520.000 ₫ khớp tổng dòng. Tìm và sửa: quyết định qua điện thoại không hiện trong feed chủ xe (36b858e). Chưa kiểm được hộp thư email của chủ xe. EVC-CD0FE459 đã được chủ xe huỷ lúc 21:08. Báo cáo: `.gstack/browse-reports/2026-10-10-smoke/`.
- [ ] **P2 · Log file backend trên Railway không ghi được** `PermissionError: [Errno 13] Permission denied: '/app/logs/app.log'` mỗi request: volume `backend-logs` mount ở `/app/logs` thuộc root, app chạy uid 1000 (`dockerfiles/Dockerfile.railway`). Log vẫn ra stdout. Fix: chown volume khi khởi động (entrypoint chạy root rồi hạ quyền) hoặc bỏ file handler trên Railway.
- [x] **P1 · Bật `QUOTE_FLOW=two_tier` sau M5 (12/10)** — Đã bật trên staging trước M5 (10/10). Code, migration `d2a8c6e4f1b7` và bucket `booking-line-photos` đã sẵn trên môi trường dùng chung; QA lượt 2 đạt. Bật: `railway variables --service <backend> --set QUOTE_FLOW=two_tier` (backend tự redeploy), deploy frontend `develop` mới (cần `GET /api/v1/pricing-flow` để ẩn luồng báo giá cũ). Tắt lại: `QUOTE_FLOW=legacy`; booking two_tier đang mở vẫn đi hết luồng hai tầng. Sau khi bật: thử một booking thật từ đầu tới Hoàn tất, xem feed và email.
- [x] **ISSUE-009 Trợ lý chat để lộ trạng thái thô "(`APPROVED`)"** — Fixed on develop, 2026-10-10: `get_booking_lines` trả nhãn tiếng Việt ("Đã đồng ý", "Không làm", "Đang làm"…).
- [x] **ISSUE-003 Một dịch vụ hiện nhiều lần trên Bảng giá** — Fixed by /qa on develop, 2026-10-10 (46d69ae: gộp theo tên, đặt giá một lần cho cả nhóm mã).
- [x] **ISSUE-002 Nút "Đặt giá"/"Sửa" trùng tên truy cập** — Fixed by /qa on develop, 2026-10-10 (46d69ae).
- [x] **ISSUE-004 Dòng giá tham khảo đã xác nhận vẫn ghi "Giá tham khảo"** — Fixed by /qa on develop, 2026-10-10 (240318b).
- [x] **ISSUE-005 Giá phát sinh "Không làm" không gạch trên bảng điều phối** — Fixed by /qa on develop, 2026-10-10 (d5d3a3b).
- [x] **ISSUE-006 Bước xác nhận đặt lịch two_tier vẫn ghi "Báo giá: Không"** — Fixed by /qa on develop, 2026-10-10 (240318b).

## Design (from /design-review on develop, 2026-10-04)

All design-review findings are fixed; decisions are logged in DESIGN.md.

## Design (from /design-review on develop, 2026-10-05, real demo backend)

IDs below belong to the 2026-10-05 report (`~/.gstack/projects/<slug>/designs/design-audit-20261005/`).

- [x] **Medium · Hierarchy** Dashboard states "quá 14.210 km · quá 199 ngày" three times in one view. (FINDING-010) Fixed 2026-10-10: from `sm` the banner headline is the milestone only; the readouts beside it carry the figures (phones, where readouts are hidden, keep them in the headline).
- [x] **Medium · Content** /vehicle says "Màu: Trắng" next to a red model photo. (FINDING-011) Fixed 2026-10-10: hero caption reads "Ảnh minh hoạ · Màu xe: …" when the stock model photo shows.
- [x] **Medium · Content** Estimate says "Chưa có dữ liệu bảo hành từ hãng" while /vehicle lists active warranties. (FINDING-012) Fixed 2026-10-10: demo-backend only (it sent `warrantyStatus: "DEMO"`, the FE forced legacy payloads to UNKNOWN). Demo now sends ACTIVE; FE keeps any known status (`warrantyStatusOf`).
- [x] **Medium · Interaction** Booking ticket has no reschedule/cancel action, though Lịch hẹn của tôi promises "đổi hoặc huỷ lịch". (FINDING-013) Fixed 2026-10-10: the real backend already returns the actions and a blocked reason (too close / max reschedules); the ticket now also explains `NOT_CONFIRMED` (pending booking past its hold). The demo backend (`src/demo`) still returns no actions: it has no owner cancel/reschedule endpoints.
- [x] **Medium · Hierarchy** Login on phones hides the product statement. (FINDING-014) Fixed 2026-10-10: `AuthMobileBrand` shows the headline and promise under the logo below `lg`, on both login pages.
- [x] **Medium · AI Slop** Workshop Dashboard desktop: icon-tile KPI cards for single digits. (FINDING-015) Fixed 2026-10-10: one strip of count links (label + mono figure, warning colour when a count needs action), same position and links.
- [x] **Medium · Typography** Notifications jumps from h1 to h3 item titles. (FINDING-019) Fixed 2026-10-10: item titles are h2.
- [ ] **Polish · Layout** Owner pages use different max widths (880 / 944 / 976 / full). (FINDING-016)
- [ ] **Polish · Content** Workshop Portal says "Dashboard" and "05/10/2026"; the owner app says "Tổng quan" and "5 tháng 10". (FINDING-017)
- [ ] **Polish · Content** Booking ticket shows "Đã xác nhận" twice (badge and status strip). (FINDING-018)
- [ ] **Polish · Content** Workshop list note "(chưa có toạ độ để tính khoảng cách)" reads like a dev note. (FINDING-020)
- [ ] **Polish · Responsive** Workshop Dashboard on phones truncates the customer name behind the status badge. (FINDING-021)
- [x] **Medium · Responsive** Owner Dashboard at 390px scrolled sideways: the "Lịch hẹn sắp tới" highlight sized the implicit grid column to its content (446px). Found and fixed 2026-10-10 (`grid-cols-1`).

## Completed
- [x] **Medium · Interaction** Demo panel opens expanded on Login and covers half the brand panel; default it to collapsed for Demo Day. (FINDING-014) Fixed by /design-review on trungmv-fontend, 2026-10-04.
- [x] **Medium · Content** AI page shows the same five suggested questions in the centre and in the right rail. (FINDING-015) Fixed by /design-review on trungmv-fontend, 2026-10-04.
- [x] **Medium · Interaction** Onboarding consent checkbox is ~16px, below the 44px touch target. (FINDING-017) Fixed by /design-review on trungmv-fontend, 2026-10-04.
- [x] **Polish · Content** Greeting subtitle "Mọi chuyến đi hôm nay, vì một tương lai xanh hơn." is filler; replace with real status. (FINDING-019) Fixed by /design-review on trungmv-fontend, 2026-10-04.
- [x] **Polish · Content** Workshop greeting shows the name in green; the owner app uses ink. (FINDING-020) Fixed by /design-review on trungmv-fontend, 2026-10-04.
- [x] **Medium · Layout** Dashboard desktop: "Xe của tôi" card stretches with a ~200px gap and the right column is empty below the AI card. (FINDING-011) Fixed by /design-review on trungmv-fontend, 2026-10-04.
- [x] **Medium · Hierarchy** Home banner: short slides leave ~170px empty on mobile because the banner keeps the tallest slide's height. Centre slide content or shorten the tall slide. (FINDING-012) Fixed by /design-review on trungmv-fontend, 2026-10-04.
- [x] **Medium · Hierarchy** Workshop › Lịch hẹn: six stat cards repeat the six status chips right below them. (FINDING-013) Fixed by /design-review on trungmv-fontend, 2026-10-04.
- [x] **Medium · Interaction** Owner sidebar: "Lịch hẹn" and "Đặt lịch" sit together with near-identical icons. (FINDING-016) Fixed by /design-review on trungmv-fontend, 2026-10-04.
- [x] **Medium · Hierarchy** Workshop › Sức chứa: 56 identical "Đã đặt 0 / Khoá 0 / Còn 3" cells at 11px are hard to scan. (FINDING-018) Fixed by /design-review on trungmv-fontend, 2026-10-04.
