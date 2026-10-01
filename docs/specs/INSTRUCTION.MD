# Hướng dẫn sử dụng 3 loại tài liệu của dự án

Tài liệu dự án được quản lý bằng **Markdown trên GitHub**.

Có 3 loại tài liệu chính:

```text
PRD
 │
 ▼
Functional Specification
 │
 ├───────────────┐
 ▼               ▼
Frontend Spec   API Spec
```

## 1. PRD — Product Requirements Document

### Dùng để làm gì?

PRD mô tả:

- **Tại sao** chúng ta xây tính năng này.
- **Vấn đề gì** cần giải quyết.
- **Người dùng là ai**.
- **Sản phẩm cần cung cấp những gì**.

PRD tập trung vào **product và business**, không đi sâu vào code.

### Khi nào cần đọc?

Đọc PRD khi:

- Bạn mới bắt đầu làm một feature.
- Bạn chưa hiểu mục tiêu của feature.
- Bạn cần hiểu user/business requirement.

### Câu hỏi PRD trả lời

> **"Chúng ta đang xây cái gì và tại sao?"**

---

# 2. Functional Specification

### Dùng để làm gì?

Functional Spec mô tả **feature hoạt động như thế nào về mặt nghiệp vụ**.

Tài liệu thường gồm:

- User Story
- Use Case
- User Flow
- UI / Screen Flow
- Business Rules
- State / Status
- Error & Edge Cases
- Acceptance Criteria
- Terminology / Glossary

UI có thể được dùng để minh họa cho stakeholder dễ hiểu, nhưng trọng tâm vẫn là **business behavior**.

### Khi nào cần đọc?

Đọc Functional Spec trước khi bắt đầu implement feature.

Nó giúp bạn hiểu:

- User sẽ làm gì.
- System phải phản ứng thế nào.
- Business rule là gì.
- Trường hợp lỗi / ngoại lệ xử lý ra sao.
- Khi nào feature được xem là hoàn thành.

### Câu hỏi Functional Spec trả lời

> **"Feature này phải hoạt động như thế nào?"**

---

# 3. Frontend Specification

### Dùng để làm gì?

Frontend Spec mô tả **frontend sẽ triển khai feature như thế nào**.

Tài liệu thường gồm:

- Screen / Page
- Component
- UI behavior
- State management
- Validation
- Loading state
- Empty state
- Error state
- Navigation
- API integration
- Permission / visibility

### Khi nào cần đọc?

Đọc khi:

- Bạn làm frontend.
- Bạn cần biết UI phải hoạt động thế nào.
- Bạn cần biết frontend gọi API nào.
- Bạn cần xử lý loading / error / state ra sao.

### Câu hỏi Frontend Spec trả lời

> **"Frontend phải triển khai feature này như thế nào?"**

---

# 4. API Specification

### Dùng để làm gì?

API Spec mô tả **backend API cung cấp và xử lý như thế nào**.

Tài liệu thường gồm:

- Endpoint
- HTTP Method
- Request
- Request field & validation
- Authentication / Authorization
- Internal processing
- Database / Entity
- Business processing
- Error handling
- HTTP Status Code
- Response

### Khi nào cần đọc?

Đọc khi:

- Bạn làm backend.
- Bạn cần tích hợp API từ frontend.
- Bạn cần biết request / response.
- Bạn cần biết API trả lỗi như thế nào.
- Bạn cần biết API đọc / ghi dữ liệu gì.

### Câu hỏi API Spec trả lời

> **"Backend/API phải cung cấp và xử lý như thế nào?"**

---

# 5. Thứ tự đọc tài liệu

Khi nhận một feature mới, hãy đọc theo thứ tự:

```text
1. PRD
   ↓
2. Functional Specification
   ↓
3. Frontend Specification / API Specification
   ↓
4. Code
```

### Ví dụ

Feature:

> AI nhắc lịch bảo dưỡng

Bạn sẽ đọc:

```text
PRD
→ Hiểu mục tiêu và vấn đề cần giải quyết

Functional Spec
→ Hiểu user flow, business rule và acceptance criteria

Frontend Spec
→ Biết UI và frontend behavior

API Spec
→ Biết API request / response / processing
```

---

# 6. Hai tài liệu kỹ thuật không được tự định nghĩa lại nghiệp vụ

Điểm rất quan trọng:

**Functional Spec là nguồn mô tả nghiệp vụ chính.**

Frontend Spec và API Spec phải **tuân theo Functional Spec**.

Ví dụ:

```text
Functional Spec
BR-001:
User chỉ được đặt lịch với vehicle thuộc tài khoản.
        │
        ├──> Frontend Spec
        │    → Không cho chọn vehicle của user khác
        │
        └──> API Spec
             → Backend phải kiểm tra ownership
```

Không nên để frontend và backend tự hiểu business rule theo hai cách khác nhau.

---

# 7. Khi tài liệu được cập nhật trên GitHub

Tất cả tài liệu được version bằng **Git commit**.

Khi tài liệu thay đổi:

1. Hãy xem **commit mới nhất** của file.
2. Đọc phần **Changed / Diff** để biết thay đổi gì.
3. Kiểm tra feature có ảnh hưởng tới công việc của bạn không.
4. Nếu có ảnh hưởng, cập nhật code / test / tài liệu liên quan.

### Quy tắc đơn giản

> **Không chỉ đọc file hiện tại. Khi có thông báo tài liệu thay đổi, hãy xem commit/diff để biết chính xác điều gì đã thay đổi.**

---

# 8. Khi bạn phát hiện tài liệu không đúng

Không tự ý sửa logic bằng cách im lặng.

Hãy:

```text
1. Tạo Issue / trao đổi với owner
        ↓
2. Xác nhận business requirement
        ↓
3. Cập nhật tài liệu
        ↓
4. Tạo Pull Request
        ↓
5. Review
        ↓
6. Merge
```

Nếu code khác tài liệu, cần xác định:

> **Code sai hay tài liệu sai?**

Không nên tự chọn một bên mà không xác nhận.

---

# 9. Quy tắc nhớ nhanh cho Intern

| Tài liệu | Câu hỏi |
|---|---|
| PRD | **Tại sao + xây cái gì?** |
| Functional Spec | **Feature hoạt động thế nào?** |
| Frontend Spec | **Frontend làm thế nào?** |
| API Spec | **Backend/API làm thế nào?** |

### Một câu dễ nhớ

> **PRD → Why / What**  
> **Functional → How về nghiệp vụ**  
> **Frontend → How ở UI**  
> **API → How ở Backend**

---

# 10. Checklist trước khi bắt đầu code

- [ ] Đã đọc PRD chưa?
- [ ] Đã đọc Functional Spec chưa?
- [ ] Đã hiểu User Flow chưa?
- [ ] Đã hiểu Business Rules chưa?
- [ ] Đã kiểm tra Acceptance Criteria chưa?
- [ ] Đã đọc Frontend / API Spec liên quan chưa?
- [ ] Đã kiểm tra commit mới nhất của tài liệu chưa?
- [ ] Có điểm nào chưa rõ đã hỏi owner chưa?

> **Nguyên tắc cuối cùng:** Nếu requirement chưa rõ, hãy hỏi trước khi code. Code đúng tài liệu quan trọng hơn code nhanh.
