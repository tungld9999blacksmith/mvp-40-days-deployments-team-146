# Kiến trúc EV Care

Trang này trước đây mô tả cấu trúc `backend/app` ở giai đoạn đầu (chỉ có chat mẫu, chưa có database) và đã lỗi thời sau khi tái cấu trúc sang `backend/src`. Nội dung cũ được bỏ để tránh hiểu sai.

| Cần gì | Đọc |
| --- | --- |
| Kiến trúc hiện tại: context, container, module, luồng chính, Celery, triển khai | [../architecture.md](../architecture.md) |
| Bảo mật, phi chức năng, vòng đời trạng thái, độ tin cậy, khoảng trống | [../architecture-deep-dive.md](../architecture-deep-dive.md) |
| Tài liệu từng công nghệ (OEM M2M, outbox, observability, Celery, LLM, prompt, PII) | [../technology/README.md](../technology/README.md) |
| Thiết kế chi tiết tính năng | [../designs/](../designs/) và [../specs/](../specs/) |

## Bảng chuyển đường dẫn từ template cũ

Tài liệu khóa học trong `docs/guide`, README boilerplate và nhật ký lịch sử có thể nhắc đường dẫn cũ; dùng bảng này để đối chiếu.

| Trước | Hiện tại |
| --- | --- |
| `src/frontend/` | `frontend/` |
| `src/main.py`, `src/config.py` | `backend/src/main.py`, `backend/src/config.py` |
| `src/api/routes.py` | `backend/src/modules/*/route.py` |
| `src/agents/` | `backend/src/agents/` |
| `src/services/llm.py` | `backend/src/infrastructure/llm/` |
| `backend/app/*` (bản tái cấu trúc đầu) | `backend/src/{modules,agents,infrastructure,common}` |
| `tests/test_agents/`, `tests/test_api/` | `backend/tests/` |
