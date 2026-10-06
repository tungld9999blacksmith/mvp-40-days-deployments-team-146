# EV Care — Frontend

React 19 + TypeScript + Vite + Tailwind CSS 4 + React Router 7, xây theo các Frontend Specification ở `docs/specs/sprint-*/frontend/*.fe.md`.

## Chạy

```bash
npm --prefix frontend ci
cp .env.example .env                            # ở gốc repo, rồi điền mục FRONTEND (VITE_FIREBASE_*)
npm --prefix frontend run dev                   # http://localhost:5173
npm --prefix frontend run dev:demo              # Vite mode demo; vẫn cần Firebase và backend
npm --prefix frontend run typecheck
npm --prefix frontend test                      # vitest
npm --prefix frontend run build                 # frontend/dist/
```

Backend (để đăng nhập và gọi API thật):

```bash
docker compose -f docker-compose.infra.yaml up -d
cd backend && uv run uvicorn src.main:app --reload --port 8000
```

Dev server proxy `/api` và `/health` sang `http://localhost:8000` (đổi bằng `VITE_BACKEND_URL`). Bản build production cần host phục vụ SPA fallback và chuyển tiếp `/api` tới backend.

## Biến môi trường (mục FRONTEND trong `.env` ở gốc repo)

Toàn repo dùng **một** file `.env` ở gốc (mẫu: `.env.example`, chia mục CHUNG / BACKEND / FRONTEND). Vite đọc file này nhờ `envDir: '..'` và chỉ đưa biến `VITE_*` vào trình duyệt.

| Biến | Bắt buộc | Ý nghĩa |
| --- | --- | --- |
| `VITE_FIREBASE_API_KEY`, `VITE_FIREBASE_AUTH_DOMAIN`, `VITE_FIREBASE_PROJECT_ID`, `VITE_FIREBASE_APP_ID` | Có | Firebase Web app, cùng project backend dùng để verify token. Thiếu thì màn đăng nhập báo "Chưa cấu hình đăng nhập". |
| `VITE_FIREBASE_AUTH_EMULATOR_URL` | Không | Dùng Firebase Auth Emulator khi dev. |
| `VITE_CONSENT_POLICY_VERSION` / `VITE_WORKSHOP_CONSENT_POLICY_VERSION` | Không | Phiên bản điều khoản gửi kèm consent (mặc định `2026-09` / `WS-2026-09`), phải khớp backend. |
| `VITE_CHAT_TRANSPORT` | Không | `http` (mặc định — API hội thoại thật, SSE theo API-CHAT-004) hoặc `mock` (dữ liệu giả, chạy không cần backend). |
| `VITE_CHAT_WS_ENABLED` | Không | Chưa dùng ở MVP (`false`). |
| `VITE_API_MOCKS` | Không | Mock API cho các nhóm endpoint: `off` (mặc định), `all` (= `estimate,bookings,board,crm`), hoặc danh sách nhóm. Xem [Mock API](#mock-api). |
| `VITE_DEMO_MODE` | Không | Đánh dấu UI demo; Firebase Emulator cũng bật cờ này. Không bỏ Firebase hoặc tự bật mock API/chat. |
| `VITE_SUPPORT_URL` | Không | Link cho các nút "Liên hệ hỗ trợ" / "Liên hệ hãng". |

Không commit `.env`.

## Route

| Path | Màn hình | Spec |
| --- | --- | --- |
| `/` | Đăng nhập chủ xe (Google) | US-001, US-005 |
| `/onboarding/profile · vehicle · verifying · success · failed` | Onboarding chủ xe | US-001 |
| `/dashboard` | Home: xe + trạng thái đến hạn | US-017 |
| `/vehicle` | Hồ sơ xe | US-017 |
| `/ai`, `/ai/new`, `/ai/:conversationId` | AI Trợ lý (chat có trích nguồn) | US-025 |
| `/notifications`, `/notifications/settings` | Thông báo (nhắc bảo dưỡng, cập nhật lịch hẹn, khảo sát) · Cài đặt nhắc bảo dưỡng (kênh ngoài "Sắp có") | US-021 |
| `/workshop/login` | Đăng nhập Workshop Portal | US-009, US-013 |
| `/workshop/onboarding/profile · operations · verifying · success · failed` | Onboarding chủ xưởng | US-009 |
| `/booking`, `/booking/workshops · slots · confirm` | Đặt lịch theo sức chứa & vị trí (API-BK-01 → 03); thẻ tóm tắt có chi phí ước tính | US-029 |
| `/estimate`, `/estimate/compare` | Dự toán chi phí theo mốc + xưởng, so sánh 2–3 xưởng (API-EST-01 → 03) | US-045 |
| `/bookings`, `/bookings/:bookingId[?src=REMINDER_24H]` | Lịch của tôi · Booking Ticket (QR, xác nhận đến, huỷ, tiến độ 6 bước) | US-033, US-053, US-057 |
| `/bookings/:bookingId/reschedule` | Đổi lịch cùng xưởng (token `RESCHEDULE`, Idempotency-Key) | US-053 |
| `/c/:bookingCode` | URL trong QR: chủ xưởng ⇒ `/technician/check-in?code=`, chủ xe ⇒ ticket của mình | US-053 |
| `/follow-ups/:followUpId` | Hỏi thăm sau dịch vụ (chấm sao, khuyến cáo an toàn) | US-041 |
| `/technician` | Dashboard Portal: tóm tắt hôm nay (WB-01) | US-037 |
| `/technician/board[/:bookingId]` | Workshop Board + drawer chi tiết (chấp nhận/từ chối/check-in/bắt đầu/hoàn tất/huỷ, tiến độ) | US-037, US-057 |
| `/technician/check-in` | Quét QR (BarcodeDetector) hoặc nhập mã ⇒ check-in | US-037 |
| `/technician/capacity`, `/technician/settings/booking` | Sức chứa & khoá chỗ · chế độ xác nhận | US-037 |
| `/technician/notifications` | Thông báo: lịch hẹn 7 ngày tới đang chờ xưởng xác nhận (WB-01) | US-037 |
| `/history` | Lịch sử dịch vụ (mock — chưa có spec) | — |

## Tổ chức

- `src/app/App.tsx` — route. Nhánh chủ xe bọc `AuthProvider`, nhánh Workshop Portal bọc `WorkshopAuthProvider` (phiên tách riêng).
- `src/features/auth/` — Firebase, phiên chủ xe, onboarding chủ xe, `resolveOnboardingRoute()`.
- `src/features/workshop-auth/` — phiên và onboarding chủ xưởng, `resolveWorkshopRoute()`.
- `src/features/vehicles/` — hồ sơ xe, trạng thái đến hạn (chỉ hiển thị số liệu backend trả về).
- `src/features/notifications/` — feed thông báo và cài đặt nhắc bảo dưỡng.
- `src/features/bookings/` — đặt lịch: `api.ts`, `context/BookingWizardContext` (token chỉ giữ trong bộ nhớ), `hooks/useSlotRequest`, `components/` (`BookingSummaryCard` dùng chung được cho chat).
- `src/features/assistant/` — chat: `transport/` (`ChatTransport`: `http` SSE / `mock`), `sse.ts`, `state/chatReducer.ts`.
- `src/shared/api/client.ts` — gắn Firebase ID token + `X-Request-ID`, bóc envelope `{ data }`, `ApiError` theo `{ error: { code, message, details, traceId } }`, retry 1 lần khi `401`.
- `src/shared/ui/` — bộ component theo phong cách thiết kế: `Button`, `Card`, `Field` (`TextInput`, `TextArea`, `SelectInput`), `Checkbox`, `Switch`, `NumberStepper`, `Badge`, `Skeleton`, `Dialog`, `Drawer`, `Toast`, `States` (`EmptyState`, `ErrorState`, `Notice`), `Stepper`, `SafeMarkdown`, `SupportLink`.
- `src/shared/hooks/` — `useCachedQuery` (cache theo phiên, xoá khi đăng xuất), `usePolling`, `useOnlineStatus`.
- `src/features/estimate/` (us-045), `workshop-board/` (us-037), `progress/` (us-057, dùng chung ticket + Board), `after-service/` (us-041, chỉ hỏi thăm sau dịch vụ).
- `src/mocks/server/` — Mock API (xem dưới). `src/mocks/*.ts` còn lại là dữ liệu giả cho trang chưa có spec (lịch sử dịch vụ, danh sách thông báo).
- `src/styles/index.css` — token màu / font (`bg-background`, `bg-surface`, `bg-card`, `border-border`, `text-emerald`...). Không viết mã hex trong JSX.

## Chế độ demo

Demo Agent + Backend + Frontend uses `src.demo.main:app`, Firebase Auth Emulator, `VITE_CHAT_TRANSPORT=http` and `VITE_API_MOCKS=off`. See [startup and E2E walkthrough](../docs/plans/AGENT_BACKEND_DEMO_PLAN.md).

`dev:demo` / `build:demo` only select Vite mode. They do not bypass Firebase, generate demo tokens or force API/chat mocks. The offline DemoPanel is not mounted because its progress and shortcuts use a separate browser store.

Completed registration redirects to the dashboard; unfinished registration resumes the saved step. Registration survives backend restart via JSON. Booking/chat data remains in backend memory. Use separate browser profiles for owner and workshop sessions. Hosting a production build requires API proxying to the backend.

## Mock API

Backend chưa có API của us-033/037/041/045/053/057. Các màn này gọi đúng contract trong `docs/specs/**/api/*.api.md`; khi `VITE_API_MOCKS` bật, `rawRequest` trả lời các endpoint đó bằng `src/mocks/server` (cùng envelope `{ data }` / `{ error }`, có độ trễ giả). Endpoint backend đã có (đăng nhập, xe, BK-01 → 04, chat…) vẫn đi tới backend thật.

- **Học dữ liệu thật:** mock ghi lại xe, xưởng gần (BK-01) và booking vừa tạo bằng BK-03 thật, nên dự toán/ticket dùng đúng id và tên thật.
- **Dữ liệu demo:** lần gọi đầu tạo sẵn lịch hẹn (đã xác nhận, hoàn tất có khảo sát, đã huỷ) và lịch hẹn của khách khác trên Board. Lưu ở `localStorage` (`evcare.mockApi.v1`, dữ liệu phiên bản cũ có báo giá/phiếu bị bỏ khi tải) nên app chủ xe và Workshop Portal mở cùng trình duyệt thấy cùng dữ liệu. Xoá: gõ `evcareMock.reset()` trong console.
- **Khác backend thật:** Board/Portal thấy mọi booking của mock (không lọc theo xưởng); hỏi thăm mở sau 1 phút thay vì 12 giờ; thao tác trên Board chỉ đổi dữ liệu mock (booking thật trong DB không đổi).
- Khi backend có endpoint nào, tắt nhóm tương ứng (ví dụ `VITE_API_MOCKS=estimate,crm` chỉ còn mock 2 nhóm đó) hoặc `off`.
- Kịch bản end-to-end của mock API có test: `src/mocks/server/demoFlow.test.ts` (onboarding → đặt lịch → Board → hoàn tất → khảo sát) và `src/features/assistant/transport/mockQuickBooking.test.ts` (us-061).

Thiết kế: [docs/design](../docs/design/). Spec: [docs/specs](../docs/specs/).
