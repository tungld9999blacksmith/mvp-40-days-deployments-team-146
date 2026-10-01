# EV Care — Frontend

React 19 + TypeScript + Vite + Tailwind CSS 4 + React Router 7, xây theo các Frontend Specification ở `docs/specs/sprint-*/frontend/*.fe.md`.

## Chạy

```bash
npm --prefix frontend ci
cp .env.example .env                            # ở gốc repo, rồi điền mục FRONTEND (VITE_FIREBASE_*)
npm --prefix frontend run dev                   # http://localhost:5173
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
| `/notifications`, `/notifications/settings` | Thông báo (mock) · Cài đặt nhắc bảo dưỡng | US-021 |
| `/workshop/login` | Đăng nhập Workshop Portal | US-009, US-013 |
| `/workshop/onboarding/profile · operations · verifying · success · failed` | Onboarding chủ xưởng | US-009 |
| `/technician`, `/technician/quotes`, `/technician/quote-review[?quoteId=]`, `/technician/notifications` | Workshop Portal (mock, trừ panel hội thoại) | US-025 SCR-605 |
| `/booking`, `/booking/workshops · slots · confirm` | Đặt lịch theo sức chứa & vị trí (API-BK-01 → 03) | US-029 |
| `/bookings/:bookingId` | Kết quả giữ chỗ + huỷ giữ chỗ (API-BK-04). Bản rút gọn của Booking Ticket, chờ API xem lịch hẹn của us-053 | US-029, US-053 |
| `/history`, `/estimate` | Dữ liệu mock (chờ API us-045 và lịch sử dịch vụ) | — |

## Tổ chức

- `src/app/App.tsx` — route. Nhánh chủ xe bọc `AuthProvider`, nhánh Workshop Portal bọc `WorkshopAuthProvider` (phiên tách riêng).
- `src/features/auth/` — Firebase, phiên chủ xe, onboarding chủ xe, `resolveOnboardingRoute()`.
- `src/features/workshop-auth/` — phiên và onboarding chủ xưởng, `resolveWorkshopRoute()`.
- `src/features/vehicles/` — hồ sơ xe, trạng thái đến hạn (chỉ hiển thị số liệu backend trả về).
- `src/features/notifications/` — cài đặt nhắc bảo dưỡng.
- `src/features/bookings/` — đặt lịch: `api.ts`, `context/BookingWizardContext` (token chỉ giữ trong bộ nhớ), `hooks/useSlotRequest`, `components/` (`BookingSummaryCard` dùng chung được cho chat).
- `src/features/assistant/` — chat: `transport/` (`ChatTransport`: `http` SSE / `mock`), `sse.ts`, `state/chatReducer.ts`.
- `src/shared/api/client.ts` — gắn Firebase ID token + `X-Request-ID`, bóc envelope `{ data }`, `ApiError` theo `{ error: { code, message, details, traceId } }`, retry 1 lần khi `401`.
- `src/shared/ui/` — bộ component theo phong cách thiết kế: `Button`, `Card`, `Field` (`TextInput`, `TextArea`, `SelectInput`), `Checkbox`, `Switch`, `NumberStepper`, `Badge`, `Skeleton`, `Dialog`, `Drawer`, `Toast`, `States` (`EmptyState`, `ErrorState`, `Notice`), `Stepper`, `SafeMarkdown`, `SupportLink`.
- `src/shared/hooks/` — `useCachedQuery` (cache theo phiên, xoá khi đăng xuất), `usePolling`, `useOnlineStatus`.
- `src/mocks/` — dữ liệu giả cho các trang chưa có spec.
- `src/styles/index.css` — token màu / font (`bg-background`, `bg-surface`, `bg-card`, `border-border`, `text-emerald`...). Không viết mã hex trong JSX.

Thiết kế: [docs/design](../docs/design/). Spec: [docs/specs](../docs/specs/).
