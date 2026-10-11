# Data access — `src/common/data_access/`

Repository dùng chung, không phụ thuộc entity: CRUD, tìm kiếm theo filter và 3 kiểu phân trang (offset, keyset, cursor).
Mọi thứ được export từ `src.common.data_access`:

```python
from src.common.data_access import (
    SQLModelRepository,                          # implementation trên SQLModel
    Filter, Op, SortField, eq, ne, lt, le, gt, ge, in_, not_in, like, ilike, is_null, is_not_null,
    OffsetPage, KeysetPage, CursorPage,          # kiểu kết quả phân trang
    EntityNotFoundError, UnknownFieldError, InvalidPageRequestError, InvalidCursorError,
)
```

| File | Nội dung |
|---|---|
| `base.py` | `Repository` — interface (port) mà service phụ thuộc vào; test có thể thay bằng fake in-memory |
| `sqlmodel_repository.py` | `SQLModelRepository` — implementation trên SQLModel/SQLAlchemy |
| `filters.py` | `Filter`, `Op`, `SortField` và các helper `eq()`, `in_()`… |
| `pagination.py` | `OffsetPage`, `KeysetPage`, `CursorPage` và codec cho cursor |
| `errors.py` | Các exception của layer |

## Mục lục

1. [Khai báo repository cho một entity](#1-khai-báo-repository-cho-một-entity)
2. [Session & transaction](#2-session--transaction)
3. [Filter và sort](#3-filter-và-sort)
4. [Các method CRUD & tìm kiếm](#4-các-method-crud--tìm-kiếm)
5. [Phân trang](#5-phân-trang)
6. [Mở rộng repository](#6-mở-rộng-repository)
7. [Lỗi & cách xử lý](#7-lỗi--cách-xử-lý)
8. [Checklist & lỗi thường gặp](#8-checklist--lỗi-thường-gặp)

---

## 1. Khai báo repository cho một entity

Kế thừa `SQLModelRepository[Model, KiểuId]` và gán `model`. Không cần viết lại method nào.

```python
from uuid import UUID

from src.common.data_access import SQLModelRepository


class BookingRepository(SQLModelRepository[Booking, UUID]):
    model = Booking
    default_order_by = ("-created_at",)  # tuỳ chọn: sort mặc định khi caller không truyền order_by
    max_page_size = 50                   # tuỳ chọn: mặc định 100
```

| Thuộc tính | Bắt buộc | Ý nghĩa |
|---|---|---|
| `model` | Có | Class SQLModel có `table=True`. Thiếu hoặc sai → `TypeError` ngay khi khởi tạo repo |
| `default_order_by` | Không | Sort dùng khi caller truyền `order_by=None` |
| `max_page_size` | Không | Giới hạn trên của `page_size` / `limit` trong các method phân trang |

Repository được khởi tạo với một `Session`:

```python
repo = BookingRepository(session)
repo.session  # truy cập lại session nếu cần query tự viết
```

Ví dụ thật trong repo: `src/common/core/maintenance/booking.py`, `src/common/core/conversation/conversation.py`.

---

## 2. Session & transaction

**Repository không bao giờ `commit`.** Các method ghi (`create`, `update`, `delete`…) chỉ `flush()` để có id sinh tự động
và giá trị `server_default`. Caller (service) sở hữu transaction và commit **một lần cho mỗi unit of work**.

```python
from sqlmodel import Session

def create_conversation(self, user_id: int, user_vehicle_id: UUID, title: str | None) -> Conversation:
    with Session(self._engine) as session:
        repo = ConversationRepository(session)
        conversation = repo.create({"user_id": user_id, "user_vehicle_id": user_vehicle_id, "title": title})
        session.commit()
        session.refresh(conversation)  # nạp lại trước khi trả object ra ngoài session
        return conversation
```

- Nhiều thao tác trong cùng một `with Session(...)` + một `commit()` → tất cả thành công hoặc rollback cùng nhau.
- Quên `commit()` → dữ liệu bị rollback khi session đóng, dù method đã trả về entity có id.
- Trong FastAPI có thể inject session qua `get_session` (`src/infrastructure/supabase/db.py`).

---

## 3. Filter và sort

### 3.1 Filter

Filter là value object thuần; repository kiểm tra tên field với các cột đã map của model trước khi sinh SQL,
nên có thể build filter trực tiếp từ query param mà không lộ thuộc tính tuỳ ý. Nhiều filter được **AND** với nhau.

| Helper | SQL | Ghi chú |
|---|---|---|
| `eq("status", "active")` | `status = 'active'` | `eq(f, None)` → `f IS NULL` |
| `ne("status", "done")` | `status != 'done'` | `ne(f, None)` → `f IS NOT NULL` |
| `lt` / `le` / `gt` / `ge` | `<` / `<=` / `>` / `>=` | |
| `in_("region", ["HN", "HCM"])` | `region IN (...)` | List rỗng → luôn **false** (không trả dòng nào) |
| `not_in("region", [...])` | `region NOT IN (...)` | List rỗng → luôn **true** (không lọc) |
| `like("name", "VF%")` | `LIKE` | Phân biệt hoa thường |
| `ilike("name", "%vin%")` | `ILIKE` | Không phân biệt hoa thường |
| `is_null("deleted_at")` / `is_not_null(...)` | `IS NULL` / `IS NOT NULL` | |

Mọi tham số `filters` nhận một trong ba dạng (`FilterSpec`):

```python
repo.search(filters=[eq("status", "active"), in_("region", ["HN", "HCM"])])  # list Filter
repo.search(filters={"status": "active", "region": "HN"})                    # dict = các eq() AND lại
repo.search(filters=None)                                                    # không lọc
```

Với `like` / `ilike`, nếu pattern lấy từ input người dùng thì escape `%` và `_` trước khi ghép.

### 3.2 Sort

Tham số `order_by` (`SortSpec`) nhận chuỗi, `SortField`, hoặc list của chúng:

```python
order_by="created_at"                         # tăng dần
order_by="-created_at"                        # giảm dần (tiền tố "-")
order_by=("-last_message_at", "-id")          # nhiều cột
order_by=[SortField("created_at", descending=True)]
```

- `order_by=None` → dùng `default_order_by` của repository.
- **Khoá chính luôn được nối vào cuối** làm tie-breaker (tăng dần) nếu chưa có, nên thứ tự luôn xác định.
  Muốn khoá chính giảm dần thì ghi rõ, ví dụ `("-created_at", "-id")`.
- Tên cột sai → `UnknownFieldError`. Khi cho client chọn cột sort, nên giới hạn bằng whitelist các cột có index.

---

## 4. Các method CRUD & tìm kiếm

### 4.1 Create

| Method | Trả về | Mô tả |
|---|---|---|
| `create(entity)` | `Model` | Insert một entity. Nhận instance `Model` **hoặc** dict field → giá trị |
| `create_many(entities)` | `list[Model]` | Insert nhiều entity trong một lần flush. Iterable rỗng → `[]` |

```python
booking = repo.create({"user_id": 1, "workshop_id": workshop_id, "status": BookingStatus.PENDING})
booking.id          # đã có sau flush
booking.created_at  # server_default đã được refresh

repo.create(Booking(user_id=1, workshop_id=workshop_id))  # truyền instance cũng được

repo.create_many([{"user_id": 1, ...}, {"user_id": 2, ...}])
```

Dict chứa key không phải cột → `UnknownFieldError`. Kiểu khác dict/instance → `TypeError`.

### 4.2 Read

| Method | Trả về | Mô tả |
|---|---|---|
| `get(id)` | `Model \| None` | Lấy theo khoá chính |
| `get_or_raise(id)` | `Model` | Như `get`, thiếu → `EntityNotFoundError` |
| `exists(filters)` | `bool` | Có ít nhất một dòng khớp (`LIMIT 1`) |
| `count(filters)` | `int` | Số dòng khớp |

```python
booking = repo.get(booking_id)
booking = repo.get_or_raise(booking_id)

repo.exists({"user_id": user_id, "status": BookingStatus.PENDING})
repo.count([eq("workshop_id", workshop_id), ge("scheduled_at", start)])
```

Khoá chính phức hợp: truyền tuple hoặc dict cho `get`, giống `Session.get` của SQLAlchemy.

### 4.3 Search

| Method | Trả về | Mô tả |
|---|---|---|
| `find_by(field, value, *, order_by)` | `list[Model]` | Mọi dòng `field == value` |
| `find_one_by(field, value)` | `Model \| None` | Dòng đầu tiên `field == value` |
| `find_in(field, values, *, order_by)` | `list[Model]` | Mọi dòng `field IN values`; `values` rỗng → `[]` (không query, nhưng vẫn kiểm tra tên field) |
| `search(filters, *, order_by, limit, offset)` | `list[Model]` | Truy vấn tổng quát: filter AND + sort + limit/offset |
| `find_one(filters, *, order_by)` | `Model \| None` | Dòng đầu tiên khớp filter theo thứ tự sort |

```python
repo.find_by("user_id", user_id, order_by="-created_at")
repo.find_one_by("email", email)

found = {m.id: m for m in ChatMessageRepository(session).find_in("id", ids)}

repo.search(
    filters=[eq("conversation_id", conv_id), in_("role", [MessageRole.USER, MessageRole.ASSISTANT])],
    order_by="-seq",
    limit=20,
)

latest = repo.find_one({"conversation_id": conv_id}, order_by="-seq")
```

`search(limit=..., offset=...)` **không** kiểm tra `max_page_size`. Khi phục vụ API cho client, dùng các method
`paginate_*` ở §5 thay vì tự ghép `limit/offset`.

### 4.4 Update

| Method | Trả về | Mô tả |
|---|---|---|
| `update(entity, values)` | `Model` | Gán `values` lên entity đã load, flush rồi refresh |
| `update_by_id(id, values)` | `Model` | Load theo id rồi `update`; thiếu → `EntityNotFoundError` |

```python
booking = repo.get_or_raise(booking_id)
repo.update(booking, {"status": BookingStatus.CONFIRMED, "note": "OK"})

repo.update_by_id(booking_id, {"status": BookingStatus.CANCELLED})
session.commit()
```

- Key không phải cột → `UnknownFieldError`.
- Không được đổi khoá chính → `ValueError`.
- Giá trị được gán bằng `setattr`, **không** chạy validation Pydantic (table model của SQLModel không validate khi gán).
  Validate ở schema request trước khi gọi repository.

### 4.5 Delete

| Method | Trả về | Mô tả |
|---|---|---|
| `delete(entity)` | `None` | Xoá entity đã load |
| `delete_by_id(id)` | `bool` | Xoá theo id; `False` khi không có dòng nào |

```python
if not repo.delete_by_id(booking_id):
    raise errors.BookingNotFound()
session.commit()
```

Đây là hard delete. Cần soft delete thì xem §6.

---

## 5. Phân trang

| Kiểu | Method | Kết quả | Khi nào dùng |
|---|---|---|---|
| Offset | `paginate_offset` | `OffsetPage` | Bảng admin có số trang, nhảy tới trang N, cần tổng số dòng. Dữ liệu ít / trang nông |
| Keyset | `paginate_keyset` | `KeysetPage` | Job nội bộ / batch quét toàn bảng; caller tự giữ giá trị khoá |
| Cursor | `paginate_cursor` | `CursorPage` | API cho client: infinite scroll, feed, danh sách hội thoại. Đi được cả tới và lui |

Cả ba đều nhận `filters` và `order_by` như §3 và kiểm tra kích thước trang: `1 <= page_size/limit <= max_page_size`,
sai → `InvalidPageRequestError`.

### 5.1 Offset — `paginate_offset`

```python
page = repo.paginate_offset(
    page=2,                     # bắt đầu từ 1
    page_size=20,
    filters={"workshop_id": workshop_id},
    order_by="-created_at",
    with_total=True,            # False để bỏ câu COUNT
)
```

`OffsetPage`:

| Thuộc tính | Kiểu | Ý nghĩa |
|---|---|---|
| `items` | `list[Model]` | Các dòng của trang |
| `page`, `page_size` | `int` | Tham số đã dùng |
| `total` | `int \| None` | Tổng số dòng khớp; `None` khi `with_total=False` |
| `total_pages` | `int \| None` | Tính từ `total` |
| `has_next` | `bool \| None` | `None` khi không có `total` |
| `has_previous` | `bool` | `page > 1` |

- `page < 1` → `InvalidPageRequestError`. Trang vượt quá cuối → `items` rỗng, không lỗi.
- `with_total=True` chạy thêm một câu `COUNT`. Bảng lớn mà không cần tổng thì đặt `False`.
- Nhược điểm: `OFFSET` lớn chậm dần; nếu có dòng được thêm/xoá giữa hai request, dòng có thể bị lặp hoặc bỏ sót.

### 5.2 Keyset — `paginate_keyset`

Caller truyền giá trị các cột sort của **dòng cuối cùng đã thấy**, nhận các dòng **đứng sau** nó.
Nhanh ở mọi độ sâu (dùng index, không `OFFSET`).

```python
key = None
while True:
    page = repo.paginate_keyset(limit=100, after=key, filters={"status": "active"}, order_by="created_at")
    for row in page.items:
        process(row)
    if not page.has_next:
        break
    key = page.next_key        # {"created_at": datetime(...), "id": UUID(...)}
```

`KeysetPage`:

| Thuộc tính | Kiểu | Ý nghĩa |
|---|---|---|
| `items` | `list[Model]` | Các dòng của trang |
| `limit` | `int` | Kích thước trang |
| `has_next` | `bool` | Còn dòng phía sau |
| `next_key` | `dict \| None` | Giá trị khoá của dòng cuối; truyền lại làm `after`. `None` khi hết |

Quy tắc của `after`:

- Phải chứa **đúng** các cột sort **kể cả khoá chính** được nối thêm (ví dụ `order_by="created_at"` → cần `created_at` và `id`).
  Thiếu/thừa key hoặc có giá trị `None` → `InvalidPageRequestError`. Cách an toàn nhất là luôn dùng nguyên `page.next_key`.
- Giữ nguyên `filters` và `order_by` giữa các trang.

### 5.3 Cursor — `paginate_cursor`

Keyset được gói thành một token URL-safe, mang theo cả hướng đi (`next` / `prev`) và "dấu vân tay" của thứ tự sort.
Client chỉ cần gửi lại token, không cần biết cột sort.

```python
page = repo.paginate_cursor(
    limit=20,
    cursor=cursor,                                   # None cho trang đầu
    filters=[eq("user_id", user_id)],
    order_by=("-last_message_at", "-id"),
)
page.items, page.next_cursor, page.prev_cursor, page.has_next, page.has_previous
```

`CursorPage`:

| Thuộc tính | Kiểu | Ý nghĩa |
|---|---|---|
| `items` | `list[Model]` | Luôn theo thứ tự `order_by`, kể cả khi đi lùi |
| `limit` | `int` | Kích thước trang |
| `has_next` / `has_previous` | `bool` | Còn trang sau / trước |
| `next_cursor` / `prev_cursor` | `str \| None` | Token để sang trang sau / về trang trước; `None` khi không còn |

Ví dụ endpoint (rút gọn; service lấy từ `modules/conversation/service.py`):

```python
# service
def list_conversations(self, user_id: int, limit: int, cursor: str | None):
    with Session(self._engine) as session:
        page = ConversationRepository(session).paginate_cursor(
            limit=limit, cursor=cursor, filters=[eq("user_id", user_id)], order_by=("-last_message_at", "-id")
        )
    return page.items, page.next_cursor, page.has_next

# router
@router.get("/conversations")
def list_conversations(limit: int = Query(20, ge=1, le=100), cursor: str | None = None, ...):
    items, next_cursor, has_more = service.list_conversations(user.id, limit, cursor)
    return {"items": items, "next_cursor": next_cursor, "has_more": has_more}
```

Lưu ý:

- Cursor gắn với thứ tự sort. Gửi cursor cùng `order_by` khác → `InvalidCursorError`. Token hỏng/không giải mã được
  → `InvalidCursorError`.
- Token chỉ là base64 của JSON, **không mã hoá, không ký**. Không đặt dữ liệu nhạy cảm vào cột sort, và luôn
  áp `filters` phân quyền (ví dụ `user_id`) ở server: client sửa token cũng không thoát được filter.
- `has_previous` ở trang đi tới (và `has_next` ở trang đi lùi) được suy ra từ việc có cursor, không query lại.
  Vì vậy trang đầu tiên mở bằng một cursor `next` luôn có `has_previous=True`.
- Nếu các dòng bị xoá sau khi cấp cursor và trang trả về rỗng, `prev_cursor` vẫn neo ở vị trí cũ để client quay lại được.
- Giá trị trong cursor giữ đúng kiểu `UUID`, `datetime`, `date`, `time`, `Decimal`. Enum được lưu bằng `.value`.

### 5.4 Ràng buộc chung của keyset & cursor

- **Cột sort phải NOT NULL.** Cột nullable → `InvalidPageRequestError` (`NULL` làm hỏng phép so sánh). Cần sort theo
  cột nullable thì dùng `paginate_offset`, hoặc đổi cột thành NOT NULL với giá trị mặc định.
- Khoá chính luôn được nối vào làm tie-breaker nên không dòng nào bị lặp hay bỏ sót, kể cả khi nhiều dòng trùng giá trị sort.
- Tạo index phủ đúng thứ tự sort, ví dụ `(user_id, last_message_at DESC, id DESC)`, để truy vấn không phải quét bảng.

---

## 6. Mở rộng repository

### 6.1 Phạm vi mặc định — override `_base_query`

`_base_query()` là `SELECT` khởi đầu của mọi truy vấn đọc (`exists`, `count`, `search`, `find_*`, `paginate_*`).
Override để thêm điều kiện luôn áp dụng, ví dụ soft delete:

```python
class WorkshopRepository(SQLModelRepository[Workshop, UUID]):
    model = Workshop

    def _base_query(self):
        return super()._base_query().where(Workshop.deleted_at.is_(None))
```

`get`, `get_or_raise`, `update_by_id`, `delete_by_id` dùng `Session.get` nên **không** đi qua `_base_query`.
Nếu cần phạm vi cho cả các method này thì override chúng hoặc dùng `find_one({"id": ...})`.

### 6.2 Thêm method riêng cho entity

Truy vấn đặc thù (join, aggregate, `GROUP BY`) viết thành method trên repository con, dùng `self.session`:

```python
from sqlmodel import func, select

class BookingRepository(SQLModelRepository[Booking, UUID]):
    model = Booking

    def count_by_status(self, workshop_id: UUID) -> dict[BookingStatus, int]:
        stmt = (
            select(Booking.status, func.count())
            .where(Booking.workshop_id == workshop_id)
            .group_by(Booking.status)
        )
        return dict(self.session.exec(stmt).all())
```

### 6.3 Test

Service nên phụ thuộc vào kiểu `Repository[Model, Id]` (port trong `base.py`) khi muốn thay bằng fake in-memory trong unit test.
Test tích hợp có thể dùng `SQLModelRepository` thật với SQLite in-memory. Cách chạy test: xem [backend/guide/testing.md](../../guide/testing.md).

---

## 7. Lỗi & cách xử lý

Mọi lỗi kế thừa `DataAccessError`.

| Exception | Kế thừa thêm | Khi nào | Gợi ý HTTP |
|---|---|---|---|
| `EntityNotFoundError` | — | `get_or_raise`, `update_by_id` không tìm thấy id. Có `.model_name`, `.entity_id` | 404 |
| `UnknownFieldError` | `ValueError` | Filter / sort / dict create-update / key keyset tham chiếu cột không tồn tại. Có `.field` | 400 (nếu do input) |
| `InvalidPageRequestError` | `ValueError` | `page < 1`, kích thước trang ngoài `[1, max_page_size]`, `after` sai, cột sort nullable | 400 / 422 |
| `InvalidCursorError` | `ValueError` | Cursor hỏng, bị sửa, hoặc cấp cho thứ tự sort khác | 400 |

Hiện chưa có exception handler toàn cục cho các lỗi này: service hoặc router phải bắt và đổi sang lỗi domain / `HTTPException`.

```python
from src.common.data_access import InvalidCursorError

try:
    page = repo.paginate_cursor(limit=limit, cursor=cursor, filters=filters, order_by=order_by)
except InvalidCursorError as exc:
    raise HTTPException(status_code=400, detail="Invalid cursor") from exc
```

---

## 8. Checklist & lỗi thường gặp

- [ ] Đã `session.commit()` sau các thao tác ghi; repository chỉ flush.
- [ ] Gọi `session.refresh(obj)` sau commit nếu trả object ra ngoài session (tránh truy cập thuộc tính đã expire).
- [ ] API trả danh sách cho client dùng `paginate_cursor` (hoặc `paginate_offset` khi cần số trang), không dùng `search` với `limit` tuỳ ý.
- [ ] Cột sort của keyset/cursor là NOT NULL và có index phù hợp.
- [ ] Giữ nguyên `filters` + `order_by` giữa các trang.
- [ ] Filter phân quyền (`user_id`, `workshop_id`…) luôn được thêm ở server, không lấy từ cursor.
- [ ] Bắt `InvalidCursorError` / `InvalidPageRequestError` và trả 400.
- [ ] `in_(field, [])` không trả gì; `not_in(field, [])` không lọc gì. Kiểm tra list rỗng nếu đó không phải ý định.
