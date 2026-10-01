# ev-contracts

Thư viện dùng chung, chứa contract của API hệ thống xe điện: request/response schema và event schema (vd: event stream số km).

- `mock-ev-system` dùng để **phát** dữ liệu đúng contract.
- EV Care backend (`src/`) dùng để **parse/validate** dữ liệu nhận về, trong lớp client/adapter.

Chỉ đặt vào đây những gì thuộc contract giữa hai hệ thống. Không đặt business logic hay model nội bộ của từng bên.

Import: `from ev_contracts import ...`
