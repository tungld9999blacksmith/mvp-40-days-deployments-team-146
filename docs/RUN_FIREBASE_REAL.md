# Chạy EV Care với Firebase Authentication thật

Tài liệu này chỉ hướng dẫn cấu hình đăng nhập Google thật cho chủ xe và chủ
xưởng, frontend gọi backend chính `src.main:app`. Không thay đổi UI, agent,
RAG hoặc triển khai email. Firebase dùng cho xác thực; hồ sơ và dữ liệu nghiệp
vụ vẫn do database của backend quản lý.

## 1. Cấu hình riêng trên máy

Dùng `.env` ở gốc repository. Nếu chưa có, sao chép `.env.example`; giữ nguyên
file đã được cấu hình. Không commit `.env` hoặc JSON service account.

Đặt JSON service account của Firebase vào `backend/src/assets/secrets/`, rồi
điền **tên file** trong `.env`:

```dotenv
FIREBASE_CREDENTIAL=<ten-file-adminsdk>.json
```

Backend cũng hỗ trợ `FIREBASE_CREDENTIAL_JSON` cho môi trường triển khai.
Nội dung private key chỉ được lưu trong cấu hình bí mật của môi trường đó.

Cấu hình Firebase Web của frontend trong cùng `.env`, dùng cùng Firebase
project với service account:

```dotenv
VITE_FIREBASE_API_KEY=<firebase-web-api-key>
VITE_FIREBASE_AUTH_DOMAIN=<project-id>.firebaseapp.com
VITE_FIREBASE_PROJECT_ID=<project-id>
VITE_FIREBASE_APP_ID=<firebase-web-app-id>

FIREBASE_AUTH_EMULATOR_HOST=
VITE_FIREBASE_AUTH_EMULATOR_URL=
```

Google provider và domain đăng nhập phải được cấu hình trong Firebase project.
Không đưa service account/private key vào biến `VITE_*` hoặc mã frontend.

## 2. Khởi động backend chính và frontend

Dùng database/Redis đã cấu hình trong `.env`; kiểm tra Redis trước khi chạy
backend. Nếu Redis local chưa chạy, từ gốc repository:

```powershell
docker compose -f docker-compose.infra.yaml up -d --no-deps redis
docker exec p146_redis redis-cli ping
```

Terminal backend, từ gốc repository:

```powershell
Remove-Item Env:FIREBASE_AUTH_EMULATOR_HOST -ErrorAction SilentlyContinue
cd backend
uv run uvicorn src.main:app --reload --host 127.0.0.1 --port 8000
```

Terminal frontend riêng, từ gốc repository:

```powershell
Remove-Item Env:VITE_FIREBASE_AUTH_EMULATOR_URL -ErrorAction SilentlyContinue
$env:VITE_BACKEND_URL = 'http://127.0.0.1:8000'
$env:VITE_CHAT_TRANSPORT = 'http'
$env:VITE_API_MOCKS = 'off'
npm --prefix frontend run dev -- --host 127.0.0.1 --port 5173 --strictPort
```

Các terminal này không được giữ giá trị emulator từ một phiên demo trước.
Không dùng `src.demo.main:app` để kiểm thử Firebase/backend chính.

## 3. Kiểm tra đăng nhập

- Chủ xe: `http://localhost:5173`.
- Chủ xưởng: `http://localhost:5173/workshop/login`.
- API docs: `http://localhost:8000/docs`.
- Dùng hai profile trình duyệt để kiểm thử hai vai trò độc lập.
- Đăng nhập Google phải gọi API sign-in của backend chính bằng Firebase ID
  token thật, không dùng token tự tạo hoặc header thay thế xác thực.
- Tài khoản chưa hoàn thành hồ sơ đi vào onboarding; tài khoản đã hoàn thành
  đi vào dashboard tương ứng. Xác minh xe/xưởng còn phụ thuộc dịch vụ OEM và
  database theo cấu hình; Firebase thật không làm dữ liệu OEM trở thành thật.
- Tải lại trang kiểm tra giữ phiên; đăng xuất kiểm tra API riêng tư từ chối
  request không có token hợp lệ.
