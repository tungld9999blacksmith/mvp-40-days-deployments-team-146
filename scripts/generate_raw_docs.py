import os
from pathlib import Path
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

RAW_DIR = Path("data/knowledge/raw")
RAW_DIR.mkdir(parents=True, exist_ok=True)

# ── 1. HTML: Chính sách bảo hành toàn diện ─────────────────────────
html_warranty = """<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <title>Chính sách bảo hành xe ô tô điện VinFast chính hãng</title>
</head>
<body>
    <header>
        <nav><a href="/">Trang chủ</a> | <a href="/dich-vu">Dịch vụ hậu mãi</a></nav>
    </header>

    <main>
        <h1>Chính sách bảo hành xe ô tô điện VinFast chính hãng</h1>
        <p><strong>Ngày ban hành:</strong> 01/01/2026 | <strong>Phạm vi áp dụng:</strong> Toàn quốc cho tất cả các dòng xe điện VinFast (VF 3, VF 5, VF 6, VF 7, VF 8, VF 9).</p>

        <h2>1. Thời hạn bảo hành xe mới theo từng dòng xe</h2>
        <p>VinFast áp dụng chính sách bảo hành chính hãng hàng đầu thị trường đối với các dòng xe ô tô điện phân phối chính thức:</p>
        <table>
            <thead>
                <tr>
                    <th>Dòng xe</th>
                    <th>Thời hạn xe mới</th>
                    <th>Giới hạn km xe mới</th>
                    <th>Thời hạn bảo hành Pin cao áp</th>
                    <th>Giới hạn km Pin cao áp</th>
                </tr>
            </thead>
            <tbody>
                <tr>
                    <td>VinFast VF 8, VF 9</td>
                    <td>10 năm</td>
                    <td>200.000 km</td>
                    <td>10 năm</td>
                    <td>Không giới hạn km</td>
                </tr>
                <tr>
                    <td>VinFast VF 6, VF 7</td>
                    <td>7 năm</td>
                    <td>160.000 km</td>
                    <td>8 năm</td>
                    <td>160.000 km</td>
                </tr>
                <tr>
                    <td>VinFast VF 5 Plus, VF 3</td>
                    <td>7 năm</td>
                    <td>160.000 km</td>
                    <td>8 năm</td>
                    <td>160.000 km</td>
                </tr>
            </tbody>
        </table>
        <p><em>Ghi chú:</em> Thời hạn bảo hành được tính từ ngày xe được bàn giao lần đầu cho khách hàng hoặc ngày xuất hóa đơn bán lẻ, tùy theo điều kiện nào đến trước.</p>

        <h2>2. Chính sách bảo hành các cấu phần quan trọng</h2>
        <h3>2.1. Cụm Pin điện áp cao (High Voltage Traction Battery)</h3>
        <p>Pin điện áp cao được bảo hành đối với các lỗi do khiếm khuyết vật liệu hoặc lắp ráp của nhà sản xuất. Nếu dung lượng pin tối đa (SOH - State of Health) giảm xuống dưới 70% trong thời hạn bảo hành thông thường, khách hàng sẽ được sửa chữa hoặc thay thế mô-đun pin/cụm pin miễn phí theo tiêu chuẩn hãng.</p>
        <p>Đối với pin mua thay thế (từ lần thứ hai trở đi), thời gian bảo hành là 4 năm hoặc 80.000 km tùy điều kiện nào đến trước.</p>

        <h3>2.2. Động cơ điện (E-Motor) & Hộp giảm tốc</h3>
        <p>Động cơ điện, biến tần (Inverter) và hộp giảm tốc truyền động được bảo hành theo thời hạn của xe mới (từ 7 đến 10 năm tùy dòng xe). Bảo hành bao gồm hư hỏng cơ khí hoặc lỗi bảng mạch điện tử điều khiển.</p>

        <h3>2.3. Hệ thống khung gầm & Treo</h3>
        <p>Bảo hành 3 năm hoặc 100.000 km đối với các chi tiết khung gầm, càng chữ A, giảm xóc, thanh cân bằng do lỗi chế tạo.</p>

        <h3>2.4. Hệ thống điện tử, Màn hình giải trí & ADAS</h3>
        <p>Màn hình trung tâm, cảm biến radar, camera ADAS, ECU điều khiển được bảo hành 3 năm hoặc 100.000 km.</p>

        <h3>2.5. Bình ắc quy 12V phụ trợ</h3>
        <p>Ắc quy 12V cung cấp nguồn cho hệ thống điện phụ trợ được bảo hành 1 năm hoặc 20.000 km tùy điều kiện nào đến trước.</p>

        <h2>3. Các trường hợp loại trừ bảo hành (Không được bảo hành miễn phí)</h2>
        <ul>
            <li>Hư hỏng pin hoặc khung gầm do va đập vật lý từ bên ngoài (sập gầm, đá văng, cạ gầm làm móp méo vỏ pack pin).</li>
            <li>Xe bị ngập nước vượt quá mức an toàn khuyến cáo của nhà sản xuất hoặc nước lọt vào khoang pin do tự ý tháo mở.</li>
            <li>Tự ý câu nối, độ chế hệ thống điện cao áp, can thiệp phần mềm ECU, bẻ khóa hệ điều hành xe (jailbreak/root) hoặc lắp đặt thiết bị ngoại vi không đạt chuẩn.</li>
            <li>Sử dụng thiết bị sạc không chính hãng, sạc tại nguồn điện không đảm bảo nối đất an toàn dẫn đến chập cháy.</li>
            <li>Hao mòn tự nhiên trong quá trình sử dụng thông thường: má phanh, đĩa phanh mòn, lốp xe mòn, gạt mưa, dung dịch làm mát hao hụt tự nhiên.</li>
            <li>Không thực hiện bảo dưỡng định kỳ đầy đủ tại các xưởng dịch vụ ủy quyền chính hãng của VinFast.</li>
        </ul>

        <h2>4. Quy trình yêu cầu bảo hành</h2>
        <p>Khi phát hiện dấu hiệu bất thường, chủ xe liên hệ xưởng dịch vụ chính hãng hoặc qua AI Agent EV Care để đặt lịch kiểm tra. Kỹ thuật viên sẽ quét mã lỗi OBD/CAN, kiểm tra vật lý và lập biên bản bảo hành điện tử.</p>
    </main>
    <footer>
        <p>&copy; 2026 VinFast Auto. All rights reserved.</p>
    </footer>
</body>
</html>
"""

# ── 2. HTML: Cẩm nang bảo dưỡng định kỳ ─────────────────────────────
html_maintenance = """<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <title>Cẩm nang lịch bảo dưỡng định kỳ ô tô điện VinFast</title>
</head>
<body>
    <main>
        <h1>Cẩm nang lịch bảo dưỡng định kỳ ô tô điện VinFast (VF 3 - VF 9)</h1>
        <p>Xe điện có cấu tạo cơ khí tinh giản hơn xe động cơ đốt trong (không dùng dầu máy, bugi, dây đai cam), giúp giảm 50% chi phí bảo dưỡng. Tuy nhiên, việc tuân thủ chu kỳ bảo dưỡng định kỳ là bắt buộc để đảm bảo an toàn vận hành và hiệu lực bảo hành chính hãng.</p>

        <h2>1. Chu kỳ bảo dưỡng định kỳ</h2>
        <p>Chu kỳ bảo dưỡng tiêu chuẩn của xe điện VinFast được áp dụng theo các mốc:</p>
        <ul>
            <li><strong>Cấp 1 (Bảo dưỡng nhỏ):</strong> Mỗi 10.000 km hoặc 6 tháng.</li>
            <li><strong>Cấp 2 (Bảo dưỡng trung bình):</strong> Mỗi 20.000 km hoặc 12 tháng.</li>
            <li><strong>Cấp 3 (Bảo dưỡng lớn):</strong> Mỗi 40.000 km hoặc 24 tháng.</li>
            <li><strong>Cấp 4 (Bảo dưỡng toàn diện):</strong> Mỗi 80.000 km hoặc 48 tháng.</li>
        </ul>

        <h2>2. Danh mục chi tiết theo từng mốc km</h2>

        <h3>2.1. Mốc 10.000 km (hoặc 6 tháng)</h3>
        <p>Hạng mục thực hiện:</p>
        <ul>
            <li>Kiểm tra và đọc lỗi toàn bộ hệ thống điện tử (OBD scanner) & tình trạng BMS pin.</li>
            <li>Kiểm tra mức và chất lượng dung dịch làm mát pin cao áp và động cơ điện.</li>
            <li>Kiểm tra độ mòn má phanh và hành trình bàn đạp phanh.</li>
            <li>Kiểm tra áp suất lốp, độ mòn gai lốp và siết lại đai ốc bánh xe theo lực siết quy định.</li>
            <li>Kiểm tra hệ thống treo, khớp cầu, cao su chắn bụi và thước lái.</li>
            <li>Bổ sung nước rửa kính chắn gió.</li>
        </ul>

        <h3>2.2. Mốc 20.000 km (hoặc 12 tháng)</h3>
        <p>Hạng mục thực hiện:</p>
        <ul>
            <li>Toàn bộ các hạng mục kiểm tra của mốc 10.000 km.</li>
            <li><strong>Thay thế lọc gió điều hòa (lọc gió cabin than hoạt tính):</strong> bắt buộc thay thế định kỳ để đảm bảo chất lượng không khí trong xe.</li>
            <li>Kiểm tra điện áp và dung lượng bình ắc quy 12V phụ trợ.</li>
            <li>Kiểm tra cổng sạc AC/DC, chốt khóa cổng sạc và vệ sinh tiếp điểm sạc.</li>
            <li>Vệ sinh dàn nóng và két tản nhiệt làm mát pin cao áp.</li>
        </ul>

        <h3>2.3. Mốc 40.000 km (hoặc 24 tháng) - Bảo dưỡng lớn</h3>
        <p>Hạng mục thực hiện:</p>
        <ul>
            <li>Toàn bộ hạng mục của mốc 20.000 km.</li>
            <li><strong>Thay thế toàn bộ dung dịch làm mát pin cao áp và motor:</strong> nhằm duy trì hiệu suất giải nhiệt pin ổn định, tránh kết tủa ăn mòn.</li>
            <li><strong>Thay thế dung dịch dầu phanh (DOT 4 EV):</strong> dầu phanh hút ẩm theo thời gian, bắt buộc thay sau mỗi 2 năm để đảm bảo áp suất phanh.</li>
            <li>Kiểm tra chuyên sâu má phanh trước/sau, đĩa phanh và độ đảo đĩa.</li>
            <li>Đảo lốp và cân bằng động 4 bánh xe.</li>
            <li>Kiểm tra độ rơ thước lái và góc đặt bánh xe.</li>
        </ul>

        <h3>2.4. Mốc 60.000 km (hoặc 36 tháng)</h3>
        <p>Hạng mục thực hiện:</p>
        <ul>
            <li>Thay lọc gió cabin điều hòa.</li>
            <li>Kiểm tra và kiểm định tình trạng suy giảm dung lượng pin (SOH evaluation).</li>
            <li>Kiểm tra gioăng chống nước khoang pin và gầm bảo vệ pin cao áp.</li>
            <li>Thay thế má phanh nếu độ dày còn dưới 3mm.</li>
        </ul>

        <h3>2.5. Mốc 80.000 km (hoặc 48 tháng) - Đại tu toàn diện</h3>
        <p>Hạng mục thực hiện:</p>
        <ul>
            <li>Thay thế toàn bộ dung dịch làm mát pin, dầu phanh.</li>
            <li><strong>Thay dầu hộp giảm tốc (Transmission Fluid for EV):</strong> làm sạch mạt kim loại và bảo vệ bánh răng vi sai.</li>
            <li>Kiểm tra cách điện cao áp (Megohmmeter test) giữa hệ thống pin và khung vỏ xe.</li>
            <li>Kiểm tra giảm xóc, cao su chân máy và rotuyn lái.</li>
        </ul>
    </main>
</body>
</html>
"""

# ── 3. HTML: Bảng giá dịch vụ và phụ tùng ──────────────────────────
html_pricing = """<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <title>Bảng giá dịch vụ bảo dưỡng và phụ tùng ô tô điện VinFast</title>
</head>
<body>
    <main>
        <h1>Bảng giá tham khảo dịch vụ bảo dưỡng và phụ tùng ô tô điện VinFast 2026</h1>
        <p>Bảng giá niêm yết áp dụng tại hệ thống Xưởng Dịch vụ Chính hãng VinFast trên toàn quốc (Đã bao gồm thuế VAT 8-10%).</p>

        <h2>1. Bảng giá phụ tùng tiêu hao & dung dịch bảo dưỡng</h2>
        <table>
            <thead>
                <tr>
                    <th>Tên phụ tùng / vật tư</th>
                    <th>Dòng xe áp dụng</th>
                    <th>Đơn vị</th>
                    <th>Đơn giá niêm yết (VNĐ)</th>
                    <th>Ghi chú</th>
                </tr>
            </thead>
            <tbody>
                <tr>
                    <td>Lọc gió điều hòa than hoạt tính</td>
                    <td>VF 5 Plus</td>
                    <td>Cái</td>
                    <td>350.000</td>
                    <td>Thay thế mỗi 20.000 km</td>
                </tr>
                <tr>
                    <td>Lọc gió điều hòa than hoạt tính cao cấp</td>
                    <td>VF 6, VF 7</td>
                    <td>Cái</td>
                    <td>420.000</td>
                    <td>Thay thế mỗi 20.000 km</td>
                </tr>
                <tr>
                    <td>Lọc gió điều hòa kép HEPA PM2.5</td>
                    <td>VF 8, VF 9</td>
                    <td>Bộ</td>
                    <td>650.000</td>
                    <td>Khử khuẩn và lọc bụi mịn PM2.5</td>
                </tr>
                <tr>
                    <td>Dung dịch làm mát pin cao áp chuyên dụng</td>
                    <td>Tất cả các dòng VF</td>
                    <td>Bình (4 Lít)</td>
                    <td>800.000</td>
                    <td>Loại điện môi đặc chủng không dẫn điện</td>
                </tr>
                <tr>
                    <td>Dầu phanh chính hãng DOT 4 EV</td>
                    <td>Tất cả các dòng VF</td>
                    <td>Chai (1 Lít)</td>
                    <td>450.000</td>
                    <td>Chống ăn mòn và chịu nhiệt cao</td>
                </tr>
                <tr>
                    <td>Dầu hộp giảm tốc E-Motor</td>
                    <td>VF 5, VF 6, VF 7, VF 8, VF 9</td>
                    <td>Lít</td>
                    <td>550.000</td>
                    <td>Thay mỗi 80.000 km</td>
                </tr>
                <tr>
                    <td>Gạt mưa silicon trước (cặp)</td>
                    <td>VF 5, VF 6</td>
                    <td>Cặp</td>
                    <td>450.000</td>
                    <td>Gạt êm, không xước kính</td>
                </tr>
                <tr>
                    <td>Má phanh trước chính hãng</td>
                    <td>VF 5, VF 6</td>
                    <td>Bộ</td>
                    <td>1.200.000</td>
                    <td>Bao gồm cảm biến báo mòn</td>
                </tr>
                <tr>
                    <td>Má phanh trước chính hãng</td>
                    <td>VF 8, VF 9</td>
                    <td>Bộ</td>
                    <td>1.850.000</td>
                    <td>Chịu tải trọng lớn</td>
                </tr>
            </tbody>
        </table>

        <h2>2. Bảng giá tiền công dịch vụ bảo dưỡng theo cấp</h2>
        <table>
            <thead>
                <tr>
                    <th>Gói dịch vụ</th>
                    <th>Mốc áp dụng</th>
                    <th>Giá công thợ VF3/VF5</th>
                    <th>Giá công thợ VF6/VF7</th>
                    <th>Giá công thợ VF8/VF9</th>
                </tr>
            </thead>
            <tbody>
                <tr>
                    <td>Bảo dưỡng Cấp 1</td>
                    <td>10.000 km</td>
                    <td>200.000 VNĐ</td>
                    <td>250.000 VNĐ</td>
                    <td>300.000 VNĐ</td>
                </tr>
                <tr>
                    <td>Bảo dưỡng Cấp 2</td>
                    <td>20.000 km</td>
                    <td>350.000 VNĐ</td>
                    <td>450.000 VNĐ</td>
                    <td>550.000 VNĐ</td>
                </tr>
                <tr>
                    <td>Bảo dưỡng Cấp 3</td>
                    <td>40.000 km</td>
                    <td>600.000 VNĐ</td>
                    <td>750.000 VNĐ</td>
                    <td>900.000 VNĐ</td>
                </tr>
                <tr>
                    <td>Bảo dưỡng Cấp 4</td>
                    <td>80.000 km</td>
                    <td>900.000 VNĐ</td>
                    <td>1.100.000 VNĐ</td>
                    <td>1.400.000 VNĐ</td>
                </tr>
                <tr>
                    <td>Đảo lốp & Cân bằng động 4 bánh</td>
                    <td>Theo nhu cầu</td>
                    <td>250.000 VNĐ</td>
                    <td>300.000 VNĐ</td>
                    <td>350.000 VNĐ</td>
                </tr>
            </tbody>
        </table>

        <h2>3. Ước tính tổng chi phí bảo dưỡng từng mốc</h2>
        <ul>
            <li><strong>Mốc 10.000 km:</strong> Khoảng 200.000 - 300.000 VNĐ (chủ yếu là công kiểm tra, vệ sinh má phanh).</li>
            <li><strong>Mốc 20.000 km:</strong> Khoảng 700.000 - 1.200.000 VNĐ (thay lọc gió điều hòa + công kiểm tra).</li>
            <li><strong>Mốc 40.000 km:</strong> Khoảng 1.800.000 - 2.800.000 VNĐ (thay nước làm mát pin, dầu phanh, lọc gió + công).</li>
        </ul>
        <p><strong>Lưu ý quan trọng:</strong> Toàn bộ chi phí do AI đề xuất mang tính chất <em>Dự toán ước tính (Estimated)</em>. Chi phí thực tế sẽ được Kỹ thuật viên kiểm tra trực tiếp và phê duyệt (HITL Approved Quote) tại xưởng dịch vụ trước khi khách hàng thanh toán.</p>
    </main>
</body>
</html>
"""

# ── 4. HTML: Quy trình duyệt báo giá HITL và đặt lịch xưởng ─────────
html_procedure = """<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <title>Quy trình dịch vụ đặt lịch xưởng và duyệt báo giá HITL</title>
</head>
<body>
    <main>
        <h1>Quy trình điều phối dịch vụ & Duyệt báo giá Human-In-The-Loop (HITL)</h1>
        <p>Hệ thống EV Care AI Agent ứng dụng mô hình HITL (Kỹ thuật viên con người tham gia phê duyệt) nhằm bảo vệ quyền lợi người dùng, chống việc AI hallucination hoặc đưa ra chi phí không chính xác.</p>

        <h2>1. Vòng đời xử lý yêu cầu bảo dưỡng</h2>
        <ol>
            <li><strong>Phát hiện nhu cầu:</strong> AI Agent theo dõi telemetry km xe hoặc chủ xe chủ động tra cứu lịch bảo dưỡng trên app.</li>
            <li><strong>Tạo dự toán AI:</strong> Dựa trên mốc km và cẩm nang kỹ thuật, AI đề xuất danh sách phụ tùng cần thay thế và tiền công ước tính. Báo giá được gắn nhãn <code>WAITING FOR TECHNICIAN APPROVAL</code>.</li>
            <li><strong>Thẩm định Kỹ thuật viên (HITL Review):</strong> Kỹ thuật viên trưởng tại Xưởng dịch vụ nhận thông báo. Kỹ thuật viên có quyền:
                <ul>
                    <li>Chọn hoặc bỏ chọn các hạng mục đề xuất dựa trên tình trạng xe.</li>
                    <li>Điều chỉnh đơn giá phụ tùng hoặc tiền công theo chính sách khuyến mãi thực tế.</li>
                    <li>Bổ sung ghi chú kỹ thuật viên (Technician note).</li>
                </ul>
            </li>
            <li><strong>Phê duyệt (Approve Quote):</strong> Kỹ thuật viên bấm duyệt. Trạng thái chuyển thành <code>APPROVED</code>.</li>
            <li><strong>Xác nhận từ Chủ xe:</strong> Chủ xe nhận thông báo báo giá đã duyệt, chọn khung giờ hẹn xưởng (09:00, 10:30, 14:00, 16:00) và xác nhận đặt lịch.</li>
            <li><strong>Tiếp nhận và thực hiện:</strong> Xe đến xưởng theo lịch hẹn, kỹ thuật viên thực hiện dịch vụ theo đúng báo giá đã ký kết.</li>
        </ol>

        <h2>2. Danh sách trung tâm xưởng dịch vụ ủy quyền</h2>
        <ul>
            <li><strong>VinFast Thăng Long:</strong> Số 68 Lê Văn Lương, Cầu Giấy, Hà Nội (Hotline: 1900 23 23 89).</li>
            <li><strong>VinFast Quận 7:</strong> 101 Tôn Dật Tiên, Tân Phú, Quận 7, TP. Hồ Chí Minh.</li>
            <li><strong>VinFast Đà Nẵng:</strong> 115 Nguyễn Văn Linh, Nam Dương, Hải Châu, Đà Nẵng.</li>
        </ul>
    </main>
</body>
</html>
"""

# Ghi các file HTML
(RAW_DIR / "vinfast_chinh_sach_bao_hanh_toan_dien.html").write_text(html_warranty, encoding="utf-8")
(RAW_DIR / "vinfast_cam_nang_bao_duong_dinh_ky.html").write_text(html_maintenance, encoding="utf-8")
(RAW_DIR / "vinfast_bang_gia_dich_vu_va_phu_tung.html").write_text(html_pricing, encoding="utf-8")
(RAW_DIR / "quy_trinh_dich_vu_xep_lich_va_duyet_bao_gia_hitl.html").write_text(html_procedure, encoding="utf-8")

# ── 5. PDF: Sổ tay vận hành & An toàn pin xe điện (Tạo bằng reportlab) ──
pdf_path = RAW_DIR / "so_tay_van_hanh_va_an_toan_pin_ev.pdf"
doc = SimpleDocTemplate(str(pdf_path), pagesize=letter)
styles = getSampleStyleSheet()

title_style = ParagraphStyle(
    "TitleStyle",
    parent=styles["Title"],
    fontSize=18,
    leading=22,
    textColor=colors.HexColor("#0B3C5D"),
)
h1_style = ParagraphStyle(
    "H1Style",
    parent=styles["Heading1"],
    fontSize=14,
    leading=18,
    textColor=colors.HexColor("#1D2731"),
)
h2_style = ParagraphStyle(
    "H2Style",
    parent=styles["Heading2"],
    fontSize=12,
    leading=15,
    textColor=colors.HexColor("#328CC1"),
)
body_style = ParagraphStyle(
    "BodyStyle",
    parent=styles["Normal"],
    fontSize=10,
    leading=14,
    textColor=colors.black,
)

elements = [
    Paragraph("SO TAY HUONG DAN VAN HANH VA AN TOAN PIN XE DIEN VINFAST", title_style),
    Paragraph("Tai lieu ky thuat chinh hang danh cho chu xe va ky thuat vien - EV Care", body_style),
    Spacer(1, 15),

    Paragraph("1. NGUYEN TAC AN TOAN VA QUAN LY PIN CAO AP (TRACTION BATTERY)", h1_style),
    Paragraph(
        "Pin cao ap tren xe dien VinFast (VF5, VF6, VF7, VF8, VF9) su dung cong nghe Lithium-ion / LFP hien dai "
        "voi he thong quan ly pin thong minh (BMS - Battery Management System). BMS lien tuc giam sat dien ap tung cell pin, "
        "nhiet do hoat dong va muc suy giam dung luong SOH.",
        body_style
    ),
    Spacer(1, 10),

    Paragraph("2. KHUYEN NGHI SAC PIN HANG NGAY DE TOI UU TUOI THO PIN", h2_style),
    Paragraph(
        "- Muc sac toi uu hang ngay: Duy tri dung luong pin tu 20% den 80% (State of Charge - SOC). "
        "Tranh de pin can kiet duoi 5% trong thoi gian dai tren 48 gio.<br/>"
        "- Chuyen di xa: Sac day 100% truoc khi khoi hanh chuyen di dai de toi uu hoa quang duong di chuyen.<br/>"
        "- Sac sieu nhanh DC: Khong nen sac nhanh DC 100% lien tuc trong ngay khi nhiet do moi truong qua nong (>40 do C). "
        "Nen uu tien sac cham AC tai nha qua dem de can bang cac cell pin.",
        body_style
    ),
    Spacer(1, 10),

    Paragraph("3. TIEU CHUAN CHONG NUOC VA XU LY KHI DI DUONG NGAP", h1_style),
    Paragraph(
        "Goi pin xe dien VinFast dat tieu chuan chong bui va chong nuoc IP67. "
        "Tuy nhien, de dam bao tuyet doi an toan he thong dien:<br/>"
        "- Khong lai xe vao vung nuoc ngap sau vuot qua nua banh xe (muc nuoc > 300 mm).<br/>"
        "- Khi xe bat buoc phai di qua doan ngap, chay deu ga voi toc do khong qua 15 km/h, khong dung lai giua vung ngap.<br/>"
        "- Neu xe bi ngap sau trong thoi gian dai, khong duoc tu y khoi dong lai. Bat buoc phai goi cuu ho 1900 23 23 89 "
        "dua ve Xuong dich vu chinh hang de kiem tra dien tro cach dien (Insulation Resistance Test).",
        body_style
    ),
    Spacer(1, 10),

    Paragraph("4. CAC BIEN CANH BAO QUAN TRONG TREN BANG DONG HO", h1_style),
    Paragraph(
        "- Bieu tuong Rua Vang (Turtle Mode): Canh bao xe dang bi gioi han cong suat do pin yeu (duoi 5%) hoac dong co qua nhiet. "
        "Lai xe can giam toc va tim tram sac gan nhat.<br/>"
        "- Den Canh bao Dien cao ap mau do: He thong phat hien ro ri cach dien hoac loi BMS. "
        "Dung xe an toan vao le duong, tat may va lien he Xuong dich vu ngay lap tuc.<br/>"
        "- Den Canh bao Ap suat lop (TPMS): Canh bao chenh lech ap suat lop vuot nguong 10%.",
        body_style
    ),
]

doc.build(elements)
print(f"Generated raw documents in {RAW_DIR}")
