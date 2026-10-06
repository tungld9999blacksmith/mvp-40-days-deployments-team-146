# TODOS

## Backend (from /review on develop, 2026-10-06)

- [ ] **P1 · Connection pool** Async booking paths (`create_hold`, `reschedule`, `find_nearby`, `check_availability`) keep the request `Session` idle in transaction while waiting on Redis locks and tokens (up to ~2s per lock). `require_active_vehicle_owner` shares that session and its SELECT opens the transaction. Same failure mode as the 2026-10-06 Supavisor outage. Fix: end the read transaction (`session.rollback()`) at the end of each read-only threadpool helper in `BookingService`, as `OemWebhookService._find_vehicle_id` does, and add a test that no lock is awaited while `session.in_transaction()`.

## Design (from /design-review on develop, 2026-10-04)

All design-review findings are fixed; decisions are logged in DESIGN.md.

## Design (from /design-review on develop, 2026-10-05, real demo backend)

IDs below belong to the 2026-10-05 report (`~/.gstack/projects/<slug>/designs/design-audit-20261005/`).

- [ ] **Medium · Hierarchy** Dashboard states "quá 14.210 km · quá 199 ngày" three times in one view: banner headline, banner readouts, Bảo dưỡng card. (FINDING-010)
- [ ] **Medium · Content** /vehicle says "Màu: Trắng" next to a red model photo. (FINDING-011)
- [ ] **Medium · Content** Estimate says "Chưa có dữ liệu bảo hành từ hãng" while /vehicle lists active warranties; check `warrantyStatus` in the demo backend. (FINDING-012)
- [ ] **Medium · Interaction** Booking ticket has no reschedule/cancel action, though Lịch hẹn của tôi promises "đổi hoặc huỷ lịch"; confirm the rule for same-day bookings. (FINDING-013)
- [ ] **Medium · Hierarchy** Login on phones hides the product statement; only the logo and "Đăng nhập" remain. (FINDING-014)
- [ ] **Medium · AI Slop** Workshop Dashboard desktop: three 150px icon-tile KPI cards for single digits. (FINDING-015)
- [ ] **Medium · Typography** Notifications jumps from h1 to h3 item titles. (FINDING-019)
- [ ] **Polish · Layout** Owner pages use different max widths (880 / 944 / 976 / full). (FINDING-016)
- [ ] **Polish · Content** Workshop Portal says "Dashboard" and "05/10/2026"; the owner app says "Tổng quan" and "5 tháng 10". (FINDING-017)
- [ ] **Polish · Content** Booking ticket shows "Đã xác nhận" twice (badge and status strip). (FINDING-018)
- [ ] **Polish · Content** Workshop list note "(chưa có toạ độ để tính khoảng cách)" reads like a dev note. (FINDING-020)
- [ ] **Polish · Responsive** Workshop Dashboard on phones truncates the customer name behind the status badge. (FINDING-021)

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
