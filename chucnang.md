# Chức năng dự án EV Care

EV Care là nền tảng hậu mãi cho xe điện VinFast. Có hai nhóm người dùng: **chủ xe** và **chủ xưởng / kỹ thuật viên dịch vụ**.

> Cập nhật: 29/09/2026, theo nhánh `develop` (đã merge `phuoctien`, `tungld-backend`, `thaidinh`).
>
> 02/10/2026: đã bỏ khỏi phạm vi **báo giá / duyệt báo giá**, **phiếu hỗ trợ** và **kết nối Discord**. Nhắc bảo dưỡng chỉ hiện trong mục Thông báo của app.

---

## Phân công

Nguyên tắc: **ai làm chức năng nào ở frontend thì làm luôn phần backend của chức năng đó**, gồm API, tác vụ nền và phần AI liên quan.

| Thành viên | Mảng phụ trách | Frontend | Backend |
|---|---|---|---|
| **Lê Đức Tùng** | Tài khoản, onboarding, xưởng dịch vụ | Đăng nhập, Khung ứng dụng, Dashboard kỹ thuật viên, Khách hàng | Xác thực + onboarding chủ xe, xác thực + onboarding chủ xưởng, giám sát, tác vụ nền của xưởng và phiên đăng nhập |
| **Mai Văn Trung** | Xe và bảo dưỡng | Tổng quan, Xe của tôi, Lịch sử dịch vụ, Thông báo | Xe của chủ xe, cài đặt nhắc bảo dưỡng, tích hợp hãng xe (OEM), đồng bộ OEM, gửi nhắc bảo dưỡng |
| **Đinh Kim Thái** | AI Trợ lý | AI Trợ lý, Ước tính chi phí | Hội thoại AI, LangGraph Agent, Retrieval, tool cho Agent, LLM, embedding |
| **Nguyễn Lê Phước Tiến** | Đặt lịch | Đặt lịch, Đặt lịch thành công | API đặt lịch, RAG Indexing |

---

## 1. Cách chạy

| Thành phần | Lệnh | Địa chỉ |
|---|---|---|
| Hạ tầng (mock-ev-system, Redis, Chroma) | `docker compose -f docker-compose.infra.yaml up -d` | 8100, 6379, 8001 |
| Backend (FastAPI) | `cd backend && uv run uvicorn src.main:app --reload --port 8000` | http://localhost:8000 (Swagger: `/docs`) |
| Frontend (React + Vite) | `cd frontend && npm install && npm run dev` | http://localhost:5173 |

Vite đã proxy `/api` và `/health` sang backend ở cổng 8000.

---

## 2. Frontend

Công nghệ: React 19, React Router 7, Tailwind CSS 4, lucide-react.

> **Lưu ý:** hiện tất cả các trang đều dùng **dữ liệu mock** trong `frontend/src/mocks/`, chưa gọi API backend. Chỉ có sẵn hàm `sendChat()` (`POST /api/v1/chat`) cho AI Trợ lý nhưng chưa được dùng. Đăng nhập cũng chỉ là giả lập: chọn vai trò trong `AuthContext`, không gọi Firebase.

### 2.1. Chung

| Trang | Đường dẫn | Chức năng | Người phụ trách |
|---|---|---|---|
| Đăng nhập | `/` | Form email/mật khẩu, "Ghi nhớ đăng nhập", chọn vai trò Chủ xe / Kỹ thuật viên | Lê Đức Tùng |
| Thông báo | `/notifications` | Danh sách thông báo (nhắc bảo dưỡng, lịch hẹn, khảo sát sau dịch vụ) | Mai Văn Trung |
| Khung ứng dụng | — | Sidebar theo vai trò, ô tìm kiếm, chuông thông báo, thông tin người dùng, Hỗ trợ, Đăng xuất | Lê Đức Tùng |

### 2.2. Chủ xe

| Trang | Đường dẫn | Chức năng | Người phụ trách |
|---|---|---|---|
| Tổng quan | `/dashboard` | Thẻ xe (VinFast VF6, biển số), số km còn lại tới mốc bảo dưỡng, trạng thái "Sắp đến hạn", lối tắt tới AI Trợ lý / Lịch sử dịch vụ / Bảo dưỡng | Mai Văn Trung |
| Xe của tôi | `/vehicle` | Thông tin xe, số km hiện tại, trạng thái bảo dưỡng và mốc tiếp theo, tình trạng pin (SoH) | Mai Văn Trung |
| Lịch sử dịch vụ | `/history` | Tất cả các lần bảo dưỡng / sửa chữa của xe | Mai Văn Trung |
| Đặt lịch | `/booking` | Chọn xưởng dịch vụ gần nhất, chọn ngày, khung giờ trống, xem tóm tắt và xác nhận | Nguyễn Lê Phước Tiến |
| Đặt lịch thành công | `/booking-success` | Mã đặt lịch, xưởng, thời gian hẹn, thời gian ước tính | Nguyễn Lê Phước Tiến |
| AI Trợ lý | `/ai` | Chat với AI về bảo dưỡng / bảo hành; bảng bên cạnh hiện thông tin xe, tiến độ bảo dưỡng, hành động nhanh | Đinh Kim Thái |
| Ước tính chi phí | `/estimate` | Danh sách dịch vụ AI gợi ý, chi phí ước tính và tổng tiền; kỹ thuật viên xác nhận trong 24 giờ làm việc | Đinh Kim Thái |

### 2.3. Kỹ thuật viên / Xưởng dịch vụ

| Trang | Đường dẫn | Chức năng | Người phụ trách |
|---|---|---|---|
| Dashboard kỹ thuật viên | `/technician` | Lịch hẹn hôm nay | Lê Đức Tùng |
| Khách hàng | `/customers` | Có trong menu nhưng **chưa có trang** (chuyển về trang đăng nhập) | Lê Đức Tùng |

---

## 3. Backend

Công nghệ: FastAPI, SQLModel / PostgreSQL (Supabase, dự phòng SQLite), Redis, Celery, Firebase Auth, LangGraph, ChromaDB / Qdrant / pgvector.

Tất cả API có tiền tố `/api/v1`.

### 3.1. Xác thực chủ xe

| Method | Endpoint | Chức năng | Người phụ trách |
|---|---|---|---|
| POST | `/oauth/sign-in` | Đăng nhập bằng Firebase (Google), đồng bộ tài khoản | Lê Đức Tùng |
| POST | `/oauth/logout` | Đăng xuất: ghi nhận sự kiện và thu hồi phiên ở nền | Lê Đức Tùng |
| GET | `/oauth/profile` | Lấy hồ sơ người dùng | Lê Đức Tùng |

### 3.2. Onboarding chủ xe

| Method | Endpoint | Chức năng | Người phụ trách |
|---|---|---|---|
| GET | `/onboarding` | Trạng thái onboarding hiện tại và dữ liệu đã lưu | Lê Đức Tùng |
| PUT | `/onboarding/profile` | Lưu thông tin cá nhân, vị trí gần nhất, đồng ý xử lý dữ liệu | Lê Đức Tùng |
| GET | `/onboarding/vehicle-models` | Danh sách dòng xe của hãng (cho dropdown) | Lê Đức Tùng |
| POST | `/onboarding/vehicle-verification` | Gửi thông tin xe sang hãng để xác minh quyền sở hữu | Lê Đức Tùng |

Quy tắc: xác minh xe bị giới hạn số lần sai (`VEHICLE_VERIFY_MAX_FAILED_ATTEMPTS`, mặc định 5). Dữ liệu onboarding dở dang được giữ `ONBOARDING_RETENTION_DAYS` ngày (mặc định 15). Có lưu phiên bản chính sách đồng ý (`CONSENT_POLICY_VERSION`).

### 3.3. Xe của chủ xe

| Method | Endpoint | Chức năng | Người phụ trách |
|---|---|---|---|
| GET | `/user-vehicles` | Danh sách xe đã xác minh, đang hoạt động | Mai Văn Trung |
| GET | `/user-vehicles/{id}` | Hồ sơ xe: định danh, thông số, bảo hành, số km, lần bảo dưỡng gần nhất | Mai Văn Trung |
| GET | `/user-vehicles/{id}/maintenance-status` | Trạng thái bảo dưỡng và mốc tiếp theo | Mai Văn Trung |

Trạng thái bảo dưỡng: `NORMAL`, `DUE_SOON` (còn ≤ 500 km hoặc ≤ 14 ngày), `OVERDUE`, `UNKNOWN` (chưa đồng bộ được dữ liệu từ hãng). Hệ thống tính theo cả km và thời gian (`KM_AND_TIME`), hoặc chỉ theo thời gian (`TIME_ONLY`).

Ngoài ra còn có module mẫu `/vehicles` (CRUD: tạo, liệt kê, xem, sửa, xoá xe), do Mai Văn Trung phụ trách.

### 3.4. Cài đặt nhắc bảo dưỡng

| Method | Endpoint | Chức năng | Người phụ trách |
|---|---|---|---|
| GET | `/notification-settings` | Xem công tắc nhắc, số ngày nhắc trước, kênh nhận | Mai Văn Trung |
| PUT | `/notification-settings` | Lưu các cài đặt trên | Mai Văn Trung |

Nhắc bảo dưỡng hiện trong mục Thông báo của app. Các kênh ngoài (Zalo, Telegram, SMS, Email) có trong danh sách nhưng chưa có adapter nên hiện "Sắp có".

### 3.5. Chủ xưởng dịch vụ

| Method | Endpoint | Chức năng | Người phụ trách |
|---|---|---|---|
| POST | `/workshop-owner/oauth/sign-in` | Đăng nhập Firebase (Google), đồng bộ tài khoản | Lê Đức Tùng |
| GET | `/workshop-owner/oauth/session` | Kiểm tra phiên (phát hiện phiên đã bị thu hồi) | Lê Đức Tùng |
| POST | `/workshop-owner/oauth/logout` | Đăng xuất, ghi audit, thu hồi phiên ở nền | Lê Đức Tùng |
| GET | `/workshop-owner/onboarding` | Trạng thái onboarding xưởng | Lê Đức Tùng |
| PUT | `/workshop-owner/onboarding/profile` | Lưu họ tên, số điện thoại, CCCD, đồng ý xử lý dữ liệu | Lê Đức Tùng |
| POST | `/workshop-owner/onboarding/workshop-verification` | Gửi dữ liệu hoạt động của xưởng sang hãng để xác minh | Lê Đức Tùng |

### 3.6. Tích hợp hãng xe (OEM)

| Method | Endpoint | Chức năng | Người phụ trách |
|---|---|---|---|
| POST | `/integrations/oem/webhooks` | Nhận tín hiệu "dữ liệu xe thay đổi" có chữ ký từ hãng, kích hoạt đồng bộ lại | Mai Văn Trung |

Khi phát triển, hệ thống hãng được giả lập bằng `mock-ev-system` (cổng 8100).

### 3.7. Hội thoại AI

| Method | Endpoint | Chức năng | Người phụ trách |
|---|---|---|---|
| POST | `/conversations` | Tạo cuộc hội thoại | Đinh Kim Thái |
| GET | `/conversations/{id}/messages` | Lấy danh sách tin nhắn | Đinh Kim Thái |
| POST | `/conversations/{id}/messages` | Thêm tin nhắn | Đinh Kim Thái |
| GET | `/conversations/{id}/search` | Tìm kiếm ngữ nghĩa trong tin nhắn (tin nhắn được embedding ở nền) | Đinh Kim Thái |

### 3.8. Giám sát

| Method | Endpoint | Chức năng | Người phụ trách |
|---|---|---|---|
| GET | `/health` | Kiểm tra backend còn sống | Lê Đức Tùng |
| GET | `/api/v1/health/dependencies` | Kiểm tra kết nối Redis, ChromaDB, database | Lê Đức Tùng |

---

## 4. AI Agent và RAG

- **LangGraph Agent** (`src/agents/graph.py`): `analyze` → định tuyến theo từ khoá → `rag_retrieval` (câu hỏi về bảo dưỡng, bảo hành, pin, chi phí, dòng VF…) hoặc `respond` (hội thoại chung). — *Phụ trách: Đinh Kim Thái*
- **Indexing** (`src/agents/tools/RAG/indexing/`): đọc PDF / HTML / MD / TXT, làm sạch, chia đoạn theo mục (tối ưu cho PDF bảo hành VinFast), tạo embedding, lưu vào ChromaDB hoặc Qdrant. — *Phụ trách: Nguyễn Lê Phước Tiến*
- **Retrieval** (`src/agents/tools/RAG/retrieval/`): viết lại câu hỏi bằng LLM, tìm kiếm hybrid (vector + BM25), rerank bằng FlashRank, sinh câu trả lời có trích dẫn nguồn. — *Phụ trách: Đinh Kim Thái*
- **Tool cho Agent**: `search_ev_knowledge`, `get_maintenance_schedule_rag` (lịch bảo dưỡng theo dòng xe và số km), `get_warranty_policy_rag` (chính sách bảo hành). — *Phụ trách: Đinh Kim Thái*
- **LLM đa nhà cung cấp**: OpenAI / OpenAI-compatible, Gemini, Anthropic. — *Phụ trách: Đinh Kim Thái*
- **Embedding đa nhà cung cấp**: OpenAI, Gemini, HuggingFace, local. — *Phụ trách: Đinh Kim Thái*

---

## 5. Tác vụ nền (Celery)

| Tác vụ | Lịch chạy | Chức năng | Người phụ trách |
|---|---|---|---|
| `oem.sync_all_vehicles` | Định kỳ (`oem_sync_interval_seconds`) | Kéo số km và lịch sử dịch vụ của mọi xe từ hãng | Mai Văn Trung |
| `reminder.send_all` | Hằng ngày (`reminder_job_hour`, giờ VN) | Gửi nhắc bảo dưỡng cho xe sắp đến hạn / quá hạn | Mai Văn Trung |
| `workshop.reconcile_verifications` | Mỗi 5 phút | Đưa lại vào hàng đợi các lần xác minh xưởng bị mất | Lê Đức Tùng |
| `workshop.purge_expired_onboarding` | 02:00 hằng ngày | Xoá onboarding xưởng dở dang đã hết hạn | Lê Đức Tùng |
| `workshop_auth.purge_events` | 02:30 hằng ngày | Xoá audit đăng nhập xưởng cũ hơn 60 ngày | Lê Đức Tùng |
| Thu hồi phiên | Theo sự kiện | Chạy nền khi chủ xe / chủ xưởng đăng xuất | Lê Đức Tùng |
| Embedding tin nhắn | Theo sự kiện | Chạy nền khi có tin nhắn hội thoại mới | Đinh Kim Thái |

---

## 6. Việc còn thiếu

| Việc cần làm | Người phụ trách |
|---|---|
| Nối trang Đăng nhập với Firebase + `/oauth/sign-in`, thêm luồng onboarding chủ xe và chủ xưởng | Lê Đức Tùng |
| Làm trang Khách hàng (`/customers`) và API cho trang này | Lê Đức Tùng |
| Nối Dashboard kỹ thuật viên với dữ liệu thật (lịch hẹn hôm nay) | Lê Đức Tùng |
| Nối Tổng quan, Xe của tôi với `/user-vehicles` | Mai Văn Trung |
| Làm API **lịch sử dịch vụ** và nối trang `/history` | Mai Văn Trung |
| Nối trang Thông báo với cài đặt nhắc bảo dưỡng và danh sách thông báo | Mai Văn Trung |
| Frontend gọi `POST /api/v1/chat` nhưng backend chưa có endpoint này (chỉ có `/conversations`): thống nhất API và nối trang AI Trợ lý | Đinh Kim Thái |
| Làm API ước tính chi phí từ dịch vụ AI gợi ý | Đinh Kim Thái |
| Làm API **đặt lịch** (xưởng gần nhất, khung giờ, xác nhận) và nối trang Đặt lịch | Nguyễn Lê Phước Tiến |
| Khai báo `html2text` trong dependency để các test RAG chạy được | Nguyễn Lê Phước Tiến |
