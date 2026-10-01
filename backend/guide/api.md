# Hướng dẫn cấu trúc backend và thiết kế API

## Mục tiêu

Backend sử dụng hai nguyên tắc:

- **Vertical slice**: mỗi module đại diện cho một feature hoặc use case và chứa các thành phần cần thiết cho feature đó.
- **Clean Architecture**: business rule không phụ thuộc vào FastAPI, ORM, Redis, Firebase hoặc SDK của nhà cung cấp.

Vertical slice là cách tổ chức theo feature; Clean Architecture là quy tắc phụ thuộc. Hai nguyên tắc này bổ trợ cho nhau.

## Cấu trúc thư mục

```text
backend/
  src/
    common/
      /shared/
        core_entity.py
      config.py
      database.py
      security.py
      exceptions.py
      exception_handlers.py

    infrastructure/
      postgres/
      redis/
      pubsub/
      firebase/
      llm/

    modules/
      appointments/
        domain.py
        schemas.py
        ports.py
        repository.py
        service.py
        route.py
        dependencies.py
      customers/
      workshops/
      vehicles/
      warranty/
      notifications/
    agents/
      /business_agent/
        /tools/
          /rag/
        /prompt/
        /router/
        agent.py
```

### Trách nhiệm của từng khu vực

- `common/`: thành phần dùng chung, giữa các module.
- `modules/`: business rule và use case, được tổ chức theo `vertical slice`.
- `infrastructure/`: code kết nối hệ thống bên ngoài như PostgreSQL, Redis, Pub/Sub, Firebase và LLM provider.
- `route.py`: khai báo endpoint, đọc request context và gọi service; không đặt business rule tại đây.

## Trách nhiệm của các file trong module

- `domain.py`: entity, value object, enum và business rule cốt lõi. Không import FastAPI, SQLAlchemy session, Redis client hoặc SDK bên ngoài.
- `models.py`: Pydantic request/response schema, input validation và serialization.
- `repository.py`: thao tác persistence của module. Nếu đây là interface thì đặt trong `ports.py`; nếu đây là implementation PostgreSQL thì đặt trong `infrastructure/`.
- `ports.py`: interface của repository.
- `service.py`: orchestration của một use case, phối hợp domain và các port. Service không nên tạo trực tiếp database client, Redis client hoặc SDK.
- `route.py`: HTTP method, path, status code, dependency injection và response schema.
- `dependencies.py`: hàm khởi tạo service và inject dependency cho FastAPI.
- `errors.py`: domain/application exception riêng của module, nếu module có exception đặc thù.

Không tạo `utility.py` theo mặc định. Hàm chỉ dùng trong một module đặt gần nơi sử dụng; hàm dùng chung đặt trong `common/` và phải có phạm vi rõ ràng.

## Quy tắc phụ thuộc

```text
route -> service -> ports
                       ^
                       |
infrastructure --------+
```

- Domain không phụ thuộc infrastructure.
- Service phụ thuộc abstraction trong `ports.py`, không phụ thuộc implementation cụ thể.
- Infrastructure implement các port và được wire thông qua `dependencies.py`.
- Không import repository của module này vào module khác nếu có thể dùng một application service hoặc port rõ ràng hơn.

## Database và hệ thống bên ngoài

Với nghiệp vụ khách hàng, xe, bảo hành và lịch hẹn:

- PostgreSQL là database chính cho transaction và quan hệ giữa các entity.
- `pgvector` có thể được dùng chung trong PostgreSQL cho semantic search nếu nhu cầu chưa lớn.
- Redis chỉ dùng cho cache, rate limit, distributed lock hoặc dữ liệu tạm thời; không coi Redis là source of truth.
- Pub/Sub dùng cho event và notification bất đồng bộ.
- Firebase Authentication dùng cho identity; backend vẫn phải xác minh token và authorization.
- Firestore chỉ nên thêm vào khi có nhu cầu document/realtime rõ ràng. Không để PostgreSQL và Firestore cùng đóng vai trò database chính.

## Phân quyền và tenant isolation

Mỗi request cần xác định user, role và phạm vi dữ liệu. Tối thiểu cần phân biệt:

- customer: chỉ xem và thao tác trên xe, lịch hẹn và hồ sơ của mình;
- workshop staff: chỉ xem dữ liệu thuộc workshop mình;
- workshop admin: quản lý nhân viên và lịch của workshop;
- system admin: quyền quản trị theo chính sách của hệ thống.

Service hoặc repository phải áp dụng `user_id`, `workshop_id` hoặc `tenant_id` trong các query cần thiết. Không chỉ kiểm tra quyền ở frontend.

## Quy tắc cho lịch hẹn

API đặt lịch phải quy định rõ:

- lưu thời gian trong UTC và chuyển đổi timezone ở lớp API/UI;
- transaction và constraint để ngăn đặt trùng khung giờ;
- idempotency key cho request tạo lịch có thể bị retry;
- trạng thái lịch hẹn, quy tắc đổi lịch và hủy lịch;
- cách xử lý hai request đồng thời cùng đặt một slot;
- audit log cho thao tác tạo, đổi và hủy lịch.

## Error handling và logging

- Domain exception được định nghĩa rõ ràng, ví dụ `AppointmentSlotUnavailable`.
- Service ném domain/application exception thay vì trả trực tiếp HTTP response.
- Global exception handler chuyển exception thành HTTP response phù hợp.
- Lỗi không dự kiến phải được log kèm `request_id`, nhưng không trả stack trace cho client.
- Không log access token, mật khẩu, thông tin cá nhân không cần thiết hoặc nội dung nhạy cảm của người dùng.

## Cách phát triển một API

1. Đọc API spec và ERD trong `docs/specs/`, xác định actor, permission, input, output, status code và error case.
2. Xác định entity, invariant, enum và business rule trong `domain.py`.
3. Định nghĩa request/response schema trong `schemas.py`.
4. Định nghĩa port cần thiết trong `ports.py`.
5. Viết service cho use case, bao gồm transaction boundary và authorization rule.
6. Viết infrastructure adapter cho PostgreSQL, Redis, Pub/Sub, Firebase hoặc LLM.
7. Wire dependency trong `dependencies.py` và tạo endpoint trong `route.py`.
8. Viết unit test cho domain/service và integration test cho route/repository.
9. Kiểm tra OpenAPI, status code, pagination, filtering, authentication và error response.

## Tiêu chí chia module

- **Cohesion**: các entity và use case trong cùng module phải có liên quan nghiệp vụ cao.
- **Coupling**: module khác chỉ phụ thuộc vào contract cần thiết, không truy cập trực tiếp database nội bộ của nhau.
- Chỉ đưa một entity vào `common/` khi nó thực sự dùng chung và có ý nghĩa ổn định. Không dùng `common/` để gom code chưa rõ chủ sở hữu.

Mục tiêu của cấu trúc này là giữ business rule để test, thay đổi infrastructure ít ảnh hưởng đến use case và cho phép mỗi feature được phát triển độc lập trong phạm vi hợp lý.