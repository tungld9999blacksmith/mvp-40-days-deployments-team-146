# EV Care — Sơ đồ kiến trúc

Các sơ đồ hiện hành nằm trong [architecture.md](architecture.md):

- Sơ đồ ngữ cảnh: mục 2
- Sơ đồ container (API, agent, Celery, outbox, OTel Collector, Postgres, Redis, Qdrant, OEM): mục 3
- Phân lớp backend: mục 4.1
- Luồng chat, agent LangGraph: mục 5.1, 5.2
- Đồng bộ OEM: mục 5.3
- Transactional outbox: mục 5.10
- Observability: mục 5.11
- Xác thực M2M với OEM: mục 5.12

Bản sơ đồ cũ (UI dùng mock, graph `analyze → respond`, "database chưa triển khai") đã lỗi thời và được bỏ.
