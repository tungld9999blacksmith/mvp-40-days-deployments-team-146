# Nghiệp vụ EV Care

EV Care hỗ trợ chủ xe theo dõi bảo dưỡng, hỏi trợ lý AI, xem dự toán và đặt lịch; kỹ thuật viên xem và duyệt báo giá.

Các màn hình hiện là prototype dùng mock. Vai trò được chọn ở giao diện, chưa có xác thực hoặc phân quyền backend.

Luồng mục tiêu:

1. Chủ xe xem thông tin xe và hạn bảo dưỡng.
2. Trợ lý giải thích hạng mục dựa trên tài liệu có nguồn.
3. Hệ thống lập dự toán và chuyển cho kỹ thuật viên.
4. Kỹ thuật viên sửa, duyệt hoặc từ chối báo giá.
5. Chủ xe chọn xưởng, khung giờ và xác nhận lịch hẹn.

Khi triển khai dữ liệu thật, các quy tắc tính hạn, tính tiền, chuyển trạng thái báo giá và kiểm tra chỗ trống phải do service backend xử lý. Báo giá AI đề xuất luôn là dự toán cho đến khi được kỹ thuật viên duyệt.

Đặc tả giao diện: [wireframe](../design/wireframe.md).
