# Nghiệp vụ EV Care

EV Care hỗ trợ chủ xe theo dõi bảo dưỡng, hỏi trợ lý AI, xem dự toán và đặt lịch; kỹ thuật viên duyệt báo giá, xác nhận và xử lý lịch hẹn.

Các màn hình hiện là prototype dùng mock. Vai trò được chọn ở giao diện, chưa có xác thực hoặc phân quyền backend.

Luồng mục tiêu:

1. Chủ xe xem thông tin xe và hạn bảo dưỡng.
2. Trợ lý giải thích hạng mục dựa trên tài liệu có nguồn.
3. Hệ thống lập dự toán chi phí theo mốc và xưởng.
4. (Tuỳ chọn) Chủ xe gửi dự toán thành báo giá; kỹ thuật viên sửa, duyệt hoặc từ chối.
5. Chủ xe chọn xưởng, khung giờ và xác nhận lịch hẹn (có thể kèm báo giá đã duyệt).
6. Kỹ thuật viên xác nhận lịch hẹn và cập nhật tiến độ dịch vụ.

Khi triển khai dữ liệu thật, các quy tắc tính hạn, tính tiền, chuyển trạng thái lịch hẹn, báo giá và kiểm tra chỗ trống phải do service backend xử lý. Mọi con số chi phí AI đưa ra là dự toán cho đến khi được kỹ thuật viên duyệt thành báo giá.

Đặc tả giao diện: [wireframe](../design/wireframe.md).
