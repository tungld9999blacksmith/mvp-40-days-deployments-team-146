# Review bước 3

Reviewer: người dùng đã chọn trực tiếp review. Các nhãn hiện vẫn trống; chưa có kết luận nghiệm thu.

1. Mở [rag_review.html](rag_review.html) bằng trình duyệt, không cần khởi động backend/frontend. Điền tên reviewer.
2. Có thể bắt đầu bằng các liên kết M07, M18, M23 ở đầu trang, rồi review đủ 100 câu. Dùng Ctrl+F để tìm ID.
3. Đọc câu hỏi, đáp án cần review và phần bằng chứng đầy đủ. Đối chiếu số citation trong đáp án qua bảng ánh xạ tới đúng document/chunk; số nguồn sau lọc có thể khác số trong context gốc.
4. Chọn ba nhãn cho mỗi câu: **Đúng nội dung**, **Nguồn hỗ trợ**, **Đáp ứng yêu cầu**. Chọn **Chưa chắc** và ghi lý do khi chưa đủ căn cứ; câu fallback phải giữ đúng giới hạn bằng chứng và đáp ứng phần có thể xác định.
5. Bấm **Export JSON** để tải `rag-maintenance-review.json`. Lưu bản export với tên mới; gửi lại kết quả review để tổng hợp. Trình duyệt lưu nhãn theo hash của lượt chạy; export chứa hash để gắn nhãn đúng output.

Các nguồn cần xác minh riêng nằm ở [source_owner_review_queue.json](source_owner_review_queue.json): coolant 12.000 km/120 tháng, bảng điều hòa và ánh xạ thao tác theo mốc, PDF VFe34 có điều khoản VF8, scope/phiên bản bảo hành, SOC đầu khi tính thời gian sạc, và expected-doc của golden. Cần tài liệu/phiên bản đủ căn cứ trước khi duyệt quy tắc; nhãn review đáp án không tự sửa corpus hoặc golden.

Ba ca mới được runtime xử lý trước provider, không phải bằng chứng model tự suy luận đúng. 100 câu này là development; bộ holdout nghiệm thu vẫn cần được khóa riêng.

Phần hội thoại 20 phiên cần review riêng tại [trang phiên](../schema_source_mistral_20261008_08/session_review.html). Kết quả Booking 54 ca mới có [CSV review](../agent_v2_1_time_booking_54_mistral_20261008_12/human_review.csv). Không cộng nhãn/điểm của các bộ này để suy ra một tỷ lệ chính xác chung.
