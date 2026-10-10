# Worklog — Team P-146

> Ghi lại tất cả công việc đã làm theo ngày. Ai làm gì, kết quả gì.
> Ngày mới nhất ở trên cùng. Cột Time để "-" khi chưa ghi nhận thời gian.

---

## 2026-10-10

| Member | Task | Status | Output | Time |
|--------|------|--------|--------|------|
| Mai Văn Trung | Dữ liệu lịch bảo dưỡng theo dòng xe và giá xưởng (báo giá hai tầng, bước 1) | ✅ Done | a7d47eb | - |
| Mai Văn Trung | Đặt lịch với báo giá hai tầng, bật qua cờ `QUOTE_FLOW` (bước 2) | ✅ Done | a152f02 | - |
| Mai Văn Trung | Sửa lỗi QA ISSUE-001: ô nhập tiền bị nối vào giá điền sẵn | ✅ Done | c115c7f | - |
| Mai Văn Trung | Eval: cho PRICE-02 đọc các dòng dịch vụ trước khi từ chối quyết định | ✅ Done | 4b138ac | - |
| Mai Văn Trung | Thêm lệnh test vào CLAUDE.md; ghi các phát hiện QA hoãn lại vào TODOS | ✅ Done | 9f83229, 5ff907f | - |
| Mai Văn Trung | Xử lý ISSUE-002 đến 006 sau QA (hạng mục lặp trên Bảng giá, nhãn giá, aria-label) | 🔄 WIP | Đang ghi trong TODOS.md | - |

**Tổng kết ngày:** Hoàn thành hai bước đầu của báo giá hai tầng và sửa lỗi QA đầu tiên. Các lỗi còn lại đã được ghi vào TODOS.

---

## 2026-10-09

| Member | Task | Status | Output | Time |
|--------|------|--------|--------|------|
| Dinh Kim Thai | Cải thiện nhắc lịch đặt xe và RAG, kèm đánh giá (guardrail, grounding, policy gate, CI đánh giá agent) | ✅ Done | 4c95cd0 | - |
| Dinh Kim Thai | Hoàn thành 2 pilot đánh giá (base và agent_gemma) | ✅ Done | 4f39241, `eval/results/step5_pilot_status.json` | - |
| Dinh Kim Thai | Sửa lỗi Qdrant WinError 10054: tạo client mới cho mỗi case và retry | ✅ Done | 728b6c6 | - |
| Mai Văn Trung | Ổn định việc huỷ chat và việc chạy RAG ở backend | ✅ Done | c4a670d | - |
| Mai Văn Trung | Sửa connection pool ở các đường đặt lịch bất đồng bộ (P1) | ❌ Blocked | Chưa sửa; giống sự cố Supavisor 06/10 (xem TODOS.md) | - |

**Tổng kết ngày:** Pilot đánh giá agent đã xong và RAG, nhắc lịch được cải thiện. Chat ổn định hơn. Lỗi connection pool vẫn chưa xử lý.

---

## 2026-10-08

| Member | Task | Status | Output | Time |
|--------|------|--------|--------|------|
| Mai Văn Trung | Làm mới giao diện trợ lý AI và trang chi tiết xe | ✅ Done | d1c52e8 | - |

**Tổng kết ngày:** Cập nhật giao diện frontend.

---

## 2026-10-07

| Member | Task | Status | Output | Time |
|--------|------|--------|--------|------|
| Mai Văn Trung | Định tuyến LLM theo từng tầng và thêm công cụ báo giá trong chat | ✅ Done | 4e251c3 | - |
| Mai Văn Trung | Khôi phục luồng xưởng duyệt báo giá | ✅ Done | 7438530 | - |
| Mai Văn Trung | Thông báo kết quả báo giá và nhắc lịch hẹn | ✅ Done | b0ab4cb | - |
| Mai Văn Trung | Kênh thông báo email (SMTP) và SMS (eSMS) | ✅ Done | d939353 | - |
| Mai Văn Trung | Bộ phân loại phản hồi sau dịch vụ bằng LLM và cờ an toàn lưu trong DB (AI-007) | ✅ Done | 220f3e9 | - |
| Mai Văn Trung | Link trang theo dõi sau dịch vụ từ phiếu đặt lịch đã hoàn thành; sửa crash khi xưởng chưa có hotline | ✅ Done | b24cb79, de01b14 | - |
| Mai Văn Trung | Deploy frontend lên Vercel với API proxy qua Railway; sửa CORS | ✅ Done | df5e3b7, f63c6f7, cc3112c | - |
| Mai Văn Trung | Tài liệu chăm sóc sau bán hàng và Celery trên Windows | ✅ Done | 8777e5f | - |
| Dinh Kim Thai | Tích hợp demo agent và email test qua Resend | ✅ Done | 0d0b998, ac24213 | - |

**Tổng kết ngày:** Ngày có nhiều việc nhất. Hoàn thành luồng báo giá, các kênh thông báo, chăm sóc sau dịch vụ và deploy staging.

---

## Vấn đề đang chặn (tính đến 2026-10-10)

- Connection pool (P1): các đường đặt lịch bất đồng bộ giữ session idle-in-transaction khi chờ khoá Redis.
- ISSUE-003: `item_code` theo từng mốc nên một dịch vụ hiện nhiều lần trên Bảng giá. Cần quyết định danh tính hạng mục xuyên mốc.
- Kênh ghi quyết định phát sinh qua điện thoại: chờ kết quả phỏng vấn The Assignment.
- Màn Bảng giá và nhãn giá đặt lịch chưa có thiết kế, đang chặn T7.

<!-- Format: copy block ngày ở trên cho mỗi ngày làm việc -->
