# Hướng dẫn sử dụng tài liệu của dự án

Tài liệu dự án được quản lý bằng **Markdown trên GitHub**.

Có 6 loại tài liệu chính:

```text
PRD
 │
 ▼
Functional Specification
 │
 ├───────────────┬───────────────┬───────────────┐
 ▼               ▼               ▼               ▼
Frontend Spec   API Spec     Entity Spec     AI-Agent Spec

Platform Spec  → quy tắc dùng chung cho mọi feature
Design Doc     → thiết kế chi tiết cho một thay đổi lớn
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

Vị trí: [docs/product/PRD_EV_Care_MVP.md](../product/PRD_EV_Care_MVP.md), mục lục ở [docs/product/README.md](../product/README.md).

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

Đuôi file: `.ff.md`.

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

Đuôi file: `.fe.md`. Khi làm UI, đọc thêm [DESIGN.md](../../DESIGN.md) ở gốc repo: file này quy định font, màu, spacing và hướng thẩm mỹ. Muốn khác DESIGN.md thì phải hỏi owner trước.

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

Đuôi file: `.api.md`.

---

# 5. Entity Specification

### Dùng để làm gì?

Entity Spec mô tả **một đối tượng dữ liệu** (bảng, quan hệ, ràng buộc) mà feature đọc hoặc ghi.

Tài liệu thường gồm:

- Entity ID (`ENT-XXX`), tên, tên nghiệp vụ, version, status
- Mô tả, mục đích nghiệp vụ, scope
- Danh sách field, kiểu dữ liệu, ràng buộc
- Quan hệ với entity khác
- Quy tắc vòng đời / trạng thái

### Khi nào cần đọc?

Đọc khi:

- Bạn thêm hoặc đổi bảng, cột, migration (Alembic).
- Bạn cần biết một field nghĩa là gì về nghiệp vụ.
- API Spec tham chiếu tới một entity.

### Câu hỏi Entity Spec trả lời

> **"Dữ liệu này gồm những gì và ràng buộc ra sao?"**

Đuôi file: `.entity.md`. Có hai nơi:

- Entity dùng chung của cả hệ thống: [docs/specs/entity/](entity/) (chia theo nhóm `identity`, `vehicle`, `workshop`, `maintenance`, `crm`, `conversation`, `knowledge`; tổng quan ở [core.entity.md](entity/core.entity.md); file cũ ở `archive/`).
- Entity gắn với một sprint: `sprint-N/entity/`.

---

# 6. AI-Agent Specification

### Dùng để làm gì?

AI-Agent Spec mô tả **hành vi của một AI Agent** cho một feature: agent phải hiểu gì, quyết định gì, dùng dữ liệu / knowledge / tool nào, trả lời ra sao, khi nào fallback hoặc chuyển cho người (Human-in-the-Loop).

Tài liệu tập trung vào **AI behavior và AI orchestration**, không thay thế Functional Spec, API Spec hay Frontend Spec.

### Khi nào cần đọc?

Đọc khi:

- Bạn làm agent, RAG, prompt, guardrail hoặc bộ đánh giá agent (`eval/`).
- Feature có phần LLM (nhắc lịch, báo giá qua chat, phân loại phản hồi...).

### Câu hỏi AI-Agent Spec trả lời

> **"AI phải hành xử thế nào, và khi nào phải dừng hoặc nhờ người?"**

Đuôi file: `.agent.md`, ID dạng `AI-XXX`. Vị trí: [docs/specs/ai-agent/](ai-agent/), đề xuất tổng quan ở [00-ai-agents-proposal.md](ai-agent/00-ai-agents-proposal.md).

---

# 7. Platform Specification

### Dùng để làm gì?

Platform Spec là các quy tắc **dùng chung cho mọi feature** và không thuộc riêng một user story, ví dụ định dạng lỗi API, danh mục mã lỗi, cách frontend hiển thị lỗi, hay API nhắn tin hội thoại.

### Khi nào cần đọc?

Đọc khi bạn viết API hoặc UI mới và cần theo đúng quy ước chung. API Spec của từng endpoint chỉ mô tả lỗi riêng của endpoint đó; định dạng chung nằm ở Platform Spec.

Vị trí: [docs/specs/platform/](platform/) (hiện có [error-handling.md](platform/error-handling.md) và [conversation-messaging.api.md](platform/conversation-messaging.api.md)).

---

# 8. Design Doc

### Dùng để làm gì?

Design Doc mô tả **thiết kế chi tiết cho một thay đổi lớn** (ví dụ báo giá hai tầng, đặt lịch tự tin nhắc), gồm các quyết định, phương án đã loại, các bước triển khai và rủi ro. Design Doc chạy trước hoặc song song với spec; sau khi chốt, nghiệp vụ phải được ghi lại vào Functional Spec.

Vị trí: [docs/designs/](../designs/). Các việc còn tồn đọng sau review hoặc QA được ghi trong [TODOS.md](../../TODOS.md).

---

# 9. Cấu trúc thư mục `docs/specs/`

```text
docs/specs/
├── INSTRUCTION.MD          ← file này
├── templates/              ← mẫu cho từng loại spec (xem mục 10)
├── entity/                 ← entity dùng chung toàn hệ thống
├── platform/               ← quy tắc dùng chung (lỗi, nhắn tin...)
├── ai-agent/               ← AI-Agent Spec (AI-001 ...)
├── mock-system/            ← ERD của hệ thống hãng xe giả lập (mock-ev-system)
├── phase2/                ← spec Phase 2, gom theo nhóm nghiệp vụ (booking, workshop-operations, …); mỗi tính năng có .ff/.api/.entity/.fe cạnh nhau
└── sprint-1 … sprint-4/    ← spec theo sprint
    ├── OUTLINE.MD          ← danh sách user story của sprint
    ├── feature-functional/ ← *.ff.md
    ├── frontend/           ← *.fe.md
    ├── api/                ← *.api.md
    └── entity/             ← *.entity.md
```

Các tài liệu liên quan nằm ngoài `docs/specs/`:

| Tài liệu | Nội dung |
|---|---|
| [docs/product/](../product/) | PRD |
| [docs/designs/](../designs/) | Design Doc |
| [DESIGN.md](../../DESIGN.md) | Design system (font, màu, spacing) |
| [ARCHITECTURE.md](../../ARCHITECTURE.md) và [docs/architecture-deep-dive.md](../architecture-deep-dive.md) | Kiến trúc, hành vi khi phụ thuộc gặp sự cố |
| [DEV_GUIDE.md](../../DEV_GUIDE.md) | Mục lục mọi hướng dẫn dev |
| [TODOS.md](../../TODOS.md) | Việc còn tồn đọng sau review / QA |

### Quy tắc đặt tên

```text
<id>-<sprint>-spec.<loại>.md

us-001-sprint-1-spec.ff.md       → Functional, user story US-001
us-001-sprint-1-spec.fe.md       → Frontend
us-001-sprint-1-spec.api.md      → API
us-001-sprint-1-spec.entity.md   → Entity
ai-007-sprint-4-spec.agent.md    → AI-Agent, AI-007
```

Một user story có thể có đủ các file `.ff`, `.fe`, `.api`, `.entity` cùng tiền tố. Khi cần tìm mọi spec của một user story, tìm theo ID (ví dụ `us-053`).

---

# 10. Viết spec mới: dùng template

Khi bắt đầu viết spec, copy mẫu từ [docs/specs/templates/](templates/) rồi điền vào, không tự dựng cấu trúc riêng:

| Loại | Template |
|---|---|
| Functional | [uk-xxx-sprint-x-spec.ff.md](templates/uk-xxx-sprint-x-spec.ff.md) |
| Frontend | [uk-xxx-sprint-x-spec.fe.md](templates/uk-xxx-sprint-x-spec.fe.md) |
| API | [uk-xxx-sprint-x-spec.api.md](templates/uk-xxx-sprint-x-spec.api.md) |
| Entity | [uk-xxx-sprint-x-spec.entity.md](templates/uk-xxx-sprint-x-spec.entity.md) |
| AI-Agent | [aa-xxx-sprint-x-spec.agent.md](templates/aa-xxx-sprint-x-spec.agent.md) |

Mỗi spec có bảng thông tin đầu file (ID, version, status, owner, ngày tạo, ngày cập nhật, spec liên quan). Giữ các trường này đúng: cập nhật `Version` và `Updated Date` mỗi khi sửa nội dung. `Status` dùng một trong `Draft / Review / Approved / Deprecated`.

---

# 11. Thứ tự đọc tài liệu

Khi nhận một feature mới, hãy đọc theo thứ tự:

```text
1. PRD
   ↓
2. Functional Specification
   ↓
3. Frontend Spec / API Spec / Entity Spec / AI-Agent Spec (tuỳ phần bạn làm)
   ↓
4. Platform Spec (nếu đụng tới lỗi, nhắn tin, quy ước chung)
   ↓
5. Code
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

Entity Spec
→ Biết bảng, field và ràng buộc dữ liệu

AI-Agent Spec
→ Biết agent hiểu gì, dùng tool nào, khi nào fallback
```

---

# 12. Các tài liệu kỹ thuật không được tự định nghĩa lại nghiệp vụ

Điểm rất quan trọng:

**Functional Spec là nguồn mô tả nghiệp vụ chính.**

Frontend Spec, API Spec, Entity Spec và AI-Agent Spec phải **tuân theo Functional Spec**.

Ví dụ:

```text
Functional Spec
BR-001:
User chỉ được đặt lịch với vehicle thuộc tài khoản.
        │
        ├──> Frontend Spec
        │    → Không cho chọn vehicle của user khác
        │
        ├──> API Spec
        │    → Backend phải kiểm tra ownership
        │
        └──> AI-Agent Spec
             → Agent không được đặt lịch cho xe không thuộc chủ xe đang chat
```

Không nên để frontend, backend và agent tự hiểu business rule theo nhiều cách khác nhau.

---

# 13. Khi tài liệu được cập nhật trên GitHub

Tất cả tài liệu được version bằng **Git commit**.

Khi tài liệu thay đổi:

1. Hãy xem **commit mới nhất** của file.
2. Đọc phần **Changed / Diff** để biết thay đổi gì.
3. Kiểm tra feature có ảnh hưởng tới công việc của bạn không.
4. Nếu có ảnh hưởng, cập nhật code / test / tài liệu liên quan.

### Quy tắc đơn giản

> **Không chỉ đọc file hiện tại. Khi có thông báo tài liệu thay đổi, hãy xem commit/diff để biết chính xác điều gì đã thay đổi.**

---

# 14. Khi bạn phát hiện tài liệu không đúng

Không tự ý sửa logic bằng cách im lặng.

Hãy:

```text
1. Tạo Issue / trao đổi với owner
        ↓
2. Xác nhận business requirement
        ↓
3. Cập nhật tài liệu (đúng template, cập nhật Version và Updated Date)
        ↓
4. Tạo Pull Request vào nhánh develop
        ↓
5. Review
        ↓
6. Merge
```

Nếu code khác tài liệu, cần xác định:

> **Code sai hay tài liệu sai?**

Không nên tự chọn một bên mà không xác nhận.

Khi sửa tài liệu, cập nhật cả các spec liên quan: nếu đổi Functional Spec thì kiểm tra lại FE, API, Entity và AI-Agent Spec cùng user story. Nếu thêm tài liệu hướng dẫn dev mới, thêm link vào [DEV_GUIDE.md](../../DEV_GUIDE.md).

---

# 15. Quy tắc nhớ nhanh cho Intern

| Tài liệu | Câu hỏi |
|---|---|
| PRD | **Tại sao + xây cái gì?** |
| Functional Spec | **Feature hoạt động thế nào?** |
| Frontend Spec | **Frontend làm thế nào?** |
| API Spec | **Backend/API làm thế nào?** |
| Entity Spec | **Dữ liệu gồm gì, ràng buộc ra sao?** |
| AI-Agent Spec | **AI hành xử thế nào?** |
| Platform Spec | **Quy ước chung của mọi feature là gì?** |
| Design Doc | **Thay đổi lớn này được thiết kế ra sao?** |

### Một câu dễ nhớ

> **PRD → Why / What**  
> **Functional → How về nghiệp vụ**  
> **Frontend → How ở UI**  
> **API → How ở Backend**  
> **Entity → How ở dữ liệu**  
> **AI-Agent → How ở AI**

---

# 16. Checklist trước khi bắt đầu code

- [ ] Đã đọc PRD chưa?
- [ ] Đã đọc Functional Spec chưa?
- [ ] Đã hiểu User Flow chưa?
- [ ] Đã hiểu Business Rules chưa?
- [ ] Đã kiểm tra Acceptance Criteria chưa?
- [ ] Đã đọc Frontend / API / Entity / AI-Agent Spec liên quan chưa?
- [ ] Đã xem Platform Spec (lỗi, nhắn tin) nếu feature đụng tới chưa?
- [ ] Đã đọc DESIGN.md nếu làm UI chưa?
- [ ] Đã kiểm tra commit mới nhất của tài liệu chưa?
- [ ] Có điểm nào chưa rõ đã hỏi owner chưa?

> **Nguyên tắc cuối cùng:** Nếu requirement chưa rõ, hãy hỏi trước khi code. Code đúng tài liệu quan trọng hơn code nhanh.
