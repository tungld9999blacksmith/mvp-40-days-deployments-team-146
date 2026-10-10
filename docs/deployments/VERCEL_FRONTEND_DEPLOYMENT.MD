# Deploy Frontend lên Vercel (nối backend Railway)

Hướng dẫn đưa frontend React + Vite (`frontend/`) lên Vercel, gọi backend FastAPI đang chạy trên Railway theo [RAILWAY_BACKEND_DEPLOYMENT.MD](RAILWAY_BACKEND_DEPLOYMENT.MD).

> **Trạng thái:** Draft, cập nhật 07/10/2026. Các bước dưới đây chưa được chạy thử từ đầu đến cuối trên staging. Đánh dấu `[Cần kiểm thử]` là những điểm phải xác nhận khi deploy lần đầu.

## Mục lục

1. [Kiến trúc triển khai](#1-kiến-trúc-triển-khai)
2. [Các file liên quan](#2-các-file-liên-quan)
3. [Bước 1 — Build thử ở local](#bước-1--build-thử-ở-local)
4. [Bước 2 — Cấu hình `vercel.json` cho frontend](#bước-2--cấu-hình-verceljson-cho-frontend)
5. [Bước 3 — Tạo project trên Vercel](#bước-3--tạo-project-trên-vercel)
6. [Bước 4 — Biến môi trường `VITE_*`](#bước-4--biến-môi-trường-vite_)
7. [Bước 5 — Firebase Authorized domains](#bước-5--firebase-authorized-domains)
8. [Bước 6 — Cập nhật biến backend trên Railway](#bước-6--cập-nhật-biến-backend-trên-railway)
9. [Bước 7 — Deploy và smoke test](#bước-7--deploy-và-smoke-test)
10. [Rollback](#rollback)
11. [Xử lý sự cố](#xử-lý-sự-cố)
12. [Việc còn tồn đọng](#việc-còn-tồn-đọng)

---

## 1. Kiến trúc triển khai

```
Trình duyệt ──► https://<app>.vercel.app
                 │
                 ├─ /api/*  ──(Vercel rewrite, proxy phía server)──►  https://backend-staging-1d29.up.railway.app/api/*
                 │                                                      backend (FastAPI) + worker (Celery) + Redis
                 └─ /*      ──► frontend/dist (SPA, fallback về index.html)
```

**Vì sao frontend phải gọi `/api` cùng origin:** API client dùng đường dẫn tương đối `const API_BASE = '/api/v1'` (`frontend/src/shared/api/client.ts`) và không có biến cấu hình base URL. Vì vậy bản build production cần host chuyển tiếp `/api/*` tới backend. Trình duyệt chỉ gọi domain Vercel nên không phát sinh CORS.

**Vì sao không đưa backend lên Vercel:** `vercel.json` cũ ở gốc repo (commit `9251123`, đã xoá ngày 07/10/2026) khai báo **2 service** (frontend Vite và backend FastAPI `src.main:app`). Cách này không phù hợp với EV Care:

- Celery worker, Celery beat (nhắc mốc, nhắc 24h, đồng bộ ODO, dọn nháp báo giá) và Redis không chạy được trên Vercel. Backend vẫn phải ở Railway.
- Chat dùng SSE kéo dài tới 30 giây cho mỗi lượt. Hàm serverless có giới hạn thời gian chạy và không giữ trạng thái giữa các request.
- CI/CD backend (test → `railway up` → smoke test) đã chạy trên Railway.

> **Đã chốt (07/10/2026):** Vercel chỉ chạy frontend. Cấu hình nằm ở `frontend/vercel.json` (Bước 2).

## 2. Các file liên quan

| File | Vai trò |
| --- | --- |
| `frontend/package.json` | Script `build` = `vite build`, đầu ra `frontend/dist/` |
| `frontend/vite.config.ts` | `envDir: '..'` (đọc `.env` ở gốc repo khi build local); proxy `/api` chỉ áp dụng cho dev server |
| `frontend/src/shared/api/client.ts` | `API_BASE = '/api/v1'`; gắn `Authorization` + `X-Request-ID` |
| `.env.example` (mục FRONTEND) | Danh sách biến `VITE_*` |
| `frontend/vercel.json` | Lệnh build, thư mục output, rewrite `/api` sang Railway và SPA fallback (Bước 2) |
| `.github/workflows/ci.yml` (job `frontend`) | `npm ci` → `typecheck` → `build` trên Node 24 |

## Bước 1 — Build thử ở local

```bash
npm --prefix frontend ci
npm --prefix frontend run typecheck
npm --prefix frontend test
npm --prefix frontend run build      # tạo frontend/dist/
npm --prefix frontend run preview    # http://localhost:5173 (không có proxy /api)
```

Build lỗi ở local thì cũng sẽ lỗi trên Vercel. Sửa trước khi đi tiếp.

## Bước 2 — Cấu hình `vercel.json` cho frontend

Vercel đọc `vercel.json` ở **Root Directory** của project. Project trỏ vào `frontend/` (Bước 3) nên cấu hình nằm ở `frontend/vercel.json`:

```json
{
  "$schema": "https://openapi.vercel.sh/vercel.json",
  "framework": "vite",
  "installCommand": "npm ci",
  "buildCommand": "npm run build",
  "outputDirectory": "dist",
  "rewrites": [
    { "source": "/api/:path*", "destination": "https://backend-staging-1d29.up.railway.app/api/:path*" },
    { "source": "/(.*)", "destination": "/index.html" }
  ]
}
```

- Rewrite đầu tiên chuyển tiếp API sang backend staging Railway tại `https://backend-staging-1d29.up.railway.app`. Khi deploy sang môi trường khác, cập nhật domain đích cho đúng backend của môi trường đó (Bước 4 của runbook backend).
- Rewrite thứ hai là **SPA fallback**: tải lại trang ở `/bookings/…`, `/technician/board`, `/c/EVC-…` vẫn trả `index.html` để React Router xử lý. Thiếu rewrite này thì các URL đó trả 404. Vercel phục vụ file tĩnh có thật (`/assets/*`, file trong `public/`) trước khi xét rewrite, nên fallback không che mất các file đó.
- Thứ tự quan trọng: rewrite `/api` phải đứng trước fallback.

`[Cần kiểm thử]` Chat SSE (`POST /api/v1/conversations/{id}/messages`, API-CHAT-004) đi qua rewrite tới origin ngoài. Phải xác nhận các event được đẩy dần về trình duyệt, không bị gom lại cho tới cuối lượt, và không bị cắt trước 30 giây.

## Bước 3 — Tạo project trên Vercel

1. Vercel Dashboard → **Add New… → Project** → import repo GitHub.
2. **Root Directory**: `frontend`.
3. **Framework Preset**: Vite. Build/Output đã khai trong `frontend/vercel.json`.
4. **Node.js Version** (Settings → General): `24.x`, trùng với CI.
5. **Production Branch** (Settings → Git): `staging` nếu Vercel chỉ dùng cho staging, `main` nếu đây là production. Các nhánh khác tạo Preview Deployment.

## Bước 4 — Biến môi trường `VITE_*`

Settings → Environment Variables. Biến `VITE_*` được **nhúng vào bundle lúc build**: đổi giá trị xong phải **Redeploy** mới có hiệu lực. Không đặt bí mật ở đây vì mọi biến đều đọc được trong trình duyệt.

| Biến | Giá trị staging/production | Ghi chú |
| --- | --- | --- |
| `VITE_FIREBASE_API_KEY` | Lấy từ Firebase Console → Project settings → Your apps → Web app | Bắt buộc |
| `VITE_FIREBASE_AUTH_DOMAIN` | `<project-id>.firebaseapp.com` | Bắt buộc |
| `VITE_FIREBASE_PROJECT_ID` | `<project-id>` | Bắt buộc. Phải **cùng project** với service account backend dùng để verify token |
| `VITE_FIREBASE_APP_ID` | Từ Firebase Web app | Bắt buộc |
| `VITE_FIREBASE_AUTH_EMULATOR_URL` | *(để trống)* | Có giá trị thì app dùng Emulator và bật chế độ demo |
| `VITE_DEMO_MODE` | `false` | |
| `VITE_CONSENT_POLICY_VERSION` | `2026-09` | Phải khớp `CONSENT_POLICY_VERSION` của backend |
| `VITE_WORKSHOP_CONSENT_POLICY_VERSION` | `WS-2026-09` | Phải khớp `WORKSHOP_CONSENT_POLICY_VERSIONS` của backend |
| `VITE_CHAT_TRANSPORT` | `http` | `mock` chỉ dùng khi demo không có backend |
| `VITE_CHAT_WS_ENABLED` | `false` | Chưa dùng ở MVP |
| `VITE_API_MOCKS` | `off` | Bật mock trên môi trường thật sẽ làm thao tác trên Board chỉ đổi dữ liệu giả |
| `VITE_SUPPORT_URL` | Link hỗ trợ của đội | Tuỳ chọn |

`VITE_BACKEND_URL` **không** cần trên Vercel: biến này chỉ đổi đích proxy của Vite dev server.

## Bước 5 — Firebase Authorized domains

Firebase Console → Authentication → Settings → **Authorized domains** → thêm:

- Domain production/staging của Vercel (ví dụ `ev-care.vercel.app`) và custom domain nếu có.
- Preview Deployment có URL thay đổi theo từng commit. Nếu cần đăng nhập trên preview, thêm từng domain preview cần test, hoặc chỉ test đăng nhập trên domain cố định.

Thiếu bước này thì nút "Đăng nhập với Google" báo `auth/unauthorized-domain`.

## Bước 6 — Cập nhật biến backend trên Railway

Trên service `backend` **và** `worker` (Railway → Variables), rồi redeploy:

| Biến | Giá trị | Dùng để |
| --- | --- | --- |
| `FRONTEND_URL` | `https://<app>.vercel.app` (không có `/` cuối) | Link trong email nhắc bảo dưỡng / hỏi thăm (worker), và là một origin được CORS cho phép |
| `CORS_ORIGINS` | Như trên. Thêm custom domain, phân tách bằng dấu phẩy | Danh sách origin được CORS cho phép, gộp với `FRONTEND_URL` (`cors_allow_origins()` trong `backend/src/main.py`) |
| `APP_BASE_URL` | Như trên, hoặc custom domain | Nội dung QR trên Booking Ticket: `{APP_BASE_URL}/c/{bookingCode}` (us-053 BR-1203). Để trống thì lấy `FRONTEND_URL` |

> Khi trình duyệt gọi API qua rewrite cùng origin, CORS không được dùng tới. Vẫn nên đặt `CORS_ORIGINS` đúng để dùng được phương án dự phòng (gọi thẳng Railway). `FRONTEND_URL` luôn phải đúng vì email và QR cần nó.

## Bước 7 — Deploy và smoke test

Push lên Production Branch, hoặc chạy `vercel --prod` trong `frontend/`. Sau khi deploy xong, kiểm tra:

| # | Kiểm tra | Kết quả đúng |
| --- | --- | --- |
| 1 | Mở `https://<app>.vercel.app/` | Màn đăng nhập chủ xe, không có lỗi trong Console |
| 2 | `https://<app>.vercel.app/api/v1/health/dependencies` | JSON từ backend Railway (chứng minh rewrite chạy) |
| 3 | Đăng nhập Google bằng tài khoản chủ xe đã onboard | Vào `/dashboard`, thấy xe và trạng thái đến hạn |
| 4 | Tải lại trang tại `/vehicle` và `/history` | Trang vẫn hiện, không trả 404 (SPA fallback) |
| 5 | `/ai` → gửi một câu hỏi | Câu trả lời hiện dần, có trích nguồn (SSE qua rewrite) |
| 6 | Đặt lịch 3 bước → mở ticket | Có mã `EVC-…` và QR. Quét QR mở đúng domain Vercel |
| 7 | `/workshop/login` bằng tài khoản chủ xưởng (cửa sổ ẩn danh) | Vào `/technician`, thấy Board và báo giá chờ duyệt |
| 8 | DevTools → Network → một request `/api/v1/…` | Có header `X-Request-ID` ở response |

## Rollback

Vercel giữ mọi bản deploy. Vào Deployments → chọn bản trước → **Promote to Production** (Instant Rollback). Không cần build lại. Nếu lỗi do biến `VITE_*`, sửa biến rồi Redeploy bản đang chạy.

## Xử lý sự cố

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Màn đăng nhập báo "Chưa cấu hình đăng nhập" | Thiếu `VITE_FIREBASE_*` lúc build | Thêm biến, Redeploy |
| `auth/unauthorized-domain` | Chưa thêm domain vào Firebase | Bước 5 |
| Đăng nhập xong mọi API trả 401 | Firebase Web app và service account backend thuộc 2 project khác nhau | Đồng bộ `VITE_FIREBASE_PROJECT_ID` với project của `FIREBASE_CREDENTIAL` |
| `/api/...` trả HTML của app | Rewrite SPA đứng trước rewrite `/api`, hoặc thiếu rewrite `/api` | Sửa thứ tự trong `frontend/vercel.json` |
| Tải lại trang con bị 404 | Thiếu SPA fallback | Bước 2 |
| Chat đứng tới cuối mới hiện cả câu, hoặc bị cắt | Proxy gom hoặc cắt luồng SSE | Xem mục `[Cần kiểm thử]` ở Bước 2. Phương án dự phòng: thêm biến base URL cho API, gọi thẳng Railway và đặt `FRONTEND_URL` cho CORS |
| Báo lỗi consent khi onboarding | Phiên bản điều khoản FE ≠ BE | Đồng bộ `VITE_*CONSENT_POLICY_VERSION` với backend |
| QR mở `localhost` | `APP_BASE_URL` / `FRONTEND_URL` trên Railway còn giá trị local | Bước 6 |

## Việc còn tồn đọng

- [x] Chốt phương án Vercel chỉ chạy frontend; thay `vercel.json` ở gốc repo bằng `frontend/vercel.json` (07/10/2026).
- [x] Cấu hình domain backend staging Railway trong `frontend/vercel.json`: `https://backend-staging-1d29.up.railway.app`.
- [ ] Chạy đủ checklist ở Bước 7 trên staging, ghi URL thật vào tài liệu này và `README.md`.
- [ ] Xác nhận SSE qua rewrite (Bước 2).
- [x] Backend đọc cả `CORS_ORIGINS` (nhiều origin) và `FRONTEND_URL` (07/10/2026).
- [ ] Thêm bước smoke test frontend (mục 1–2 ở Bước 7) vào CI sau khi deploy.
