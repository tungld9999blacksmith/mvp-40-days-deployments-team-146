Thiết kế một bộ wireframe web desktop cho hệ thống **EV Care AI Agent – AI Agent Chăm sóc sau bán & lịch bảo dưỡng xe điện**.

Mục tiêu: tạo giao diện hiện đại, cao cấp, đậm chất công nghệ dành cho xe điện, theo phong cách **Premium Dark**.

## 1. Phong cách thiết kế

* Dark mode là chủ đạo.
* Background chính: đen hoặc xám than rất đậm.
* Màu accent: xanh emerald / xanh lá neon nhẹ.
* Card nền xám đen, có border mờ.
* Góc bo tròn khoảng 10–16px.
* Thiết kế tối giản, hiện đại, cao cấp.
* Cảm giác giống dashboard của một hãng xe điện cao cấp.
* Không sử dụng quá nhiều màu.
* Ưu tiên spacing rộng, bố cục sạch.
* Typography hiện đại như Inter, SF Pro hoặc tương tự.
* Icon dạng outline đơn giản.
* CTA chính dùng xanh emerald.
* Warning dùng vàng/cam.
* Success dùng xanh lá.
* Error dùng đỏ.
* Wireframe nên rõ cấu trúc UI, chưa cần quá tập trung vào hình ảnh trang trí.

Website desktop width khoảng **1440px**.

---

# 2. Navigation chung

Thiết kế sidebar cố định bên trái.

Logo:

EV Care

Menu:

* Tổng quan
* Xe của tôi
* Lịch sử dịch vụ
* Đặt lịch
* AI Trợ lý
* Thông báo
* Hồ sơ

Bottom sidebar:

* Hỗ trợ
* Đăng xuất

Top bar:

* Search
* Notification icon
* Avatar
* Tên người dùng
* Role: Chủ xe

---

# 3. Screen 1 – Login

Tạo màn hình đăng nhập phong cách Premium Dark.

Bố cục 2 cột.

Bên trái:

* Logo EV Care
* Headline:
  "Chăm sóc xe thông minh hơn"
* Subtitle:
  "Theo dõi bảo dưỡng, đặt lịch và nhận hỗ trợ từ AI Agent."
* Background hoặc placeholder hình xe điện cao cấp.

Bên phải:

Form login gồm:

* Email
* Password
* Remember me
* Forgot password
* Button "Đăng nhập"

Footer nhỏ:

"EV Care – Smart EV After-sales Platform"

---

# 4. Screen 2 – Owner Dashboard

Đây là màn hình chính.

Header:

"Xin chào, Nguyễn Văn A 👋"

Subtitle:

"Mọi chuyến đi hôm nay, vì một tương lai xanh hơn."

Khu vực chính chia thành các card.

## Vehicle Card

Title:

"Xe của tôi"

Hiển thị:

* VinFast VF6 hoặc Xe X
* Biển số: 30A-12345
* Placeholder ảnh xe
* Button "Xem chi tiết"

---

## Maintenance Status Card

Title:

"Sắp đến hạn bảo dưỡng"

Thông tin:

"Còn 500 km"

"đến mốc 20,000 km"

Progress bar:

19,500 / 20,000 km

Status badge:

"DUE SOON"

Button:

"Xem chi tiết"

---

## Quick Actions

3 card nhỏ:

1. Hỏi AI

   * subtitle: "Tư vấn 24/7"

2. Đặt lịch

   * subtitle: "Chọn xưởng gần nhất"

3. Cập nhật km

   * subtitle: "Giữ dữ liệu chính xác"

---

## Service History

Table:

Columns:

* Mốc km
* Ngày
* Hạng mục
* Xưởng dịch vụ
* Trạng thái

Example:

10,000 km | 12/04/2026 | Bảo dưỡng định kỳ | Service Center Hà Nội | Hoàn thành

Có link:

"Xem tất cả"

---

# 5. AI Assistant Panel

Đặt một panel AI bên phải Dashboard.

Title:

"AI Trợ lý"

Intro:

"Xin chào! Tôi có thể giúp bạn tra cứu lịch bảo dưỡng, chi phí, bảo hành hoặc đặt lịch xưởng."

Suggested questions dạng chip:

* Xe tôi sắp bảo dưỡng chưa?
* Chi phí bảo dưỡng khoảng bao nhiêu?
* Chính sách bảo hành pin?
* Đặt lịch bảo dưỡng

Phía dưới:

Chat input:

"Nhập câu hỏi..."

Send button dùng màu xanh emerald.

---

# 6. Screen 3 – Vehicle Detail

Page title:

"Xe của tôi"

Vehicle overview card:

* Model
* License Plate
* VIN
* Purchase Date
* Current Mileage
* Battery status placeholder
* Vehicle image placeholder

Current mileage:

19,500 km

Caption (read-only, no button):

"Dữ liệu do hãng cung cấp · cập nhật lúc 09:00 28/09"

> Số km được đồng bộ tự động từ hãng (định kỳ / webhook); chủ xe không nhập hay sửa số km — xem FEAT-VEH-001.

---

Phần Maintenance Status:

Title:

"Trạng thái bảo dưỡng"

Hiển thị:

* Next maintenance: 20,000 km
* Remaining: 500 km
* Progress bar
* Status: Sắp đến hạn

Button:

"Đặt lịch bảo dưỡng"

---

# 7. Screen 4 – Service History

Page title:

"Lịch sử dịch vụ"

Có filter phía trên:

* Tất cả
* Bảo dưỡng
* Sửa chữa
* Kiểm tra

Search input.

Table lớn:

Columns:

* Ngày
* Mileage
* Hạng mục
* Service Center
* Technician
* Chi phí
* Status
* Action

Action:

"Xem chi tiết"

Có pagination phía dưới.

---

# 8. Screen 5 – AI Maintenance Assistant

Thiết kế trang chat AI riêng.

Layout:

Main chat ở giữa.

Sidebar nhỏ bên phải:

"Thông tin xe"

Hiển thị:

* Vehicle: Xe X
* Mileage: 19,500 km
* Next maintenance: 20,000 km
* Status: Due Soon

Chat sample:

User:

"Xe tôi đã đến hạn bảo dưỡng chưa?"

AI:

"Xe hiện đang ở 19,500 km.

Mốc bảo dưỡng tiếp theo là 20,000 km.

Bạn còn khoảng 500 km trước mốc bảo dưỡng tiếp theo."

Phần source riêng:

"Official Source"

Maintenance Manual 2026
Page 25

Buttons:

* Xem hạng mục
* Ước tính chi phí
* Đặt lịch

Chat input ở dưới.

---

# 9. Screen 6 – Maintenance Estimate / Quote

Page title:

"Ước tính chi phí bảo dưỡng"

Vehicle:

Xe X – 30A-12345

Mileage:

19,500 km

Section:

"AI Suggested Services"

Table:

* Hạng mục
* Mô tả
* Estimated Price

Ví dụ:

Service A – 500,000 VND
Service B – 700,000 VND
Service C – 300,000 VND

Total:

1,500,000 VND

Warning card màu vàng đậm:

"Đây là chi phí ước tính. Báo giá chính thức cần được kỹ thuật viên xác nhận."

Status:

"WAITING FOR TECHNICIAN APPROVAL"

Timeline:

AI Recommendation
→ Cost Estimate
→ Technician Review
→ Confirmed Quote

---

# 10. Screen 7 – Booking

Page title:

"Đặt lịch bảo dưỡng"

Step indicator:

1. Chọn xưởng
2. Chọn thời gian
3. Xác nhận

Service Center selector.

Card từng service center gồm:

* Tên xưởng
* Địa chỉ
* Khoảng cách
* Available slots

Date picker.

Available Time:

* 09:00
* 10:30
* 14:00
* 16:00

Selected time sử dụng border xanh emerald.

Booking Summary bên phải:

* Vehicle
* Service Center
* Date
* Time
* Estimated service

Button lớn:

"Xác nhận đặt lịch"

---

# 11. Screen 8 – Booking Success

Modal hoặc page success.

Icon check màu xanh.

Title:

"Đặt lịch thành công"

Thông tin:

Service Center Hà Nội

20/09/2026

10:30

Vehicle:

Xe X – 30A-12345

Buttons:

* Xem lịch hẹn
* Quay về Dashboard

---

# 12. Screen 9 – Notifications

Page title:

"Thông báo"

Các notification card:

### Due Maintenance

Icon warning.

Title:

"Sắp đến hạn bảo dưỡng"

Message:

"Xe của bạn hiện ở 19,500 km và còn khoảng 500 km trước mốc bảo dưỡng."

CTA:

"Đặt lịch ngay"

---

### Quote Approved

Icon success.

Title:

"Báo giá đã được kỹ thuật viên duyệt"

Message:

"Tổng chi phí dự kiến: 1,500,000 VND"

CTA:

"Xem báo giá"

---

# 13. Technician Dashboard

Sau khi login với role Technician, sử dụng cùng phong cách Premium Dark.

Sidebar:

* Dashboard
* Báo giá
* Lịch hẹn
* Khách hàng
* Thông báo

Dashboard cards:

* Pending Quotes
* Today's Appointments
* Completed Services
* Overdue Vehicles

---

# 14. Screen 10 – Pending Quote Approval

Page title:

"Yêu cầu duyệt báo giá"

Danh sách card hoặc table.

Columns:

* Vehicle
* Customer
* Mileage
* Estimated Price
* Created At
* Status
* Action

Action:

"Review"

---

# 15. Screen 11 – Technician Quote Review

Page title:

"Review Quote"

Thông tin xe:

* Model
* License plate
* Mileage
* Customer

AI Recommendation card:

"AI Suggested Services"

Hiển thị từng service.

Cho Technician:

* checkbox chọn/bỏ hạng mục
* chỉnh sửa giá
* thêm hạng mục
* viết technician note

Total Price cập nhật ở cuối.

Buttons:

"Reject"

"Save Changes"

"Approve Quote"

Approve button màu xanh emerald nổi bật.

---

# 16. Trạng thái quan trọng

Thiết kế badge thống nhất:

NORMAL
→ neutral / green

DUE SOON
→ yellow

OVERDUE
→ red

PENDING APPROVAL
→ yellow

APPROVED
→ green

REJECTED
→ red

COMPLETED
→ green

CANCELLED
→ gray

---

# 17. Design System

Colors:

Background:
#0B0F0E

Surface:
#121817

Card:
#171D1C

Primary:
Emerald Green

Text Primary:
#F5F7F6

Text Secondary:
#8D9995

Border:
dark gray

Warning:
yellow / amber

Error:
red

---

Buttons:

Primary:
emerald background + dark text

Secondary:
dark background + subtle border

Danger:
dark red

---

# 18. UX Priorities

Dashboard phải giúp người dùng nhìn ngay thấy:

1. Xe hiện đang ở bao nhiêu km.
2. Khi nào cần bảo dưỡng.
3. Có đang quá hạn hay không.
4. Có thể hỏi AI ở đâu.
5. Có thể đặt lịch ở đâu.

Không để người dùng phải mở nhiều màn hình mới biết trạng thái bảo dưỡng.

AI recommendations phải luôn hiển thị nguồn tài liệu chính hãng.

Chi phí AI đưa ra phải luôn có nhãn "Estimated".

Báo giá chưa được Technician duyệt phải có trạng thái rõ ràng.

---

# 19. Prototype Flow

Tạo prototype navigation:

Login
→ Owner Dashboard

Owner Dashboard
→ Vehicle Detail

Owner Dashboard
→ AI Assistant

AI Assistant
→ Maintenance Estimate

Maintenance Estimate
→ Booking

Booking
→ Booking Success

Login as Technician
→ Technician Dashboard

Technician Dashboard
→ Pending Quote

Pending Quote
→ Quote Review

Quote Review
→ Approve

Approve
→ Quote status Approved

---

Mục tiêu cuối cùng:

Tạo một bộ wireframe web SaaS dashboard cho nền tảng chăm sóc xe điện, mang cảm giác **Premium, Futuristic, Trustworthy, Technology-focused và EV-oriented**, với dark theme và emerald green làm màu nhận diện chính.
