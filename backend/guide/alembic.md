# Sử dụng alembic để quản lý migration csdl

## Tạo migration tự động dựa trên model

```bash
alembic revision --autogenerate -m "create items table"
```

## Xem lại file migration sinh ra trong alembic/versions/ trước khi áp dụng rồi mới chạy:

```bash
alembic upgrade head
```

## Câu lệnh khác 

```bash
alembic current          # xem revision hiện tại
alembic history           # xem lịch sử migration
alembic downgrade -1      # rollback 1 bước
```