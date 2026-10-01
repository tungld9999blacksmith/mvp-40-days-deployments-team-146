# EV Care — Sơ đồ kiến trúc

## Luồng đang hoạt động

```mermaid
flowchart LR
    UI[React UI] --> Mock[Dữ liệu mock trong frontend]
    Client[API client] --> API[FastAPI assistant router]
    API --> Service[Assistant service]
    Service --> Graph[LangGraph]
    Graph --> Nodes[Analyze / Respond mẫu]
```

Các trang UI hiện chưa gọi API. API client trong sơ đồ là bên gọi HTTP độc lập, ví dụ Swagger.

## Hướng phát triển

```mermaid
flowchart LR
    UI[React features] --> API[FastAPI routers]
    API --> Services[Services nghiệp vụ]
    API --> Assistant[Assistant service]
    Assistant --> Agent[LangGraph agent]
    Agent --> Tools[AI tools]
    Tools --> Services
    Services --> DB[(Database)]
    Agent --> Retrieval[Tra cứu tài liệu và nguồn]
    Retrieval --> Index[(Chỉ mục kiến thức)]
```

Database, retrieval và các service nghiệp vụ ngoài assistant mới có vị trí tổ chức, chưa được triển khai.
Xem [tài liệu kiến trúc](architecture/README.md).
