# PRD bổ sung — EV Care sau MVP (Phase 2)

> Hệ thống tự vận hành: chủ xe tự phục vụ, xưởng bớt tư vấn, con người chỉ xử lý ngoại lệ.
>
> **Quan hệ với PRD MVP:** tài liệu này **bổ sung**, không thay thế [PRD_EV_Care_MVP.md](PRD_EV_Care_MVP.md) (v3.8.1). Mọi quy tắc đã chốt trong PRD MVP và `docs/specs/**` vẫn giữ nguyên, trừ khi mục 4.3 và Phụ lục C ghi rõ là thay đổi. Khi hai tài liệu khác nhau về tính năng MVP, PRD MVP và `docs/specs` là chuẩn.
>
> **Trạng thái:** Bản nháp đề xuất để thảo luận nhóm. Chưa tính năng nào trong tài liệu này được cam kết.

---

## 0. Thông tin tài liệu

| Field | Value |
| --- | --- |
| Product | EV Care — AI Agent Chăm sóc sau bán & lịch bảo dưỡng xe điện |
| Tài liệu | PRD bổ sung giai đoạn sau MVP (Phase 2) |
| Version | v0.1 |
| Status | Draft — chờ nhóm thảo luận, PO/Mentor duyệt |
| Product Owner | Lê Đức Tùng |
| Project Manager | Mai Văn Trung |
| Tech Lead | Nguyễn Lê Phước Tiến · Đinh Kim Thái · Lê Đức Tùng |
| Mentor | Phạm Văn Ngoan |
| Ngày tạo | 09/10/2026 |
| Khung thời gian dự kiến | Sau mốc M8 của MVP (30/10/2026) — xem mục 13 |

### Change log

| Version | Ngày | Thay đổi |
| --- | --- | --- |
| v0.1 | 09/10/2026 | Bản nháp đầu: 33 tính năng theo 9 nhóm, tình huống và tiêu chí chấp nhận cho từng tính năng, mô hình bài toán lập lịch, lộ trình 3 giai đoạn, câu hỏi mở. |

### Cách đọc tài liệu này

Không cần đọc hết. Mỗi vai trò nên đọc các mục sau:

| Bạn là | Nên đọc | Để biết |
| --- | --- | --- |
| PO, Mentor, người duyệt | 1, 3, 4, 6, 13, 16 | Vì sao làm, làm gì, làm trước cái gì, cần chốt gì |
| PM | 6, 13, 14, 15, 16 | Phạm vi theo giai đoạn, rủi ro, phụ thuộc |
| BA, người viết spec | 2, 5, 7, Phụ lục A | Quy tắc nghiệp vụ, tình huống, thuật ngữ |
| Backend, AI | 7, 8, 9, 10, 11 | Yêu cầu chi tiết, bài toán lập lịch, nguyên tắc AI, dữ liệu mới |
| Frontend, Design | 5, 7 (các mục có "Màn hình"), 12 | Tương tác mới, thẻ trong chat, lịch, bản đồ |
| QA | 7 (bảng tình huống + AC), 12 | Ca kiểm thử và chỉ số |

**Quy ước ký hiệu**

- **Giai đoạn:** `P2-A` Làm sớm · `P2-B` Tầm trung · `P2-C` Dài hạn.
- **Loại:** *Chức năng* (hệ thống làm được một việc mới) · *Phi chức năng* (chất lượng của việc đã làm được, ví dụ nhanh hơn, tối ưu hơn) · *Cải tiến MVP* (mở rộng một tính năng MVP đã có).
- **Mã tính năng:** `BK` đặt lịch · `HS` hồ sơ xe · `PS` cá nhân hoá · `CH` trải nghiệm chat · `AD` agent tư vấn · `WS` tự động hoá xưởng · `TA` trợ lý kỹ thuật viên · `MC` chat nhiều bên · `PL` nền tảng chung.
- **Mã khác:** `PP2-xx` pain point · `G2-x` mục tiêu · `BR-<tính năng>-xx` quy tắc nghiệp vụ · `<tính năng>-Sxx` tình huống · `AC-<tính năng>-xx` tiêu chí chấp nhận · `P2Q-xx` câu hỏi mở · `NFR-xx` yêu cầu phi chức năng.
- Các số `1.2`, `5.4`… trong cột "Trang trình bày" là số mục trên trang thuyết trình đề xuất đã chia sẻ với nhóm.

---

## 1. Tóm tắt

**Vấn đề:** MVP đã chạy được luồng xem đến hạn → hỏi đáp có nguồn → dự toán → đặt lịch theo sức chứa → check-in → hỏi thăm. Nhưng còn nhiều việc vẫn cần người làm tay:
- Chủ xe phải tự dò xưởng và giờ phù hợp với mình.
- Chủ xưởng vẫn duyệt lịch, trả lời câu hỏi về giá và bảo hành, gọi điện báo chi phí phát sinh.
- Sức chứa đang tính thô: mỗi lịch chiếm một thợ, bất kể hạng mục.
- Kỹ thuật viên chưa có công cụ riêng.

**Giải pháp Phase 2:** biến EV Care thành **hệ thống tự vận hành**. Hệ thống tự làm những việc lặp lại; con người chỉ xác nhận một chạm hoặc xử lý ngoại lệ do hệ thống đánh dấu.

```
Hãng đồng bộ ODO → Phát hiện sắp đến mốc → Tự lập lịch theo ràng buộc của chủ xe
→ Chủ xe xác nhận 1 chạm → Xưởng tự nhận theo luật → Nhắc, giải phóng chỗ, mời danh sách chờ
→ Check-in → KTV cập nhật tiến độ → Phát sinh: agent soạn báo giá, xưởng duyệt, chủ xe đồng ý
→ Hỏi thăm, đánh giá → Tính lại mốc kế tiếp
```

**Ba lợi ích chính**

| Ai | Được gì |
| --- | --- |
| Chủ xe | Đặt lịch phù hợp trong vài chạm, không phải gõ; tự quản lý lịch sử xe; tự có câu trả lời về giá, bảo hành, phụ tùng 24/7. |
| Chủ xưởng và kỹ thuật viên | Ít phải tư vấn lặp lại; lịch tự nhận theo luật; sức chứa tính đúng theo thời lượng; có trợ lý tra cứu và nhắc việc. |
| Người vận hành hệ thống | Đặt luật một lần; chỉ xử lý ngoại lệ; theo dõi bằng chỉ số. |

**Trọng tâm số 1:** tính năng **tự động lập lịch theo ràng buộc** (BK-01). Đây là yêu cầu *chức năng*, ưu tiên cao nhất. Việc **tối ưu hoá lịch** theo các mục tiêu thời gian (BK-10) là yêu cầu *phi chức năng*, để giai đoạn dài hạn.

---

## 2. Hiện trạng MVP và khoảng trống

Phase 2 xây trên những gì MVP đã có, không làm lại.

| Khu vực | MVP đã có | Khoảng trống Phase 2 xử lý |
| --- | --- | --- |
| Đặt lịch | Đặt theo sức chứa (F6, us-029); giữ chỗ 10 phút; đề xuất nhanh từ AI có lý do, xếp xưởng theo khoảng cách (us-061 BR-1503, BR-1506); hết chỗ thì đưa 2–3 phương án | Chưa có ràng buộc riêng của chủ xe (giờ rảnh, bán kính, xưởng yêu thích lưu lâu dài); chưa có luồng "xưởng yêu thích kín thì xếp chỗ khác" có hệ thống → **BK-01** |
| Đổi, huỷ | Huỷ, đổi lịch trong cùng xưởng (F6b, us-053); nhắc 24h có "xác nhận sẽ đến" (us-033) | Đổi sang xưởng khác phải huỷ rồi đặt lại (us-053 Q-1201); chưa có chính sách huỷ muộn, lỡ hẹn (ngoài phạm vi MVP) → **BK-02** |
| Sức chứa | 1 booking chiếm 1 thợ trong 1 khung (PQ-03); khoá chỗ cho khách gọi điện, vãng lai; chế độ xác nhận `auto` / `manual`; xưởng `manual` quá 12 giờ thì tự huỷ | Không tính theo thời lượng hạng mục; tự nhận chỉ bật/tắt; lịch bị tự huỷ khi xưởng chậm duyệt mà không có phương án thay thế → **WS-01, WS-02** |
| Hồ sơ xe | Trạng thái đến hạn (F3); ODO và lịch sử dịch vụ đồng bộ từ hãng | Chủ xe chưa có màn xem lịch sử đầy đủ → **HS-01** |
| Tư vấn | RAG có trích nguồn (F4); dự toán theo model + mốc (F5); báo giá HITL (F5b) | Chưa tư vấn sửa chữa ngoài mốc, chưa tra bảo hành theo VIN, chưa có báo giá phát sinh khi đang làm → **AD-01…04** |
| Chat | Chat một phiên, lưu hội thoại; agent nhớ xưởng ưa thích (AI-004) | Chưa có gợi ý một chạm có hệ thống; bộ nhớ dài hạn còn hẹp → **CH-01, CH-02, PS-01** |
| Sau dịch vụ | Hỏi thăm 12h sau `completed`, có điểm 1–5 và cờ `has_issue` (F9) | Phiếu hỗ trợ đã bỏ ở v3.7; điểm đánh giá chưa dùng để gợi ý xưởng → **PS-02, PL-02** |
| Vai trò | 2 vai trò: Chủ xe, Chủ xưởng. Giao diện gọi chủ xưởng là "Kỹ thuật viên" | Chưa có tài khoản kỹ thuật viên thật → **WS-03** (điều kiện tiên quyết của TA, MC) |

---

## 3. Vấn đề (Pain points)

Mọi pain point dưới đây ở mức **Giả định**. Chúng cần được kiểm chứng theo cách đã làm với PRD MVP, xem [surveys.md](../../personal/tungld-03005/surveys.md). Giả thuyết đề xuất bổ sung nằm ở Phụ lục B. Pain point nào mở rộng từ pain point MVP thì ghi rõ.

### 3.1 Phía chủ xe

| ID | Pain point | Mở rộng từ | Tính năng |
| --- | --- | --- | --- |
| PP2-01 | **Phải tự dò xưởng và giờ khớp với mình.** Chủ xe có giờ rảnh, khu vực và xưởng quen, nhưng phải tự thử từng xưởng, từng khung. Xưởng quen kín lịch thì bỏ cuộc hoặc gọi điện thoả thuận. | PP-02 | BK-01, BK-04, BK-05, CH-01 |
| PP2-02 | **Lặp lại việc đặt lịch mỗi mốc.** Đi bảo dưỡng ở cùng một xưởng, cùng kiểu giờ, nhưng lần nào cũng đặt lại từ đầu. | PP-01 | BK-06, PS-01 |
| PP2-03 | **Không có nơi xem lại lịch sử bảo dưỡng.** Không nhớ lần trước làm gì, ở đâu, hết bao nhiêu; hoá đơn giấy thất lạc; khó chứng minh lịch sử khi bán xe. | — | HS-01 |
| PP2-04 | **Không biết làm sớm hay làm trễ mốc thì sao.** Sắp đi xa muốn làm trước nhưng không biết có cần không, mốc sau tính thế nào, có ảnh hưởng bảo hành không. | PP-01, PP-04 | BK-03 |
| PP2-05 | **Gõ chat trên điện thoại chậm và không biết nên hỏi gì.** | — | CH-01, CH-02 |
| PP2-06 | **Không biết trước giá sửa chữa, phụ tùng, gói bảo hành; bất ngờ với chi phí phát sinh.** Phải gọi xưởng hỏi, hoặc đến nơi mới biết. | PP-03, PP-04 | AD-01…04 |
| PP2-07 | **Đến xưởng vẫn phải chờ, hoặc xưởng thiếu phụ tùng phải hẹn lại; xe nằm xưởng lâu.** | PP-02 | BK-08, BK-09, BK-10, WS-02 |
| PP2-08 | **Gợi ý không hiểu mình.** Được gợi ý lại xưởng mình từng không hài lòng; agent không nhớ thói quen; câu trả lời quá dài hoặc quá kỹ thuật. | — | PS-01…05 |

### 3.2 Phía xưởng

| ID | Pain point | Mở rộng từ | Tính năng |
| --- | --- | --- | --- |
| PP2-09 | **Chủ xưởng vẫn phải duyệt tay và tư vấn lặp lại.** Chế độ tự nhận chỉ bật hoặc tắt; câu hỏi về giá, bảo hành, phụ tùng vẫn dồn về xưởng. | PP-05 | WS-01, AD-01…04 |
| PP2-10 | **Chỗ bị bỏ trống vì huỷ muộn và lỡ hẹn**, trong khi khách khác muốn đặt không còn chỗ. | PP-07 | BK-02, BK-07 |
| PP2-11 | **Sức chứa tính thô.** Bảo dưỡng lớn và kiểm tra nhanh đều tính là một chỗ, nên lúc thì thợ ngồi chơi, lúc thì quá tải. | PP-06 | WS-02, BK-10 |
| PP2-12 | **Kỹ thuật viên thiếu công cụ.** Không nhớ lịch được giao, không tra nhanh được lịch sử xe, quên mình đã làm cho ai. | — | WS-03, TA-01, TA-02 |
| PP2-13 | **Trao đổi với khách qua điện thoại hoặc Zalo cá nhân**, không lưu vết; báo giá phát sinh mất thời gian chờ khách đồng ý. | PP-05 | AD-04, MC-01, MC-02 |

---

## 4. Mục tiêu & phi mục tiêu

### 4.1 Mục tiêu

| # | Mục tiêu | Pain point | Đo bằng (mục 12) |
| --- | --- | --- | --- |
| G2-1 | Chủ xe đặt xong một lịch **thoả ràng buộc của mình** trong vài chạm, không cần gõ chữ. | PP2-01, PP2-05 | M-01, M-02 |
| G2-2 | Khi xưởng yêu thích kín lịch, hệ thống **luôn đưa được phương án thay thế** thoả ràng buộc cứng, hoặc nói rõ vì sao không có và gợi ý nới ràng buộc. | PP2-01 | M-03 |
| G2-3 | Chủ xe **tự trả lời được** câu hỏi về lịch sử xe, giá, bảo hành, phụ tùng mà không cần gọi xưởng. | PP2-03, PP2-06 | M-08 |
| G2-4 | Xưởng **chỉ duyệt tay ngoại lệ**; chỗ bị bỏ trống do huỷ muộn và lỡ hẹn giảm. | PP2-09, PP2-10 | M-05, M-06, M-07 |
| G2-5 | Sức chứa phản ánh đúng thời lượng công việc; giảm thời gian khách chờ và thời gian thợ rảnh. | PP2-07, PP2-11 | M-09, M-10 |
| G2-6 | Kỹ thuật viên có tài khoản và trợ lý riêng. | PP2-12 | M-11 |
| G2-7 | Cá nhân hoá **có kiểm soát**: chủ xe đồng ý, xem được và xoá được những gì hệ thống nhớ. | PP2-08 | M-12 |

### 4.2 Phi mục tiêu (Phase 2 không làm)

- Thanh toán, đặt cọc trực tuyến. BK-02 chỉ ghi nhận đặt cọc là hướng mở rộng sau.
- App mobile native, Zalo Mini App.
- Chẩn đoán lỗi qua ảnh, telematics, OBD, dự đoán hỏng hóc.
- Hệ thống kho phụ tùng đầy đủ (WMS/ERP). BK-09 chỉ cần xưởng khai báo tồn kho đơn giản.
- Định giá động, upsell, khuyến mãi theo doanh thu.
- Xưởng ngoài mạng lưới hãng.
- Nhiều xe trên một tài khoản. Vẫn ngoài phạm vi; các ý liên quan nhiều xe trong HS-02 chỉ bật khi mục này được mở.

### 4.3 Thay đổi so với phạm vi MVP

| Nội dung MVP | Phase 2 đề xuất |
| --- | --- |
| Phi mục tiêu "quản lý phụ tùng" | Mở một phần: khai báo tồn kho đơn giản và giá phụ tùng sửa chữa (BK-09, AD-02). Vẫn không làm WMS. |
| "Không có role nhân viên xưởng" | Thêm vai trò **Kỹ thuật viên** (WS-03). Cần đổi tên trong mã nguồn, vì `/technician/*` đang chỉ chủ xưởng (P2Q-01). |
| "Tính theo thời lượng từng hạng mục là phase sau" (F6) | Làm ở WS-02. |
| "Đổi sang xưởng khác: huỷ rồi đặt mới" (us-053 Q-1201) | Đổi xưởng trong một thao tác, giữ được chỗ mới rồi mới trả chỗ cũ (BK-01 tình huống S07). |
| "Phạt no-show, chấm điểm uy tín" ngoài phạm vi (us-053) | Làm ở BK-02, không có phạt tiền. |
| Phiếu hỗ trợ bỏ ở v3.7 | Không đưa lại. Đánh giá thấp được chuyển cho xưởng xử lý qua PL-02. |

---

## 5. Người dùng & vai trò

| Vai trò | Mô tả | Kênh | Thay đổi Phase 2 |
| --- | --- | --- | --- |
| **Chủ xe** | Như MVP: chủ 01 xe đã được hãng xác thực. | Web App chủ xe (mobile-first) | Thêm ràng buộc đặt lịch, lịch sử xe, bộ nhớ agent, màn quyền riêng tư. |
| **Chủ xưởng** | Như MVP: quản lý 01 xưởng, kiêm cố vấn dịch vụ. | Workshop Portal | Cấu hình luật tự nhận, thời lượng hạng mục, bảng giá sửa chữa, tồn kho; quản lý KTV. |
| **Kỹ thuật viên (MỚI)** | Thợ của xưởng, do chủ xưởng tạo tài khoản. Chỉ thấy xe và lịch của xưởng mình. | Workshop Portal (mobile-first cho KTV) | Vai trò mới — WS-03. |
| **Hệ thống: bộ lập lịch** | Service backend tìm và giữ lịch thoả ràng buộc (BK-01), sau này tối ưu (BK-10). | — | Mới. |
| **Hệ thống: AI Agent** | Như MVP, thêm tool lập lịch, tra lịch sử, tư vấn, bộ nhớ. | Chat | Mở rộng. |
| **Hệ thống hãng** | Nguồn sự thật: xe, ODO, lịch sử dịch vụ, bảo hành. | API | Cần thêm: bảo hành theo hạng mục, chiến dịch triệu hồi (P2Q-06). |
| **Người vận hành EV Care** | Đặt cấu hình chung (ngưỡng, trọng số). | Biến môi trường, seed | Chưa có giao diện quản trị ở Phase 2. |

### 5.1 Kịch bản tiêu biểu

- **UC2-A — Xưởng quen kín lịch.**
  1. Chủ xe đã lưu ràng buộc: rảnh sáng thứ Bảy, bán kính 5 km, xưởng yêu thích là Xưởng Cầu Giấy.
  2. Xe còn 600 km đến mốc 24.000 km. Hệ thống tự tìm lịch.
  3. Sáng thứ Bảy Xưởng Cầu Giấy đã kín, nên hệ thống giữ sẵn hai phương án: Xưởng Mỹ Đình 08:00 thứ Bảy (3,4 km), hoặc Xưởng Cầu Giấy 11:00 cùng ngày.
  4. Chủ xe chọn một phương án, bấm Xác nhận và nhận vé lịch hẹn.
  5. Chủ xe không gõ chữ nào.
- **UC2-B — Phát sinh khi đang làm.**
  1. KTV phát hiện lốp sau trái phồng hông, chụp ảnh và chọn phụ tùng.
  2. Agent soạn báo giá phát sinh. Chủ xưởng duyệt một chạm.
  3. Chủ xe nhận ảnh và giá trên app, bấm "Đồng ý thay". Tiến độ tự cập nhật.
- **UC2-C — Hỏi bảo hành ở nhà.** Lúc 22h, chủ xe hỏi "Xe tôi còn bảo hành pin không?". Agent tra theo VIN, trả lời kèm trích nguồn chính sách của hãng, rồi gợi ý đặt lịch mốc sắp tới để giữ bảo hành.
- **UC2-D — KTV đầu ca.** KTV hỏi "Hôm nay tôi có mấy xe?". Agent liệt kê 4 xe kèm giờ và hạng mục, rồi tóm tắt xe 10h: triệu chứng khách kể trong chat và báo giá đã duyệt.
- **UC2-E — Huỷ muộn và danh sách chờ.** Chủ xe A huỷ lịch 09:30 lúc 7 giờ sáng cùng ngày, hệ thống tính một lần huỷ muộn. Chỗ được trả ngay. Chủ xe B đang chờ khung này nhận lời mời, giữ chỗ 15 phút, bấm nhận.

---

## 6. Phạm vi & ưu tiên

| Giai đoạn | Mã | Tính năng | Loại | MoSCoW | Phụ thuộc | Trang trình bày |
| --- | --- | --- | --- | --- | --- | --- |
| P2-A | BK-01 | Tự động lập lịch theo ràng buộc của chủ xe | Chức năng | Must | PL-01 | 1.2 |
| P2-A | BK-02 | Chính sách huỷ lịch và lỡ hẹn | Cải tiến MVP | Must | — | 1.3 |
| P2-A | BK-03 | Bảo dưỡng sớm hoặc trễ so với mốc | Cải tiến MVP | Should | — | 1.5 |
| P2-A | BK-04 | Widget lịch | Chức năng | Should | BK-01 | 1.6 |
| P2-A | BK-05 | Bản đồ xưởng (Google Maps) | Chức năng | Should | P2Q-07 | 1.7 |
| P2-A | HS-01 | Tra cứu lịch sử bảo dưỡng phía chủ xe | Chức năng | Must | — | 2.1 |
| P2-A | PS-01 | Bộ nhớ ngắn hạn và dài hạn của agent | Cải tiến MVP | Should | PL-01 | 3.1 |
| P2-A | CH-01 | Gợi ý một chạm | Chức năng | Must | — | 4.1 |
| P2-A | CH-02 | Thẻ tương tác trong chat | Cải tiến MVP | Should | CH-01 | 4.2 |
| P2-A | AD-01 | Giá bảo dưỡng theo mốc, tách phần bảo hành | Cải tiến MVP | Should | — | 5.3 |
| P2-A | WS-01 | Tự nhận lịch hẹn có điều kiện | Cải tiến MVP | Must | BK-02 | 6.1 |
| P2-A | WS-02 | Sức chứa theo thời lượng và hạn phản hồi | Cải tiến MVP | Should | — | 6.2 |
| P2-A | PL-01 | Quyền riêng tư và sự đồng ý | Chức năng | Must | — | N.1 |
| P2-A | PL-03 | Chỉ số đo hiệu quả | Phi chức năng | Must | — | N.3 |
| P2-B | BK-06 | Lịch bảo dưỡng định kỳ tại xưởng quen | Chức năng | Should | BK-01 | 1.1 |
| P2-B | BK-07 | Danh sách chờ | Chức năng | Could | BK-02 | 1.8 |
| P2-B | BK-08 | Báo trễ chủ động hai chiều | Chức năng | Could | WS-02 | 1.9 |
| P2-B | HS-02 | Gộp việc vào một lần đến xưởng | Chức năng | Could | P2Q-06 | 2.2 |
| P2-B | PS-02 | Cá nhân hoá theo phản hồi dịch vụ | Chức năng | Should | — | 3.2 |
| P2-B | PS-03 | Giải thích và phản hồi gợi ý | Cải tiến MVP | Should | BK-01 | 3.5 |
| P2-B | AD-02 | Tư vấn phụ tùng và báo giá sửa chữa | Chức năng | Should | Bảng giá sửa chữa | 5.1 |
| P2-B | AD-03 | Tư vấn bảo hành và gói bảo hành | Chức năng | Should | P2Q-05 | 5.2 |
| P2-B | AD-04 | Báo giá phát sinh khi thay phụ tùng | Chức năng | Should | WS-03 | 5.4 |
| P2-B | WS-03 | Tài khoản kỹ thuật viên và tự phân công | Chức năng | Must | P2Q-01 | 6.3 |
| P2-B | TA-01 | Trợ lý tra cứu và nhắc việc cho KTV | Chức năng | Should | WS-03 | 7.1 |
| P2-B | PL-02 | Chuyển sang người thật | Chức năng | Should | — | N.2 |
| P2-C | BK-09 | Chọn xưởng theo phụ tùng sẵn có | Chức năng | Could | P2Q-08 | 1.4 |
| P2-C | BK-10 | Tối ưu hoá lập lịch | **Phi chức năng** | Could | BK-01, WS-02, dữ liệu | 1.10 |
| P2-C | PS-04 | Gợi ý từ chủ xe có đặc điểm tương đồng | Chức năng | Could | Đủ dữ liệu | 3.3 |
| P2-C | PS-05 | Agent trả lời theo phong cách giao tiếp | Chức năng | Could | PS-01 | 3.4 |
| P2-C | TA-02 | Hỗ trợ tại khoang làm việc | Chức năng | Could | TA-01 | 7.2 |
| P2-C | MC-01 | Chat theo từng lịch hẹn giữa xưởng và chủ xe | Chức năng | Could | WS-03 | 8.1 |
| P2-C | MC-02 | Agent cùng tham gia luồng chat | Chức năng | Could | MC-01 | 8.2 |

**Tổng:** 33 tính năng. P2-A có 14, P2-B có 12, P2-C có 7.

**Nguyên tắc xếp giai đoạn:**
- **P2-A** chỉ gồm việc dựa trên dữ liệu và service MVP đã có.
- **P2-B** cần thêm vai trò mới (KTV) hoặc dữ liệu mới (bảng giá sửa chữa, bảo hành theo VIN).
- **P2-C** cần tích hợp ngoài hoặc cần đủ dữ liệu vận hành thật.

---

## 7. Yêu cầu tính năng

Mỗi tính năng gồm năm phần:
- **Thông tin chung.**
- **Mô tả.**
- **Quy tắc nghiệp vụ (BR).**
- **Tình huống:** luồng chính, luồng thay thế, ngoại lệ.
- **Tiêu chí chấp nhận (AC).**

Tình huống ghi theo dạng: *ai làm gì → hệ thống xử lý thế nào → người dùng thấy gì*.

Mọi tính năng phải tuân thủ nguyên tắc AI của PRD MVP (§7) và phần bổ sung ở mục 9.

### 7.1 Nhóm BK — Đặt lịch

#### BK-01 — Tự động lập lịch theo ràng buộc của chủ xe

| Giai đoạn | Loại | MoSCoW | Pain point | Nền tảng MVP |
| --- | --- | --- | --- | --- |
| P2-A | Chức năng | Must | PP2-01 | us-029 (sức chứa, đề xuất 2–3 phương án), us-061 (đề xuất nhanh, lý do, xếp theo khoảng cách), AI-004 (xưởng ưa thích) |

**Mô tả.** Hệ thống nhận các ràng buộc của chủ xe, kết hợp với các yếu tố của xưởng, rồi tìm và giữ một lịch hẹn hợp lệ. Nếu xưởng yêu thích còn chỗ thì xếp luôn. Nếu kín thì tìm giờ khác hoặc xưởng khác vẫn thoả ràng buộc. Một bộ lập lịch dùng chung cho chat, màn đặt lịch, lịch định kỳ (BK-06) và đổi lịch.

BK-01 chỉ yêu cầu **tìm được lịch hợp lệ và xếp hạng hợp lý**. Việc **tìm lịch tốt nhất** theo các mục tiêu thời gian thuộc BK-10.

**Ràng buộc của chủ xe**

| Loại | Ràng buộc | Nguồn | Ví dụ |
| --- | --- | --- | --- |
| Cứng | Khung thời gian rảnh | Chat, cài đặt, Google Calendar (nếu đồng ý — PL-01) | "Sáng thứ Bảy, hoặc sau 17h ngày thường" |
| Cứng | Khu vực hoặc bán kính tối đa | Vị trí GPS, địa chỉ nhà/chỗ làm đã lưu | "Trong 5 km quanh nhà" |
| Cứng | Xe và hạng mục cần làm | Mốc đến hạn (F3), triệu chứng kể trong chat | Mốc 24.000 km |
| Cứng | Hạn chót | Ngày đến hạn của mốc | Trước 26/10 |
| Mềm | Xưởng yêu thích | Chủ xe chọn, hoặc suy ra từ lịch sử (PS-01) | Xưởng Cầu Giấy |
| Mềm | Giờ hay chọn | Bộ nhớ agent | 08:00–10:00 |
| Mềm | Mức giá, đánh giá tối thiểu | Cài đặt, phản hồi (PS-02) | ≥ 4 sao |

**Yếu tố của xưởng:** giờ hoạt động; sức chứa từng khung (số thợ − chỗ dự phòng − chỗ đã khoá, sau này tính theo thời lượng — WS-02); chế độ và luật tự nhận (WS-01); phụ tùng sẵn có (BK-09, khi có); trạng thái hoạt động.

**Quy tắc nghiệp vụ**

- **BR-BK01-01 — Ràng buộc cứng không được vi phạm.** Không đề xuất lịch nào vi phạm ràng buộc cứng. Chỉ được nới ràng buộc cứng khi chủ xe đồng ý rõ ràng (S05).
- **BR-BK01-02 — Thứ tự tìm kiếm:**
  1. Xưởng yêu thích, trong khung rảnh.
  2. Xưởng yêu thích, giờ khác vẫn trong khung rảnh.
  3. Xưởng khác thoả mọi ràng buộc cứng, xếp hạng theo điểm khớp ràng buộc mềm.
  4. Không có phương án nào: gợi ý nới ràng buộc hoặc vào danh sách chờ (BK-07).
- **BR-BK01-03 — Số phương án:** trả tối đa 3 phương án. Mỗi phương án có lý do ngắn, ví dụ "đúng xưởng bạn thích", "cách 3,4 km", "còn 1 chỗ". Tái dùng BR-1503 của us-061.
- **BR-BK01-04 — Điểm khớp ở P2-A dùng luật đơn giản,** cộng điểm có trọng số: đúng xưởng yêu thích, khoảng cách, độ gần giờ hay chọn, đánh giá. Trọng số đặt trong cấu hình. BK-10 sẽ thay phần này.
- **BR-BK01-05 — Ba mức tự động hoá**, chủ xe tự chọn, mặc định là mức 2:
  1. Gợi ý: chỉ đưa phương án.
  2. Giữ chỗ sẵn: hệ thống giữ phương án tốt nhất, chủ xe một chạm xác nhận.
  3. Tự đặt: hệ thống tự xác nhận. Chỉ dùng khi chủ xe bật, và vẫn gửi thông báo kèm nút huỷ.
- **BR-BK01-06 — Giữ chỗ chủ động** (mức 2) dùng cơ chế giữ chỗ MVP (`pending`, `hold_expires_at`). Thời gian giữ cho đề xuất chủ động là `PROACTIVE_HOLD_HOURS` (đề xuất 24 giờ — P2Q-03). Quá hạn chưa xác nhận thì tự trả chỗ và không tính là huỷ.
- **BR-BK01-07 — Một service sức chứa.** Bộ lập lịch không tự đếm chỗ. Nó gọi Booking & Capacity Service hiện có (us-029 BR-011) để kiểm tra và giữ chỗ, nhằm tránh đặt trùng khi chạy đồng thời.
- **BR-BK01-08 — Một lịch mở mỗi xe.** Giữ quy tắc us-029 BR-013. Nếu xe đã có lịch mở thì bộ lập lịch chỉ đề xuất **đổi lịch**, không tạo lịch thứ hai.
- **BR-BK01-09 — Đổi xưởng trong một thao tác.** Khi chủ xe chọn phương án ở xưởng khác cho một lịch đang mở, hệ thống giữ chỗ mới trước, rồi mới huỷ lịch cũ trong cùng giao dịch. Không có lúc nào mất cả hai. Đây là mở rộng của us-053.
- **BR-BK01-10 — Lưu ràng buộc.** Ràng buộc cứng và mềm chủ xe khai được lưu vào hồ sơ đặt lịch, dùng cho lần sau. Mọi ràng buộc suy ra (không do chủ xe khai) phải hiện cho chủ xe thấy và sửa được (PL-01).

**Tình huống**

| ID | Tình huống | Hệ thống xử lý | Chủ xe thấy |
| --- | --- | --- | --- |
| BK01-S01 | Xưởng yêu thích còn chỗ trong khung rảnh | Giữ khung sớm nhất khớp giờ hay chọn | Thẻ lịch hẹn đã giữ sẵn, nút "Xác nhận" |
| BK01-S02 | Xưởng yêu thích kín đúng giờ mong muốn, còn giờ khác trong khung rảnh | Đề xuất giờ khác cùng xưởng, xếp đầu | "Xưởng Cầu Giấy kín 08:00, còn 11:00 cùng ngày" |
| BK01-S03 | Xưởng yêu thích kín cả khung rảnh | Tìm xưởng khác thoả ràng buộc cứng, tối đa 3 phương án có lý do | Danh sách phương án ở xưởng khác, kèm khoảng cách và số chỗ |
| BK01-S04 | Chủ xe chưa có xưởng yêu thích | Bỏ bước 1–2, xếp theo khoảng cách và giờ hay chọn | 3 phương án gần nhất |
| BK01-S05 | Không có phương án nào thoả ràng buộc cứng | Gợi ý nới cụ thể: "mở rộng bán kính lên 8 km có 2 phương án", "thêm chiều Chủ nhật có 1 phương án"; hoặc vào danh sách chờ | Nút "Mở rộng bán kính", "Thêm ngày khác", "Vào danh sách chờ" |
| BK01-S06 | Xe đã có lịch đang mở | Chỉ đề xuất đổi lịch (BR-BK01-08) | "Bạn đã có lịch ngày 24/10. Đổi sang phương án này?" |
| BK01-S07 | Chủ xe chọn phương án ở xưởng khác cho lịch đang mở | Giữ chỗ mới, huỷ lịch cũ trong một giao dịch (BR-BK01-09); huỷ lịch cũ do đổi xưởng không tính là huỷ muộn | Vé mới; thông báo lịch cũ đã huỷ |
| BK01-S08 | Hai chủ xe cùng được đề xuất chỗ cuối của một khung | Service sức chứa chỉ cho một người giữ thành công | Người thứ hai nhận ngay phương án kế tiếp |
| BK01-S09 | Chủ xe không xác nhận lịch giữ chủ động trước hạn | Tự trả chỗ, không tính huỷ; nhắc một lần trước khi hết hạn | Thông báo "Lịch giữ sẵn đã hết hạn — tìm lại?" |
| BK01-S10 | Ràng buộc mâu thuẫn ("sáng thứ Bảy" nhưng xưởng yêu thích không mở thứ Bảy) | Báo mâu thuẫn, đưa lựa chọn giữ xưởng hoặc giữ giờ | "Xưởng Cầu Giấy nghỉ thứ Bảy. Ưu tiên xưởng hay ưu tiên giờ?" |
| BK01-S11 | Chủ xe tắt quyền vị trí, chưa lưu địa chỉ | Hỏi khu vực; tái dùng us-061 AF-1501/1502 | Gợi ý một chạm "Gần nhà", "Gần chỗ làm", "Chọn trên bản đồ" |
| BK01-S12 | Mức "Tự đặt": hệ thống tự xác nhận | Tạo lịch `confirmed` theo luật xưởng; gửi thông báo | Thông báo kèm nút "Huỷ" và "Đổi giờ"; huỷ trong 2 giờ đầu không tính |
| BK01-S13 | Xưởng báo không phục vụ được một lịch đã xác nhận | Gọi bộ lập lịch tìm phương án thay thế với ràng buộc cũ; giữ chỗ phương án tốt nhất | "Xưởng báo bận. Mình đã giữ sẵn 2 phương án khác" |

**Màn hình và chat:** chip "Tôi muốn đặt lịch bảo dưỡng" (CH-01) → các bước hỏi bằng gợi ý: ở đâu, xưởng nào, khi nào rảnh, giờ nào → thẻ tóm tắt → vé. Mục Cài đặt có thêm khối **Thói quen đặt lịch** để xem và sửa ràng buộc đã lưu.

**Tiêu chí chấp nhận**

- AC-BK01-01: *Given* xưởng yêu thích còn chỗ trong khung rảnh, *when* chủ xe yêu cầu đặt lịch, *then* phương án đầu tiên là xưởng yêu thích.
- AC-BK01-02: *Given* xưởng yêu thích kín cả khung rảnh, *when* yêu cầu đặt lịch, *then* trả 1–3 phương án ở xưởng khác, mọi phương án thoả ràng buộc cứng và có lý do.
- AC-BK01-03: Không phương án nào vi phạm ràng buộc cứng. Kiểm tra bằng bộ test sinh ngẫu nhiên ≥ 500 tổ hợp ràng buộc.
- AC-BK01-04: *Given* không có phương án hợp lệ, *then* hệ thống không tự nới ràng buộc mà đưa lựa chọn nới cụ thể hoặc danh sách chờ.
- AC-BK01-05: Đổi xưởng cho lịch đang mở: nếu giữ chỗ mới thất bại thì lịch cũ giữ nguyên.
- AC-BK01-06: AC-F6-01 của MVP vẫn đạt khi yêu cầu đến từ bộ lập lịch (20 yêu cầu đồng thời, còn 1 chỗ → đúng 1 thành công).
- AC-BK01-07: Thời gian trả phương án ≤ 2 giây (p90) cho bán kính 10 km và cửa sổ 14 ngày (NFR-03).

---

#### BK-02 — Chính sách huỷ lịch và lỡ hẹn

| Giai đoạn | Loại | MoSCoW | Pain point | Nền tảng MVP |
| --- | --- | --- | --- | --- |
| P2-A | Cải tiến MVP | Must | PP2-10 | us-053 (huỷ, đổi), us-033 (nhắc 24h, "xác nhận sẽ đến"), us-037 (check-in) |

**Mô tả.** Định nghĩa rõ huỷ sớm, huỷ muộn và lỡ hẹn. Đếm số lần trong một cửa sổ thời gian, áp dụng các bậc xử lý tăng dần, không phạt tiền. Áp dụng công bằng cho cả xưởng.

**Quy tắc nghiệp vụ**

- **BR-BK02-01 — Định nghĩa** (ngưỡng trong cấu hình — P2Q-04):
  - **Huỷ sớm:** huỷ trước giờ hẹn ≥ `LATE_CANCEL_HOURS`, mặc định 24h. Không tính.
  - **Huỷ muộn:** huỷ trong vòng `LATE_CANCEL_HOURS`.
  - **Lỡ hẹn:** quá giờ hẹn `NO_SHOW_GRACE_MIN` (mặc định 30 phút) mà chưa check-in, và chủ xe không báo trễ (BK-08).
- **BR-BK02-02 — Đếm theo cửa sổ trượt** `RELIABILITY_WINDOW_DAYS`, mặc định 90 ngày. Một lần lỡ hẹn tính 1 điểm, một lần huỷ muộn tính 0,5 điểm (P2Q-04).
- **BR-BK02-03 — Bậc xử lý:**

| Điểm trong cửa sổ | Xử lý |
| --- | --- |
| < 1 | Bình thường |
| 1 – < 2 | Nhắc nhẹ về chính sách khi đặt lịch tiếp |
| 2 – < 3 | Bắt buộc bấm "Xác nhận sẽ đến" trước giờ hẹn 24h; không xác nhận trước 12h thì hệ thống tự trả chỗ, báo chủ xe và không tính thêm điểm |
| ≥ 3 | Chỉ đặt được ở xưởng chế độ duyệt tay, hoặc trong giờ thấp điểm; xưởng thấy nhãn "cần xác nhận" |

- **BR-BK02-04 — Không tính điểm khi:** xưởng huỷ hoặc đổi; xưởng trễ quá `WS_LATE_MIN`; đổi xưởng do BK-01 S07 hoặc S13; chủ xe báo bất khả kháng và xưởng chấp nhận miễn; huỷ trong 2 giờ đầu của lịch "Tự đặt".
- **BR-BK02-05 — Lỡ hẹn được ghi nhận** khi chủ xưởng đánh dấu trên Workshop Board, hoặc hệ thống tự đánh dấu sau `NO_SHOW_GRACE_MIN + 60` phút nếu xưởng không thao tác. Chủ xe được khiếu nại trong 72 giờ; chủ xưởng quyết định.
- **BR-BK02-06 — Công bằng hai chiều.** Xưởng huỷ lịch đã xác nhận trong vòng `LATE_CANCEL_HOURS` thì bị tính vào chỉ số tin cậy của xưởng. Chỉ số này ảnh hưởng thứ hạng trong BK-01.
- **BR-BK02-07 — Minh bạch.** Chủ xe xem được điểm của mình và lý do từng lần tính trong mục Lịch của tôi. Bậc xử lý được báo trước khi áp dụng.
- **BR-BK02-08 — Không phạt tiền ở Phase 2.** Đặt cọc nằm ngoài phạm vi (4.2).

**Tình huống**

| ID | Tình huống | Hệ thống xử lý | Kết quả |
| --- | --- | --- | --- |
| BK02-S01 | Huỷ trước 2 ngày | Huỷ, trả chỗ, không tính | "Đã huỷ" |
| BK02-S02 | Huỷ lúc 7h cho lịch 9h30 cùng ngày | Huỷ, trả chỗ, +0,5 điểm, mời danh sách chờ (BK-07) | Thông báo đã tính một lần huỷ muộn, kèm lý do |
| BK02-S03 | Quá 30 phút chưa check-in, không báo trễ | Đánh dấu chờ xưởng xác nhận lỡ hẹn | Chủ xe nhận "Bạn có đang tới không?" với nút "Đang tới", "Huỷ" |
| BK02-S04 | Chủ xe đã báo trễ 20 phút (BK-08) | Không tính lỡ hẹn trong khoảng trễ đã báo | Xưởng thấy giờ đến dự kiến mới |
| BK02-S05 | Xưởng huỷ lịch lúc 8h cho lịch 10h | Không tính điểm chủ xe; tính chỉ số xưởng; gọi BK-01 S13 | Phương án thay thế giữ sẵn |
| BK02-S06 | Chủ xe ở bậc 2, không bấm xác nhận sẽ đến | Trước 12h, tự trả chỗ và thông báo | "Lịch đã được trả vì chưa xác nhận" |
| BK02-S07 | Chủ xe ở bậc 3 đặt lịch | BK-01 chỉ đề xuất xưởng duyệt tay hoặc giờ thấp điểm | Giải thích ngắn lý do giới hạn |
| BK02-S08 | Chủ xe khiếu nại lần lỡ hẹn | Chủ xưởng xem và miễn | Điểm được trừ lại |
| BK02-S09 | Điểm rơi khỏi cửa sổ 90 ngày | Tự hạ bậc | Thông báo đã trở lại bình thường |

**Tiêu chí chấp nhận**

- AC-BK02-01: Huỷ ở mốc đúng bằng `LATE_CANCEL_HOURS` được tính là huỷ sớm.
- AC-BK02-02: Các trường hợp ở BR-BK02-04 không làm tăng điểm.
- AC-BK02-03: Mọi lần tính điểm có bản ghi lý do, thời điểm và lịch hẹn liên quan; chủ xe xem được.
- AC-BK02-04: Bậc xử lý tự hạ khi điểm rơi khỏi cửa sổ, không cần người thao tác.

---

#### BK-03 — Bảo dưỡng sớm hoặc trễ so với mốc

| Giai đoạn | Loại | MoSCoW | Pain point | Nền tảng MVP |
| --- | --- | --- | --- | --- |
| P2-A | Cải tiến MVP | Should | PP2-04 | F3 (trạng thái đến hạn), F7 (nhắc), F4 (RAG có nguồn) |

**Mô tả.** Cho phép đặt lịch trước mốc trong ngưỡng hợp lý, giải thích khi quá sớm, tính lại mốc kế tiếp theo thực tế, và xử lý rõ trường hợp trễ mốc.

**Quy tắc nghiệp vụ**

- **BR-BK03-01:** Sớm trong ngưỡng `EARLY_SERVICE_DAYS` hoặc `EARLY_SERVICE_KM` (đề xuất 30 ngày hoặc 1.000 km — P2Q-09; phải khớp chính sách hãng) thì đặt bình thường.
- **BR-BK03-02:** Sớm hơn ngưỡng thì agent giải thích có thể chưa cần, kèm nguồn nếu tài liệu hãng có. Agent gợi ý "Kiểm tra nhanh" nếu xưởng có hạng mục này. Chủ xe vẫn muốn thì vẫn cho đặt, sau một bước xác nhận.
- **BR-BK03-03:** Mốc kế tiếp luôn tính từ **ngày và ODO thực tế** của lần bảo dưỡng do hãng đồng bộ về, không theo mốc danh nghĩa. Đây là quy tắc F3 hiện có, cần kiểm tra lại cho trường hợp làm sớm.
- **BR-BK03-04:** Trễ mốc (`OVERDUE`) thì BK-01 ưu tiên khung sớm nhất. Agent chỉ cảnh báo về bảo hành khi tài liệu hãng có nêu (nguyên tắc no-source-no-claim, PQ-07).
- **BR-BK03-05:** Không tự nêu thời gian ân hạn hay ngưỡng mất bảo hành khi tài liệu hãng không ghi.

**Tình huống**

| ID | Tình huống | Xử lý | Kết quả |
| --- | --- | --- | --- |
| BK03-S01 | Còn 20 ngày đến mốc, muốn làm vì sắp đi xa | Trong ngưỡng, đặt bình thường | Luồng BK-01 |
| BK03-S02 | Còn 4 tháng đến mốc | Giải thích, gợi ý kiểm tra nhanh | Hai nút "Kiểm tra nhanh", "Vẫn bảo dưỡng đầy đủ" |
| BK03-S03 | Đã làm sớm 1.000 km | Mốc kế tiếp tính từ ODO thực tế | Màn Home hiển thị mốc mới |
| BK03-S04 | Quá hạn 2 tuần | Ưu tiên khung sớm nhất; cảnh báo bảo hành nếu có nguồn | Nhãn "Quá hạn" và phương án sớm nhất |
| BK03-S05 | Quá hạn, tài liệu không nói gì về bảo hành | Không khẳng định; gợi ý hỏi xưởng | "Tài liệu hãng chưa nêu, bạn nên hỏi xưởng" |

**Tiêu chí chấp nhận**

- AC-BK03-01: Sau một lần bảo dưỡng sớm, mốc kế tiếp hiển thị khớp công thức tính từ ODO và ngày thực tế.
- AC-BK03-02: Không câu trả lời nào về bảo hành khi làm trễ mốc thiếu trích nguồn (eval tự động).

---

#### BK-04 — Widget lịch

| Giai đoạn | Loại | MoSCoW | Pain point | Nền tảng MVP |
| --- | --- | --- | --- | --- |
| P2-A | Chức năng | Should | PP2-01 | F3 (ngày đến hạn), F6b (lịch của tôi), sức chứa theo khung |

**Mô tả.** Một lịch tháng hoặc tuần, đặt ở Trang chủ và màn Đặt lịch. Lịch hiển thị cửa sổ đến hạn, lịch hẹn, ngày chủ xe bận, và cho đặt ngay từ một ngày. Chủ xưởng có bản lịch tuần với số chỗ còn lại.

**Quy tắc nghiệp vụ**

- **BR-BK04-01:** Ngày trong cửa sổ đến hạn được tô nhận biết. Cửa sổ đến hạn là từ khi `DUE_SOON` tới ngày đến hạn dự kiến.
- **BR-BK04-02:** Ngày bận chỉ hiện khi chủ xe đã đồng bộ lịch (PL-01). Hệ thống chỉ đọc trạng thái bận/rảnh (free/busy), không đọc nội dung sự kiện.
- **BR-BK04-03:** Chạm một ngày thì gọi BK-01 với ràng buộc ngày đó và hiện các khung còn chỗ của xưởng đang chọn.
- **BR-BK04-04:** Nút "Thêm vào lịch" xuất sự kiện cho Google Calendar hoặc tệp `.ics`. Khi lịch hẹn đổi giờ hoặc bị huỷ, sự kiện đã thêm qua Google Calendar được cập nhật nếu có quyền ghi. Nếu không có quyền ghi thì gửi thông báo để chủ xe tự sửa.
- **BR-BK04-05:** Bản cho chủ xưởng: lịch tuần, mỗi ô ghi số chỗ còn lại, nhất quán với Workshop Board (us-037).

**Tình huống**

| ID | Tình huống | Xử lý | Kết quả |
| --- | --- | --- | --- |
| BK04-S01 | Chủ xe mở Trang chủ | Hiện tháng hiện tại với cửa sổ đến hạn và lịch hẹn | Thấy ngay nên đặt khoảng nào |
| BK04-S02 | Chạm ngày 24/10 | BK-01 với ràng buộc ngày 24/10 | Danh sách khung còn chỗ |
| BK04-S03 | Ngày đã chọn rơi vào ngày bận | Vẫn cho chọn, kèm cảnh báo nhẹ | "Lịch của bạn có sự kiện ngày này" |
| BK04-S04 | Đổi giờ lịch hẹn đã thêm vào Google Calendar | Cập nhật sự kiện | Lịch điện thoại đổi theo |
| BK04-S05 | Chưa đồng bộ lịch | Ẩn lớp "ngày bận", hiện lời mời đồng bộ có thể bỏ qua | — |

**Tiêu chí chấp nhận**

- AC-BK04-01: Số chỗ hiển thị trên widget khớp service sức chứa tại thời điểm tải.
- AC-BK04-02: Hệ thống không lưu tiêu đề hay nội dung sự kiện từ lịch của chủ xe.

---

#### BK-05 — Bản đồ xưởng (Google Maps)

| Giai đoạn | Loại | MoSCoW | Pain point | Nền tảng MVP |
| --- | --- | --- | --- | --- |
| P2-A | Chức năng | Should | PP2-01 | Toạ độ xưởng (`workshop.latitude/longitude`), API tìm xưởng gần (us-029) |

**Mô tả.** Bản đồ hiển thị vị trí chủ xe và các xưởng. Mỗi ghim ghi số chỗ trống, kèm bộ lọc, thời gian di chuyển và nút chỉ đường. Dùng chung với chat qua chip "Chọn trên bản đồ".

**Quy tắc nghiệp vụ**

- **BR-BK05-01:** Ghim xưởng ghi số chỗ còn trong ngày đang xem. Xưởng hết chỗ hiện màu xám nhưng vẫn bấm được để xem ngày khác.
- **BR-BK05-02:** Bộ lọc: còn chỗ, đang mở cửa, đánh giá tối thiểu, có phụ tùng (khi có BK-09).
- **BR-BK05-03:** Thời gian di chuyển dùng API tính tuyến đường theo giao thông. Kết quả được lưu đệm theo cặp (khu vực, xưởng) để giảm chi phí API (NFR-07).
- **BR-BK05-04:** Nút "Chỉ đường" mở Google Maps bên ngoài app; EV Care không tự dẫn đường.
- **BR-BK05-05:** Không có quyền vị trí thì đặt tâm bản đồ ở địa chỉ đã lưu, hoặc trung tâm thành phố.
- **BR-BK05-06:** Chọn xưởng trên bản đồ trả về đúng luồng BK-01 với ràng buộc "xưởng = xưởng đã chọn".

**Tình huống**

| ID | Tình huống | Xử lý | Kết quả |
| --- | --- | --- | --- |
| BK05-S01 | Mở bản đồ từ chip "Chọn trên bản đồ" | Hiện bản đồ quanh vị trí | Bấm ghim → thẻ xưởng → "Đặt ở đây" |
| BK05-S02 | Bật lọc "Còn chỗ hôm nay" | Ẩn xưởng hết chỗ | — |
| BK05-S03 | API bản đồ lỗi hoặc hết hạn mức | Chuyển sang dạng danh sách theo khoảng cách đường chim bay | "Bản đồ tạm thời không tải được" |
| BK05-S04 | Xưởng chưa có toạ độ | Không hiện trên bản đồ, vẫn có trong danh sách | — |

**Tiêu chí chấp nhận**

- AC-BK05-01: Khi API bản đồ lỗi, chủ xe vẫn đặt được lịch bằng danh sách.
- AC-BK05-02: Chi phí API trong tháng nằm trong ngân sách đã chốt (P2Q-07); có cảnh báo khi đạt 80%.

---

#### BK-06 — Lịch bảo dưỡng định kỳ tại xưởng quen

| Giai đoạn | Loại | MoSCoW | Pain point | Nền tảng MVP |
| --- | --- | --- | --- | --- |
| P2-B | Chức năng | Should | PP2-02 | BK-01, F3, F7 |

**Mô tả.** Chủ xe tạo một **chuỗi lịch định kỳ** tại một xưởng. Hệ thống không giữ chỗ cứng trước nhiều tháng. Trước mỗi mốc, hệ thống tự tạo một lịch hẹn qua BK-01 và chờ chủ xe xác nhận.

**Quy tắc nghiệp vụ**

- **BR-BK06-01:** Chu kỳ chuỗi theo mốc bảo dưỡng của hãng (km hoặc thời gian, cái nào đến trước). Chủ xe không tự đặt chu kỳ khác mốc hãng.
- **BR-BK06-02:** `SERIES_LEAD_DAYS` ngày trước ngày đến hạn dự kiến (đề xuất 14 — P2Q-03), hệ thống gọi BK-01 với ràng buộc của chuỗi, giữ chỗ và gửi chủ xe xác nhận.
- **BR-BK06-03:** Hai bước tách bạch. **Hệ thống kiểm tra hợp lệ** (còn chỗ, đúng mốc, xưởng hoạt động), rồi **xưởng chấp nhận** theo luật WS-01.
- **BR-BK06-04:** Chuỗi chỉ tạo lần kế tiếp khi xe không có lịch mở (BR-BK01-08).
- **BR-BK06-05:** Huỷ **một lần** khác với huỷ **cả chuỗi**. Huỷ một lần áp dụng BK-02 như lịch thường.

**Tình huống**

| ID | Tình huống | Xử lý | Kết quả |
| --- | --- | --- | --- |
| BK06-S01 | Đến T−14 ngày, xưởng quen còn chỗ | Giữ chỗ, gửi xác nhận | Một chạm xác nhận |
| BK06-S02 | Chủ xe bận lần này | "Bỏ qua lần này": huỷ lịch đó, chuỗi giữ nguyên | Lần sau vẫn tự tạo |
| BK06-S03 | Chủ xe muốn làm lần này ở xưởng khác | BK-01 S07 cho lần này; chuỗi gốc giữ nguyên | — |
| BK06-S04 | Chủ xe đổi giờ trước ngày hẹn | Đổi lịch theo us-053 | — |
| BK06-S05 | Xưởng quen kín vào thời điểm tạo | BK-01 S02/S03 | Phương án thay thế |
| BK06-S06 | Xưởng báo không phục vụ được | BK-01 S13; không tự chuyển xưởng khi chủ xe chưa đồng ý | — |
| BK06-S07 | Xưởng ngừng hoạt động | Tạm dừng chuỗi, mời chọn xưởng mới | Thông báo |
| BK06-S08 | Hãng báo xe đã bảo dưỡng ở nơi khác | Tính lại mốc, lùi lần kế tiếp, không nhắc thừa | — |
| BK06-S09 | Xe đổi chủ (hãng báo) | Kết thúc chuỗi, xoá ràng buộc của chủ cũ | — |
| BK06-S10 | Chủ xe không xác nhận lịch giữ sẵn | BK01-S09; chuỗi giữ nguyên, nhắc theo F7 | — |

**Tiêu chí chấp nhận**

- AC-BK06-01: Không có thời điểm nào chuỗi giữ quá một lịch mở cho một xe.
- AC-BK06-02: "Bỏ qua lần này" không làm dừng chuỗi; "Huỷ chuỗi" không huỷ lịch đã xác nhận nếu chủ xe không chọn huỷ kèm.

---

#### BK-07 — Danh sách chờ

| Giai đoạn | Loại | MoSCoW | Pain point | Nền tảng MVP |
| --- | --- | --- | --- | --- |
| P2-B | Chức năng | Could | PP2-10 | Service sức chứa |

**Quy tắc nghiệp vụ**

- **BR-BK07-01:** Khung hết chỗ thì chủ xe đăng ký chờ khung đó, hoặc một khoảng (ví dụ "bất kỳ khung sáng thứ Bảy").
- **BR-BK07-02:** Có chỗ trống thì mời người đầu danh sách. Người được mời có `WAITLIST_OFFER_MIN` (đề xuất 15) phút để nhận; quá hạn thì mời người kế tiếp.
- **BR-BK07-03:** Thứ tự danh sách là thời điểm đăng ký. Chủ xe ở bậc ≥ 3 của BK-02 xếp sau.
- **BR-BK07-04:** Chủ xe chỉ chờ tối đa `WAITLIST_MAX` (đề xuất 3) khung cùng lúc. Khi đã có lịch cho mốc đó thì tự rời mọi danh sách chờ.
- **BR-BK07-05:** Không mời nếu chỗ trống còn dưới 1 giờ nữa là đến giờ hẹn.

**Tình huống:** người đầu danh sách nhận chỗ; người đầu không phản hồi nên chuyển người kế tiếp; hai chỗ trống cùng lúc thì mời song song hai người; chủ xe đã đặt được chỗ khác nên tự rời danh sách.

**Tiêu chí chấp nhận**

- AC-BK07-01: Một chỗ trống không bao giờ được mời đồng thời cho hai người.
- AC-BK07-02: Lời mời hết hạn trả chỗ về cho người kế tiếp trong ≤ 1 phút.

---

#### BK-08 — Báo trễ chủ động hai chiều

| Giai đoạn | Loại | MoSCoW | Pain point | Nền tảng MVP |
| --- | --- | --- | --- | --- |
| P2-B | Chức năng | Could | PP2-07 | us-057 (tiến độ 6 bước), WS-02 (thời lượng) |

**Quy tắc nghiệp vụ**

- **BR-BK08-01 — Xưởng trễ.** Ước tính giờ bắt đầu thực tế từ tiến độ các xe trước và thời lượng chuẩn (WS-02). Lệch ≥ `DELAY_NOTIFY_MIN` (đề xuất 15 phút) thì báo chủ xe kèm hai lựa chọn: "Đến muộn hơn" hoặc "Đổi giờ".
- **BR-BK08-02 — Chủ xe trễ.** Chủ xe bấm "Tôi đến trễ" và chọn 10, 20 hoặc 30 phút. Xưởng thấy giờ đến mới. BK-02 không tính lỡ hẹn trong khoảng trễ đã báo.
- **BR-BK08-03:** Mỗi lịch báo trễ tối đa 2 lần mỗi phía, để tránh làm phiền.

**Tình huống:** xe trước làm lâu 25 phút nên báo khách sau; chủ xe kẹt xe báo trễ 20 phút; chủ xe báo trễ quá 30 phút thì gợi ý đổi giờ.

**Tiêu chí chấp nhận**

- AC-BK08-01: Chủ xe đã báo trễ trong giới hạn thì không bị ghi lỡ hẹn.

---

#### BK-09 — Chọn xưởng theo phụ tùng sẵn có

| Giai đoạn | Loại | MoSCoW | Pain point | Nền tảng MVP |
| --- | --- | --- | --- | --- |
| P2-C | Chức năng | Could | PP2-07 | F5 (hạng mục theo mốc) |

**Quy tắc nghiệp vụ**

- **BR-BK09-01:** Phụ tùng cần dùng xác định từ hạng mục của mốc, và từ chẩn đoán sơ bộ của AD-02 khi chủ xe kể triệu chứng.
- **BR-BK09-02:** Xưởng khai báo tồn kho theo mã phụ tùng, nhập tay hoặc đồng bộ phần mềm kho (P2Q-08). Mỗi xưởng hiển thị một trạng thái: **Có sẵn**, **Về trong N ngày**, **Chưa rõ**.
- **BR-BK09-03:** Phụ tùng trở thành một ràng buộc mềm trong BK-01. Chỉ thành ràng buộc cứng nếu chủ xe chọn "Chỉ xưởng có sẵn".
- **BR-BK09-04:** Không xưởng nào có sẵn thì cho đặt lịch kèm "đặt trước phụ tùng". Giờ hẹn sớm nhất là sau ngày hàng về.
- **BR-BK09-05:** Khi nhận lịch, xưởng xác nhận lại phụ tùng và giữ phụ tùng cho lịch đó. Hết hàng sau khi đã nhận lịch thì đi theo BK-01 S13.

**Tiêu chí chấp nhận**

- AC-BK09-01: Trạng thái phụ tùng hiển thị kèm thời điểm cập nhật; quá `STOCK_STALE_DAYS` ngày thì chuyển "Chưa rõ".

---

#### BK-10 — Tối ưu hoá lập lịch (phi chức năng)

| Giai đoạn | Loại | MoSCoW | Pain point | Nền tảng MVP |
| --- | --- | --- | --- | --- |
| P2-C | **Phi chức năng** | Could | PP2-07, PP2-11 | BK-01 (lời giải theo luật làm mốc so sánh), WS-02, us-057 |

**Mô tả.** Trong các lịch hợp lệ BK-01 tìm được, chọn lịch tốt nhất cho cả chủ xe và xưởng theo năm mục tiêu thời gian. Đây là chất lượng của lời giải, không phải chức năng mới, nên không chặn P2-A. Mô hình chi tiết ở **mục 8**.

**Quy tắc nghiệp vụ**

- **BR-BK10-01:** Bộ tối ưu chỉ thay phần **xếp hạng và gán** của BK-01. Mọi ràng buộc cứng và quy tắc giữ chỗ của BK-01 giữ nguyên.
- **BR-BK10-02:** Lịch đã `confirmed` chỉ được dời khi chủ xe đồng ý. Bộ tối ưu chỉ được tự do sắp xếp các lịch đang giữ chỗ, và gán khoang, KTV trong nội bộ xưởng.
- **BR-BK10-03:** Trọng số mục tiêu có giá trị mặc định toàn hệ thống. Từng xưởng có thể chỉnh trong giới hạn cho phép (P2Q-10).
- **BR-BK10-04:** Bật bộ tối ưu theo từng xưởng, có thể so sánh A/B với lời giải theo luật bằng chỉ số M-09, M-10 (mục 12).

**Tiêu chí chấp nhận**

- AC-BK10-01: Lời giải của bộ tối ưu không vi phạm ràng buộc cứng nào.
- AC-BK10-02: Trên dữ liệu thử nghiệm, tổng hàm mục tiêu tốt hơn lời giải theo luật ít nhất `OPT_MIN_GAIN` (đề xuất 10%). Không đạt thì không bật.
- AC-BK10-03: Thời gian giải theo lô cho một xưởng một ngày ≤ 30 giây; giải theo sự kiện ≤ 3 giây (NFR-04).

---

### 7.2 Nhóm HS — Hồ sơ và lịch sử xe

#### HS-01 — Tra cứu lịch sử bảo dưỡng phía chủ xe

| Giai đoạn | Loại | MoSCoW | Pain point | Nền tảng MVP |
| --- | --- | --- | --- | --- |
| P2-A | Chức năng | Must | PP2-03 | Đồng bộ lịch sử dịch vụ từ hãng (`ServiceHistory`), booking `completed`, quote đã duyệt |

**Mô tả.** Màn **Lịch sử xe** hiển thị dòng thời gian mọi lần bảo dưỡng và sửa chữa. Mỗi lần gồm: ngày, ODO, xưởng, hạng mục, phụ tùng đã thay, chi phí, báo giá đã duyệt và ảnh (khi có). Agent trả lời được câu hỏi về lịch sử.

**Quy tắc nghiệp vụ**

- **BR-HS01-01:** Hai nguồn dữ liệu, ghi rõ nguồn trên từng mục:
  - Lịch sử hãng đồng bộ, gồm cả lần làm ngoài EV Care.
  - Lịch hẹn `completed` trong EV Care.
  
  Nếu một lần làm có ở cả hai nguồn thì gộp thành một mục, ưu tiên dữ liệu hãng.
- **BR-HS01-02:** Lọc theo nhóm hạng mục (pin, phanh, lốp, điều hoà, phần mềm…) và theo năm.
- **BR-HS01-03:** Chi phí hiển thị theo nguồn: báo giá đã duyệt hoặc dữ liệu hãng. Nếu chỉ có dự toán thì gắn nhãn "ước tính".
- **BR-HS01-04:** Agent có tool tra lịch sử, ví dụ "Lần trước thay lốp khi nào?". Câu trả lời dẫn về mục cụ thể trong dòng thời gian.
- **BR-HS01-05 — Chia sẻ khi bán xe:** chủ xe tạo link chỉ đọc có hạn `SHARE_LINK_DAYS` (đề xuất 7 ngày), thu hồi được. Link không chứa VIN đầy đủ, SĐT, email; biển số che một phần.
- **BR-HS01-06:** Xe đổi chủ thì chủ mới chỉ thấy lịch sử hãng cung cấp. Ghi chú riêng và ảnh của chủ cũ không chuyển sang.

**Tình huống**

| ID | Tình huống | Xử lý | Kết quả |
| --- | --- | --- | --- |
| HS01-S01 | Mở Lịch sử xe | Tải dòng thời gian, mới nhất trước | Danh sách theo năm |
| HS01-S02 | Hỏi chat "Lần trước thay lốp khi nào?" | Tool tra lịch sử, lọc theo nhóm lốp | Câu trả lời kèm link tới mục |
| HS01-S03 | Hãng chưa đồng bộ lần làm ngoài EV Care | Hiện thời điểm đồng bộ gần nhất | "Dữ liệu hãng cập nhật lúc …" |
| HS01-S04 | Tạo link chia sẻ | Sinh link có hạn | Nút sao chép, nút thu hồi |
| HS01-S05 | Link đã hết hạn hoặc bị thu hồi | Trả trang báo hết hiệu lực | — |
| HS01-S06 | Xe mới, chưa có lịch sử | Trạng thái rỗng, giải thích nguồn dữ liệu | Gợi ý đặt mốc đầu |

**Tiêu chí chấp nhận**

- AC-HS01-01: Một lần bảo dưỡng có ở cả hai nguồn chỉ hiện một mục.
- AC-HS01-02: Link chia sẻ không lộ VIN đầy đủ, SĐT, email.
- AC-HS01-03: Tải 50 mục gần nhất ≤ 500 ms (p90).

---

#### HS-02 — Gộp việc vào một lần đến xưởng

| Giai đoạn | Loại | MoSCoW | Pain point | Nền tảng MVP |
| --- | --- | --- | --- | --- |
| P2-B | Chức năng | Could | PP2-02, PP2-07 | F3, BK-01 |

**Quy tắc nghiệp vụ**

- **BR-HS02-01:** Khi hãng có chiến dịch triệu hồi hoặc cập nhật phần mềm áp cho xe (P2Q-06), BK-01 gợi ý gộp vào lần bảo dưỡng gần nhất nếu mốc đó trong vòng `MERGE_WINDOW_DAYS` (đề xuất 60 ngày).
- **BR-HS02-02:** Hạng mục sắp đến hạn trong cửa sổ đó được gợi ý làm luôn. Đây chỉ là gợi ý, chủ xe chọn.
- **BR-HS02-03:** Thời lượng lịch hẹn cộng thêm theo hạng mục gộp (WS-02).
- **BR-HS02-04:** Gộp lịch cho nhiều xe trong một gia đình chỉ áp dụng khi phạm vi "nhiều xe trên một tài khoản" được mở (4.2).

**Tiêu chí chấp nhận**

- AC-HS02-01: Không tự thêm hạng mục tính phí vào lịch hẹn khi chủ xe chưa đồng ý.

---

### 7.3 Nhóm PS — Cá nhân hoá

#### PS-01 — Bộ nhớ ngắn hạn và dài hạn của agent

| Giai đoạn | Loại | MoSCoW | Pain point | Nền tảng MVP |
| --- | --- | --- | --- | --- |
| P2-A | Cải tiến MVP | Should | PP2-02, PP2-08 | LangGraph checkpoint (bộ nhớ hội thoại), AI-004 (xưởng ưa thích) |

| | Bộ nhớ ngắn hạn | Bộ nhớ dài hạn |
| --- | --- | --- |
| Phạm vi | Một hội thoại | Theo tài khoản, qua nhiều hội thoại |
| Nội dung | Xe đang nhắc tới, thông tin đặt lịch đang hỏi dở, ý định hiện tại | Xưởng hay đến, giờ hay chọn, cách xưng hô, vấn đề xe từng gặp, phản hồi dịch vụ, thói quen huỷ |
| Lưu ở | Checkpoint hiện có | Bảng bộ nhớ riêng (mục 11) |
| Hết hạn | Theo hội thoại | `MEMORY_TTL_DAYS` (đề xuất 365), làm mới khi được dùng lại |

**Quy tắc nghiệp vụ**

- **BR-PS01-01:** Chỉ lưu những loại thông tin trong danh mục cho phép ở bảng trên. Không lưu CCCD, VIN đầy đủ, nội dung sức khoẻ, tài chính cá nhân, hay suy đoán về tính cách.
- **BR-PS01-02:** Mỗi mục nhớ có nguồn: chủ xe nói, suy ra từ hành vi, hoặc từ phản hồi. Mục suy ra chỉ được dùng sau khi lặp lại ≥ 2 lần.
- **BR-PS01-03:** Thông tin cũ và mới mâu thuẫn nhau thì dùng thông tin mới, lưu lịch sử.
- **BR-PS01-04:** Agent nói rõ khi dùng bộ nhớ, ví dụ "Lần trước bạn đặt sáng thứ Bảy ở Xưởng Cầu Giấy, đặt như vậy nhé?".
- **BR-PS01-05:** Có màn **"Agent đang nhớ gì về tôi"**: xem, sửa, xoá từng mục, hoặc xoá hết. Tắt bộ nhớ dài hạn thì agent hoạt động như MVP.
- **BR-PS01-06:** Bộ nhớ dài hạn chỉ hoạt động khi chủ xe đã đồng ý (PL-01).

**Tình huống:** dùng lại xưởng và giờ quen; chủ xe nói "lần này tôi muốn buổi chiều" thì cập nhật ưu tiên mới; chủ xe xoá một mục nhớ thì agent không nhắc lại; chủ xe tắt bộ nhớ thì agent hỏi lại như người mới.

**Tiêu chí chấp nhận**

- AC-PS01-01: Mục đã xoá không xuất hiện trong bất kỳ câu trả lời nào sau đó (eval).
- AC-PS01-02: Không có mục nhớ nào thuộc danh mục cấm (kiểm tra tự động trên mẫu dữ liệu).

---

#### PS-02 — Cá nhân hoá theo phản hồi dịch vụ

| Giai đoạn | Loại | MoSCoW | Pain point | Nền tảng MVP |
| --- | --- | --- | --- | --- |
| P2-B | Chức năng | Should | PP2-08 | F9: `follow_up.rating` 1–5, `has_issue` |

**Quy tắc nghiệp vụ**

- **BR-PS02-01:** Ngoài điểm 1–5, thêm tag đánh giá nhanh: đúng giờ, giá đúng báo giá, chất lượng, thái độ, sạch sẽ. Có thể chọn nhiều tag.
- **BR-PS02-02 — Cho từng chủ xe:**
  - Điểm ≤ 2 ở một xưởng thì xưởng đó không được BK-01 đề xuất cho chủ xe này nữa, trừ khi chủ xe chọn lại.
  - Điểm ≥ 4 thì được cộng vào điểm khớp.
- **BR-PS02-03 — Cho toàn hệ thống:**
  - Điểm trung bình 90 ngày của xưởng là một yếu tố xếp hạng, chỉ tính khi có ≥ `MIN_REVIEWS` (đề xuất 5) đánh giá.
  - Gửi tổng hợp tag cho chủ xưởng hằng tuần.
- **BR-PS02-04:** Chỉ lịch hẹn `completed` mới được đánh giá, mỗi lịch một lần (giữ BR-006).

**Tiêu chí chấp nhận**

- AC-PS02-01: Sau khi chấm 1 sao một xưởng, lần đặt sau của chủ xe đó không có xưởng này trong danh sách đề xuất.

---

#### PS-03 — Giải thích và phản hồi gợi ý

| Giai đoạn | Loại | MoSCoW | Pain point | Nền tảng MVP |
| --- | --- | --- | --- | --- |
| P2-B | Cải tiến MVP | Should | PP2-08 | us-061 BR-1503 (lý do đề xuất) |

**Quy tắc nghiệp vụ**

- **BR-PS03-01:** Mọi đề xuất tự động (xưởng, giờ, hạng mục gộp) kèm tối đa 3 lý do có thật, lấy từ dữ liệu đã dùng để xếp hạng. Không viết lý do bằng LLM tự do.
- **BR-PS03-02:** Chủ xe bấm "Không phù hợp" và chọn lý do: xa, giờ không tiện, không thích xưởng này, giá cao. Lý do được ghi vào bộ nhớ (PS-01) và dùng cho lần sau.

**Tiêu chí chấp nhận**

- AC-PS03-01: Mọi lý do hiển thị đều truy được về một yếu tố trong điểm xếp hạng.

---

#### PS-04 — Gợi ý từ chủ xe có đặc điểm tương đồng

| Giai đoạn | Loại | MoSCoW | Pain point | Nền tảng MVP |
| --- | --- | --- | --- | --- |
| P2-C | Chức năng | Could | PP2-08 | — |

**Quy tắc nghiệp vụ**

- **BR-PS04-01:** "Tương đồng" gồm: cùng dòng xe, cùng khu vực, số km mỗi tháng cùng khoảng, cùng kiểu sử dụng (cá nhân hay chạy dịch vụ).
- **BR-PS04-02:** Giai đoạn đầu dùng phân nhóm theo luật. Chỉ dùng học máy khi mỗi nhóm có ≥ `MIN_COHORT` (đề xuất 30) chủ xe.
- **BR-PS04-03:** Chỉ dùng dữ liệu tổng hợp, ẩn danh. Không bao giờ hiện thông tin của một chủ xe cụ thể cho người khác.
- **BR-PS04-04:** Ứng dụng: gợi ý xưởng cho người mới chưa có lịch sử, gợi ý hạng mục nên làm thêm. Luôn kèm lý do, ví dụ "nhiều chủ VF 8 trong khu vực chọn…".

**Tiêu chí chấp nhận**

- AC-PS04-01: Không gợi ý nào dựa trên nhóm có số chủ xe dưới ngưỡng.

---

#### PS-05 — Agent trả lời theo phong cách giao tiếp

| Giai đoạn | Loại | MoSCoW | Pain point | Nền tảng MVP |
| --- | --- | --- | --- | --- |
| P2-C | Chức năng | Could | PP2-08 | PS-01 |

**Quy tắc nghiệp vụ**

- **BR-PS05-01:** Nhận diện **phong cách**, không suy diễn tính cách. Các chiều: ngắn hay chi tiết, rành kỹ thuật hay không, quan tâm giá, mức độ gấp, cách xưng hô.
- **BR-PS05-02:** Phong cách chỉ đổi **cách nói**: độ dài, thuật ngữ, thứ tự thông tin. Không đổi nội dung về an toàn, giá, bảo hành và không bỏ trích nguồn.
- **BR-PS05-03:** Chủ xe chọn phong cách thủ công trong Cài đặt; lựa chọn thủ công luôn được ưu tiên.
- **BR-PS05-04:** Phát hiện khách đang bực hoặc mất kiên nhẫn thì đề nghị chuyển người thật (PL-02).

**Tiêu chí chấp nhận**

- AC-PS05-01: Cùng một câu hỏi, câu trả lời ở mọi phong cách có cùng con số và cùng nguồn trích dẫn (eval).

---

### 7.4 Nhóm CH — Trải nghiệm chat

#### CH-01 — Gợi ý một chạm

| Giai đoạn | Loại | MoSCoW | Pain point | Nền tảng MVP |
| --- | --- | --- | --- | --- |
| P2-A | Chức năng | Must | PP2-01, PP2-05 | Chat F4, đề xuất nhanh us-061 |

**Mô tả.** Các nút gợi ý (chip) bên dưới khung chat. Chủ xe đi hết một luồng, ví dụ đặt lịch, chỉ bằng chạm.

**Ba nguồn gợi ý**

| Nguồn | Khi nào hiện | Ví dụ |
| --- | --- | --- |
| Mở đầu | Mở chat mới | "Tôi muốn đặt lịch bảo dưỡng", "Xe tôi khi nào đến hạn?", "Mốc tới hết bao nhiêu?", "Xem lịch sử bảo dưỡng" |
| Theo ngữ cảnh | Sau mỗi câu trả lời | Sau dự toán: "Đặt lịch luôn", "So sánh xưởng"; sau khi hỏi "ở đâu": "Gần vị trí hiện tại", "Gần nơi làm việc", "Xưởng quen", "Chọn trên bản đồ" |
| Theo trạng thái | Theo trạng thái xe và lịch | Xe `DUE_SOON`: "Đặt lịch mốc 24.000 km"; có hẹn ngày mai: "Đổi giờ", "Chỉ đường", "Tôi đến trễ" |

**Luồng đặt lịch một chạm** (chuẩn cho mọi màn và chat):

```
[Tôi muốn đặt lịch bảo dưỡng]
 → Ở đâu?          [Gần vị trí hiện tại] [Gần nơi làm việc] [Xưởng quen] [Chọn trên bản đồ]
 → Xưởng nào?      thẻ 3 xưởng có lý do (bỏ qua nếu chọn Xưởng quen)
 → Khi nào rảnh?   [Sáng thứ Bảy này] [Chiều mai] [Cuối tuần sau] [Mở lịch chọn ngày]
 → Giờ nào?        [08:00] [09:30] [10:30 · còn 1 chỗ]
                   (xưởng kín → phương án thay thế theo BK-01)
 → Xác nhận        thẻ tóm tắt: xe, hạng mục, xưởng, giờ, dự toán
 → Hoàn tất        vé lịch hẹn + [Thêm vào lịch] [Chỉ đường]
```

**Quy tắc nghiệp vụ**

- **BR-CH01-01:** Mỗi lần hiện 3–5 gợi ý. Gợi ý quan trọng nhất (bước tiếp theo hợp lý) được tô đậm.
- **BR-CH01-02:** Mỗi gợi ý gắn với **một ý định agent đã xử lý được** (intent và tham số). Bấm gợi ý gửi đúng ý định đó, không đi qua bước hiểu ngôn ngữ tự do. Như vậy luôn ra kết quả xác định.
- **BR-CH01-03:** Chủ xe vẫn gõ tự do bất cứ lúc nào. Gợi ý không khoá luồng; gõ tự do thì agent hiểu như MVP.
- **BR-CH01-04:** Gợi ý mở đầu lấy từ thống kê các ý định phổ biến nhất trong 30 ngày, cập nhật hằng tuần. Có danh sách mặc định khi chưa đủ dữ liệu.
- **BR-CH01-05:** Nút có tác dụng phụ (xác nhận đặt, huỷ, đồng ý báo giá) vẫn tuân nguyên tắc "Confirm before side effect": đi kèm thẻ tóm tắt và `confirmation_token`.
- **BR-CH01-06:** Ghi sự kiện hiển thị và bấm của từng gợi ý cho chỉ số M-04.

**Tình huống**

| ID | Tình huống | Xử lý | Kết quả |
| --- | --- | --- | --- |
| CH01-S01 | Đặt lịch chỉ bằng chạm | Luồng trên | Vé lịch hẹn, 0 ký tự phải gõ |
| CH01-S02 | Đang giữa luồng thì gõ "thôi để chiều" | Hiểu ý định, cập nhật ràng buộc giờ, tiếp tục luồng | Gợi ý giờ buổi chiều |
| CH01-S03 | Chọn "Xưởng quen" và giờ đã kín | BK-01 S02/S03 | Phương án thay thế dưới dạng gợi ý |
| CH01-S04 | Bấm lại gợi ý cũ phía trên lịch sử chat | Gợi ý cũ bị vô hiệu sau khi luồng đã sang bước khác | "Gợi ý này đã hết hiệu lực" |
| CH01-S05 | Bấm "Xác nhận" hai lần do mạng chậm | Chống trùng bằng `confirmation_token` (us-061 EF-1507) | Một lịch duy nhất |

**Tiêu chí chấp nhận**

- AC-CH01-01: Luồng đặt lịch chuẩn hoàn tất được mà không cần gõ ký tự nào.
- AC-CH01-02: Mỗi gợi ý trên giao diện đều có ý định tương ứng được backend xử lý (kiểm tra tự động danh mục gợi ý).
- AC-CH01-03: Gợi ý của bước cũ không tạo tác dụng phụ khi bấm lại.

---

#### CH-02 — Thẻ tương tác trong chat

| Giai đoạn | Loại | MoSCoW | Pain point | Nền tảng MVP |
| --- | --- | --- | --- | --- |
| P2-A | Cải tiến MVP | Should | PP2-05 | Thẻ tóm tắt đặt lịch (F6), vé lịch hẹn (F6b) |

**Quy tắc nghiệp vụ**

- **BR-CH02-01 — Danh mục thẻ:** thẻ xưởng (khoảng cách, đánh giá, phụ tùng, số chỗ); thẻ khung giờ; thẻ tóm tắt lịch hẹn; vé lịch hẹn; thẻ dự toán; thẻ báo giá phát sinh (AD-04); thẻ mục lịch sử (HS-01).
- **BR-CH02-02:** Dữ liệu trên thẻ lấy từ kết quả tool. LLM không tự viết con số trên thẻ.
- **BR-CH02-03:** Mọi thẻ có nút hành động. Thẻ hết hiệu lực (giữ chỗ hết hạn, báo giá hết hạn) hiển thị trạng thái mới khi mở lại hội thoại.

**Tiêu chí chấp nhận**

- AC-CH02-01: Con số trên thẻ trùng khớp với kết quả tool đã lưu trong `chat_message`.

---

### 7.5 Nhóm AD — Agent tư vấn thay xưởng

**Mục tiêu chung của nhóm:** chủ xe tự có câu trả lời về giá, bảo hành, phụ tùng mà không cần gọi xưởng. Xưởng chỉ nhập dữ liệu một lần: bảng giá, tồn kho, gói dịch vụ. Toàn nhóm tuân thủ các nguyên tắc AI ở mục 9.

#### AD-01 — Giá bảo dưỡng theo mốc, tách phần bảo hành

| Giai đoạn | Loại | MoSCoW | Pain point | Nền tảng MVP |
| --- | --- | --- | --- | --- |
| P2-A | Cải tiến MVP | Should | PP2-06 | F5 (dự toán, tách trong bảo hành / tính phí), AI-003 |

**Quy tắc nghiệp vụ**

- **BR-AD01-01:** So sánh dự toán cùng mốc giữa tối đa 3 xưởng thoả ràng buộc của chủ xe (BK-01).
- **BR-AD01-02:** Mỗi dự toán ghi ngày cập nhật bảng giá của xưởng. Giá cũ hơn `PRICE_STALE_DAYS` (đề xuất 90) thì kèm cảnh báo.
- **BR-AD01-03:** Giữ nguyên quy tắc F5: LLM không tự tính, mọi số gắn nhãn "ước tính".

**Tiêu chí chấp nhận**

- AC-AD01-01: Tổng dự toán từng xưởng khớp tool (giữ AC-F5-01).

---

#### AD-02 — Tư vấn phụ tùng và báo giá sửa chữa

| Giai đoạn | Loại | MoSCoW | Pain point | Nền tảng MVP |
| --- | --- | --- | --- | --- |
| P2-B | Chức năng | Should | PP2-06, PP2-09 | F4 (RAG), F5 (tool giá), F5b (báo giá HITL) |

**Mô tả.** Chủ xe kể triệu chứng hoặc hỏi thẳng tên phụ tùng. Agent xác định hạng mục sửa chữa có thể liên quan theo tài liệu hãng, đưa khoảng giá phụ tùng + tiền công theo bảng giá xưởng, cho biết xưởng nào có sẵn, và đặt lịch được ngay.

**Quy tắc nghiệp vụ**

- **BR-AD02-01:** Agent chỉ nêu **hạng mục có thể liên quan**, kèm nguồn tài liệu. Agent không chẩn đoán chắc chắn. Mọi tư vấn sửa chữa có câu "cần kỹ thuật viên kiểm tra để xác nhận".
- **BR-AD02-02:** Giá sửa chữa lấy từ **bảng giá sửa chữa** do xưởng nhập: mã phụ tùng, giá phụ tùng, tiền công, thời lượng. Đây là dữ liệu mới, mục 11. Thiếu giá thì nói rõ chưa có giá và mời xưởng báo giá qua F5b.
- **BR-AD02-03:** Luôn trình bày dạng **khoảng giá** kèm ngày cập nhật. Giá chính thức chỉ có khi xưởng duyệt báo giá (F5b) hoặc khi nhận xe.
- **BR-AD02-04:** Triệu chứng có dấu hiệu an toàn (phanh mất tác dụng, cảnh báo pin cao áp, khói, mùi khét) thì khuyên dừng xe và đưa hotline xưởng trước, theo cách F9 đang làm. Không báo giá trước lời khuyên an toàn.
- **BR-AD02-05:** Triệu chứng chủ xe kể được lưu vào lịch hẹn nếu chủ xe đặt lịch, để KTV xem (TA-01).

**Tình huống**

| ID | Tình huống | Xử lý | Kết quả |
| --- | --- | --- | --- |
| AD02-S01 | "Phanh trước kêu khi dừng, thay má phanh hết bao nhiêu?" | RAG: hạng mục má phanh; tool giá 3 xưởng | Khoảng giá, xưởng có sẵn, chip "Đặt lịch thay" |
| AD02-S02 | Xưởng chưa nhập giá phụ tùng này | Nói rõ chưa có giá | Chip "Xin xưởng báo giá" (F5b) |
| AD02-S03 | "Xe có mùi khét khi sạc" | Lời khuyên an toàn trước, không báo giá | Hướng dẫn dừng sạc, hotline xưởng, chip "Đặt lịch kiểm tra sớm nhất" |
| AD02-S04 | Hỏi phụ tùng không chính hãng | Không tư vấn mua ngoài; nêu điều khoản bảo hành nếu tài liệu có | Trích nguồn |
| AD02-S05 | Triệu chứng mơ hồ ("xe hơi lạ") | Hỏi thêm bằng gợi ý: tiếng kêu, rung, đèn cảnh báo | Thu hẹp hạng mục |

**Tiêu chí chấp nhận**

- AC-AD02-01: 100% câu trả lời có triệu chứng an toàn đưa lời khuyên an toàn trước giá (bộ eval ≥ 20 câu).
- AC-AD02-02: Không câu trả lời nào nêu một con số giá duy nhất như giá cuối cùng.

---

#### AD-03 — Tư vấn bảo hành và gói bảo hành

| Giai đoạn | Loại | MoSCoW | Pain point | Nền tảng MVP |
| --- | --- | --- | --- | --- |
| P2-B | Chức năng | Should | PP2-06, PP2-09 | F4 (RAG `warranty_policy`), F1 (hãng trả thông tin bảo hành khi xác thực xe) |

**Quy tắc nghiệp vụ**

- **BR-AD03-01:** Thời hạn bảo hành theo hạng mục lấy từ **dữ liệu hãng theo VIN**. Agent không tự tính thời hạn từ tài liệu chung nếu đã có dữ liệu theo xe. Nguồn dữ liệu là P2Q-05.
- **BR-AD03-02:** Điều kiện bảo hành, những việc làm mất bảo hành, quy trình yêu cầu bảo hành: chỉ trả lời từ tài liệu `warranty_policy`, có trích nguồn (no-source-no-claim).
- **BR-AD03-03:** Gói bảo hành mở rộng hoặc gói bảo dưỡng: chỉ giới thiệu gói có trong tài liệu hoặc danh mục của hãng/xưởng. Phần "có đáng mua không" chỉ là phép tính so sánh minh bạch theo số km thực tế của xe, không phải khuyến nghị bán hàng.
- **BR-AD03-04:** Tranh chấp bảo hành ("xưởng từ chối bảo hành của tôi") thì chuyển người thật (PL-02) kèm tóm tắt. Agent không phán xử.

**Tình huống:** hỏi pin còn bảo hành không; hỏi điều gì làm mất bảo hành; hỏi gói mở rộng có lợi không; hãng chưa có dữ liệu bảo hành theo VIN thì trả lời theo tài liệu chung và ghi rõ; khiếu nại bị từ chối bảo hành thì chuyển người.

**Tiêu chí chấp nhận**

- AC-AD03-01: Câu trả lời về thời hạn bảo hành của xe cụ thể khớp dữ liệu hãng (test với dữ liệu mock).
- AC-AD03-02: 100% câu khẳng định điều kiện bảo hành có trích nguồn.

---

#### AD-04 — Báo giá phát sinh khi thay phụ tùng

| Giai đoạn | Loại | MoSCoW | Pain point | Nền tảng MVP |
| --- | --- | --- | --- | --- |
| P2-B | Chức năng | Should | PP2-06, PP2-13 | F5b (báo giá HITL), us-057 (tiến độ) |

**Mô tả.** Khi xe đang làm mà phát hiện cần thay thêm, KTV ghi nhận bằng ảnh và chọn phụ tùng. Agent soạn báo giá phát sinh dễ hiểu, chủ xưởng duyệt, chủ xe đồng ý trên app. Mọi bước có lưu vết.

**Quy tắc nghiệp vụ**

- **BR-AD04-01:** Báo giá phát sinh là một `quote` gắn với lịch hẹn đang `in_progress`, loại "phát sinh". Nó tái dùng luồng duyệt của F5b, không tạo luồng duyệt mới.
- **BR-AD04-02:** KTV tạo nháp: ảnh (bắt buộc ít nhất 1), phụ tùng, lý do ngắn. Agent viết lời giải thích cho chủ xe từ lý do của KTV và tài liệu hãng.
- **BR-AD04-03:** Chủ xưởng duyệt hoặc sửa trước khi gửi chủ xe. Xưởng có thể đặt luật tự duyệt dưới `AUTO_APPROVE_EXTRA_VND`.
- **BR-AD04-04:** Tổng chi phí tăng quá `EXTRA_CONSENT_PCT` (đề xuất 10%) so với báo giá hoặc dự toán ban đầu thì **bắt buộc chủ xe đồng ý** mới được làm. Dưới ngưỡng thì vẫn thông báo.
- **BR-AD04-05:** Chủ xe có 3 lựa chọn: "Đồng ý thay", "Không thay lần này", "Gọi cho xưởng". Không phản hồi trong `EXTRA_TIMEOUT_MIN` (đề xuất 30) thì xưởng gọi điện. Trạng thái hiển thị "chờ khách".
- **BR-AD04-06:** "Không thay lần này" được ghi vào lịch sử xe (HS-01) như một khuyến nghị chưa làm, để nhắc ở lần sau.

**Tình huống**

| ID | Tình huống | Xử lý | Kết quả |
| --- | --- | --- | --- |
| AD04-S01 | KTV phát hiện lốp phồng, chủ xe đồng ý | Nháp → xưởng duyệt → chủ xe đồng ý → tiến độ cập nhật | Tổng mới trên vé, có lưu vết |
| AD04-S02 | Chủ xe từ chối | Ghi khuyến nghị chưa làm | Nhắc ở lần bảo dưỡng sau |
| AD04-S03 | Chủ xe không phản hồi 30 phút | Báo xưởng gọi điện | Xưởng thấy nhãn "chờ khách" |
| AD04-S04 | Phát sinh nhỏ dưới ngưỡng tự duyệt và dưới ngưỡng bắt buộc đồng ý | Tự duyệt, thông báo cho chủ xe | Chủ xe vẫn thấy ảnh và giá |
| AD04-S05 | Phát sinh liên quan an toàn | Ghi rõ mức khẩn cấp; khuyến nghị không lái xe nếu không thay | — |

**Tiêu chí chấp nhận**

- AC-AD04-01: Không phát sinh nào vượt ngưỡng chuyển sang "đã làm" khi chưa có đồng ý của chủ xe.
- AC-AD04-02: Mọi báo giá phát sinh có ít nhất một ảnh và người duyệt.

---

### 7.6 Nhóm WS — Tự động hoá phía xưởng

#### WS-01 — Tự nhận lịch hẹn có điều kiện

| Giai đoạn | Loại | MoSCoW | Pain point | Nền tảng MVP |
| --- | --- | --- | --- | --- |
| P2-A | Cải tiến MVP | Must | PP2-09 | `booking_confirmation_mode` `auto`/`manual`, khoá chỗ, Workshop Board (us-037) |

**Mô tả.** Thay công tắc tự động / thủ công bằng **bộ luật** do chủ xưởng đặt một lần. Lịch thoả luật thì tự nhận; lịch rơi vào ngoại lệ mới cần chủ xưởng duyệt.

**Quy tắc nghiệp vụ**

- **BR-WS01-01 — Luật có sẵn để bật hoặc tắt:**

| Luật | Ý nghĩa | Mặc định |
| --- | --- | --- |
| Còn chỗ | Còn ≥ N chỗ trống trong ngày thì tự nhận | N = 1 |
| Khách tin cậy thấp | Chủ xe ở bậc ≥ 3 của BK-02 thì duyệt tay | Bật |
| Phụ tùng đặc biệt | Hạng mục có phụ tùng "Chưa rõ" hoặc "Về trong N ngày" thì duyệt tay | Bật khi có BK-09 |
| Khung giờ chỉ duyệt tay | Xưởng chọn khung cụ thể | Không |
| Có báo giá kèm | Lịch kèm báo giá phát sinh lớn thì duyệt tay | Tắt |

- **BR-WS01-02:** Luật đánh giá theo thứ tự. Chỉ cần một luật yêu cầu duyệt tay thì lịch chuyển duyệt tay, kèm **lý do** hiện trên Workshop Board.
- **BR-WS01-03:** Không bật luật nào thì giữ hành vi của chế độ `auto` hoặc `manual` như MVP, để tương thích ngược.
- **BR-WS01-04:** Thay đổi luật chỉ áp dụng cho lịch mới; lịch đang chờ giữ nguyên trạng thái.

**Tình huống**

| ID | Tình huống | Xử lý | Kết quả |
| --- | --- | --- | --- |
| WS01-S01 | Lịch thường, còn chỗ | Tự nhận | Chủ xe nhận vé ngay |
| WS01-S02 | Chủ xe bậc 3 đặt lịch | Duyệt tay, lý do "khách lỡ hẹn 3 lần / 90 ngày" | Chủ xưởng thấy nhãn |
| WS01-S03 | Khung giờ chủ xưởng đặt là chỉ duyệt tay | Duyệt tay | — |
| WS01-S04 | Chủ xưởng tắt hết luật | Hành vi như MVP | — |

**Tiêu chí chấp nhận**

- AC-WS01-01: Mỗi lịch chuyển duyệt tay đều có ít nhất một lý do hiển thị.
- AC-WS01-02: Tỉ lệ lịch phải duyệt tay được đo (M-06).

---

#### WS-02 — Sức chứa theo thời lượng và hạn phản hồi

| Giai đoạn | Loại | MoSCoW | Pain point | Nền tảng MVP |
| --- | --- | --- | --- | --- |
| P2-A | Cải tiến MVP | Should | PP2-07, PP2-11 | Sức chứa theo đầu thợ (PQ-03); xưởng `manual` quá 12 giờ thì tự huỷ (us-029 BR-015) |

**Quy tắc nghiệp vụ**

- **BR-WS02-01:** Mỗi hạng mục có **thời lượng chuẩn** (phút). Giá trị mặc định lấy từ tài liệu hãng, xưởng chỉnh được. Lịch hẹn chiếm thời lượng bằng tổng các hạng mục, làm tròn lên theo đơn vị khung (`SLOT_UNIT_MIN`, đề xuất 30 phút).
- **BR-WS02-02:** Một lịch có thể chiếm nhiều khung liên tiếp của cùng một thợ hoặc khoang. Kiểm tra sức chứa theo **thợ × thời gian**, không theo số lịch.
- **BR-WS02-03:** Chuyển đổi từ mô hình cũ: thời lượng mặc định của lịch không rõ hạng mục bằng một khung MVP (60 phút), để dữ liệu cũ vẫn đúng.
- **BR-WS02-04 — Hạn phản hồi:**
  - Trước hạn chót duyệt tay (us-029 BR-015), nhắc chủ xưởng khi đã qua 50% thời gian.
  - Khi hết hạn, **thay vì chỉ tự huỷ**, hệ thống gọi BK-01 để giữ phương án thay thế cho chủ xe rồi mới huỷ lịch cũ.
- **BR-WS02-05:** Chỗ dự phòng cho khách vãng lai có thể đặt theo tỉ lệ thực tế của xưởng trong 30 ngày. Hệ thống đề xuất con số, chủ xưởng quyết định.
- **BR-WS02-06:** Thời lượng thực tế (từ tiến độ 6 bước) được ghi lại để đề xuất điều chỉnh thời lượng chuẩn. Đây cũng là dữ liệu đầu vào cho BK-10.

**Tình huống:** bảo dưỡng lớn 150 phút chiếm 5 khung 30 phút; kiểm tra nhanh 30 phút chiếm 1 khung; xưởng chậm duyệt thì chủ xe nhận phương án thay thế trước khi lịch cũ bị huỷ; dữ liệu cũ không có hạng mục được coi là 60 phút.

**Tiêu chí chấp nhận**

- AC-WS02-01: Không thợ nào bị gán hai lịch chồng thời gian.
- AC-WS02-02: AC-F6-01 vẫn đạt với mô hình thời lượng.
- AC-WS02-03: Lịch bị huỷ do xưởng chậm duyệt luôn đi kèm phương án thay thế, hoặc lý do không có.

---

#### WS-03 — Tài khoản kỹ thuật viên và tự phân công

| Giai đoạn | Loại | MoSCoW | Pain point | Nền tảng MVP |
| --- | --- | --- | --- | --- |
| P2-B | Chức năng | Must | PP2-12 | Xác thực chủ xưởng (F2); `total_technicians` |

**Quy tắc nghiệp vụ**

- **BR-WS03-01:** Chủ xưởng mời KTV bằng email Google. KTV đăng nhập Google như các vai trò khác, gắn với đúng một xưởng.
- **BR-WS03-02:** Hồ sơ KTV gồm tên, kỹ năng (danh mục hạng mục làm được) và lịch làm việc. Số KTV đang hoạt động thay cho `total_technicians` trong tính sức chứa (đường chuyển đổi: P2Q-01).
- **BR-WS03-03 — Quyền KTV:**
  - Được: xem lịch được giao, cập nhật tiến độ, tạo nháp báo giá phát sinh, dùng trợ lý TA-01.
  - Không được: duyệt báo giá, đổi luật xưởng, xem doanh thu.
- **BR-WS03-04 — Tự phân công:** lịch đã xác nhận được gán cho KTV có đủ kỹ năng và ít tải nhất trong khung đó. Chủ xưởng đổi tay được.
- **BR-WS03-05:** KTV nghỉ đột xuất thì sức chứa giảm ngay. Các lịch đã gán được phân lại; không đủ người thì gọi BK-01 S13 cho các lịch bị ảnh hưởng.
- **BR-WS03-06:** Mọi thao tác của KTV ghi log có người thực hiện.

**Tiêu chí chấp nhận**

- AC-WS03-01: KTV không truy cập được dữ liệu của xưởng khác, hoặc của lịch không được giao khi luật xưởng chỉ cho xem lịch được giao.
- AC-WS03-02: Đánh dấu KTV nghỉ làm giảm sức chứa các khung liên quan ngay lập tức.

---

### 7.7 Nhóm TA — Trợ lý kỹ thuật viên

#### TA-01 — Trợ lý tra cứu và nhắc việc

| Giai đoạn | Loại | MoSCoW | Pain point | Nền tảng MVP |
| --- | --- | --- | --- | --- |
| P2-B | Chức năng | Should | PP2-12 | Lịch sử dịch vụ từ hãng, us-057, chat của chủ xe (chủ xưởng đọc được đoạn dẫn tới booking — F4) |

| Tình huống | Agent làm gì | Ví dụ câu hỏi |
| --- | --- | --- |
| Tra lịch sử bảo dưỡng của xe | Tìm theo biển số, VIN, tên khách hoặc mã lịch hẹn; gồm cả lần làm ở xưởng khác (dữ liệu hãng) | "Xe 30A-123.45 lần trước thay gì?" |
| Nhắc lịch cho KTV | Lịch hôm nay, xe sắp đến, bước tiến độ chưa cập nhật | "Hôm nay tôi có mấy xe?" |
| Tình trạng xe trước khi nhận | Tóm tắt ODO, mốc, triệu chứng khách kể, báo giá đã duyệt, khuyến nghị chưa làm, triệu hồi | "Tóm tắt xe 10 giờ sắp vào" |
| KTV quên mình đã làm cho ai | Liệt kê việc đã làm theo thời gian | "Tuần trước tôi làm những xe nào?" |

**Quy tắc nghiệp vụ**

- **BR-TA01-01:** Chỉ trả dữ liệu của xưởng mình. Thông tin cá nhân chủ xe được che bớt (tên rút gọn, SĐT ẩn).
- **BR-TA01-02:** Nhắc chủ động: 15 phút trước giờ xe đến; khi một bước tiến độ quá thời lượng chuẩn mà chưa cập nhật.
- **BR-TA01-03:** Tóm tắt xe chỉ dùng dữ liệu có thật. Phần nào thiếu thì nói thiếu, không đoán.

**Tiêu chí chấp nhận**

- AC-TA01-01: KTV hỏi về xe không thuộc xưởng mình thì bị từ chối.
- AC-TA01-02: Tóm tắt xe trùng khớp dữ liệu nguồn (eval ≥ 30 ca).

---

#### TA-02 — Hỗ trợ tại khoang làm việc

| Giai đoạn | Loại | MoSCoW | Pain point | Nền tảng MVP |
| --- | --- | --- | --- | --- |
| P2-C | Chức năng | Could | PP2-12 | RAG (`maintenance_manual`) |

**Quy tắc nghiệp vụ**

- **BR-TA02-01:** Checklist hạng mục theo mốc lấy từ tài liệu kỹ thuật của hãng. KTV đánh dấu từng mục; checklist hoàn tất là điều kiện chuyển bước tiến độ.
- **BR-TA02-02:** Tóm tắt giao ca: xe đang làm dở, chờ phụ tùng, chờ khách duyệt.
- **BR-TA02-03:** Hỏi và nhập bằng giọng nói khi trình duyệt cho phép. Nội dung chuyển thành chữ phải được KTV xác nhận trước khi lưu.

**Tiêu chí chấp nhận**

- AC-TA02-01: Không chuyển được sang bước "hoàn tất" khi checklist bắt buộc còn mục chưa đánh dấu.

---

### 7.8 Nhóm MC — Chat giữa xưởng và chủ xe

#### MC-01 — Chat theo từng lịch hẹn

| Giai đoạn | Loại | MoSCoW | Pain point | Nền tảng MVP |
| --- | --- | --- | --- | --- |
| P2-C | Chức năng | Could | PP2-13 | Lưu hội thoại (F4); ADR-01 (mục "Khi nào xem lại Firestore") |

**Quy tắc nghiệp vụ**

- **BR-MC01-01:** Mỗi lịch hẹn có một luồng chat. Luồng mở khi lịch `confirmed`, đóng sau `THREAD_CLOSE_DAYS` (đề xuất 7) ngày kể từ `completed` hoặc `cancelled`. Luồng đã đóng vẫn đọc được.
- **BR-MC01-02:** Người tham gia gồm chủ xe, chủ xưởng và KTV được giao. Không hiển thị SĐT hay email cá nhân của bất kỳ bên nào.
- **BR-MC01-03:** Hỗ trợ chữ, ảnh và các thẻ (báo giá phát sinh AD-04, cập nhật tiến độ).
- **BR-MC01-04:** Xưởng cam kết thời gian phản hồi trong giờ làm việc (`WS_REPLY_SLA_MIN`). Quá hạn thì nhắc chủ xưởng.
- **BR-MC01-05:** Lưu toàn bộ để giải quyết tranh chấp, theo thời hạn lưu PQ-09.
- **BR-MC01-06:** Trước khi làm phải chốt lại ADR-01 (realtime người–người). Đây là P2Q-12.

**Tiêu chí chấp nhận**

- AC-MC01-01: Không có SĐT hoặc email cá nhân trong payload gửi cho phía bên kia.

---

#### MC-02 — Agent cùng tham gia luồng chat

| Giai đoạn | Loại | MoSCoW | Pain point | Nền tảng MVP |
| --- | --- | --- | --- | --- |
| P2-C | Chức năng | Could | PP2-13 | MC-01 |

**Quy tắc nghiệp vụ**

- **BR-MC02-01:** Ngoài giờ, agent trả lời các câu thuộc phạm vi AD và HS, ghi rõ "Trợ lý EV Care".
- **BR-MC02-02:** Agent giải thích thuật ngữ cho chủ xe và tóm tắt luồng chat cho xưởng khi được hỏi.
- **BR-MC02-03:** Agent không thay xưởng hứa hẹn về giá, thời gian, bảo hành. Câu nào cần cam kết thì gắn cờ cho người của xưởng.

---

### 7.9 Nhóm PL — Nền tảng chung

#### PL-01 — Quyền riêng tư và sự đồng ý

| Giai đoạn | Loại | MoSCoW | Pain point | Nền tảng MVP |
| --- | --- | --- | --- | --- |
| P2-A | Chức năng | Must | PP2-08 | Nguyên tắc Privacy (PRD MVP §7), xoá hội thoại theo yêu cầu (F4) |

**Quy tắc nghiệp vụ**

- **BR-PL01-01:** Một màn **Quyền riêng tư** với các công tắc riêng: bộ nhớ dài hạn (PS-01), đồng bộ lịch (BK-04), vị trí (BK-01, BK-05), dùng dữ liệu cho gợi ý cá nhân (PS-02, PS-04), mức tự động hoá đặt lịch (BK-01).
- **BR-PL01-02:** Mặc định: bộ nhớ dài hạn **bật** (có thông báo lần đầu); đồng bộ lịch **tắt**; vị trí hỏi khi cần; tự đặt lịch **tắt**. Mặc định cuối cùng chờ PO chốt (P2Q-11).
- **BR-PL01-03:** Tắt một công tắc thì dừng dùng ngay. Bấm "Xoá dữ liệu" thì xoá dữ liệu liên quan trong `DELETE_SLA_HOURS` (đề xuất 24).
- **BR-PL01-04:** Mọi thay đổi đồng ý được ghi log (thời điểm, giá trị cũ, giá trị mới).

**Tiêu chí chấp nhận**

- AC-PL01-01: Tắt đồng bộ lịch thì lần gọi bộ lập lịch kế tiếp không dùng dữ liệu bận/rảnh.
- AC-PL01-02: Xoá bộ nhớ dài hạn thì không còn bản ghi nào sau thời hạn xoá.

---

#### PL-02 — Chuyển sang người thật

| Giai đoạn | Loại | MoSCoW | Pain point | Nền tảng MVP |
| --- | --- | --- | --- | --- |
| P2-B | Chức năng | Should | PP2-08, PP2-09 | Nguyên tắc Escalation (PRD MVP §7); F9 `has_issue` |

**Quy tắc nghiệp vụ**

- **BR-PL02-01 — Điều kiện chuyển:**
  - Chủ xe yêu cầu.
  - Agent không có nguồn sau 2 lần hỏi lại.
  - Tranh chấp bảo hành.
  - Dấu hiệu bực bội (PS-05).
  - Hỏi thăm sau dịch vụ có `has_issue` hoặc điểm ≤ 2.
- **BR-PL02-02:** Khi chuyển, gửi kèm tóm tắt: vấn đề, xe, lịch hẹn liên quan, những gì agent đã trả lời. Bên nhận là chủ xưởng của lịch liên quan, hoặc của xưởng ưa thích nếu không có lịch.
- **BR-PL02-03:** Xưởng thấy yêu cầu trên Workshop Board với nhãn "cần liên hệ khách". Đây là một nhãn trên lịch hẹn hoặc hồ sơ khách, **không** đưa lại thực thể phiếu hỗ trợ đã bỏ ở v3.7.
- **BR-PL02-04:** Chủ xe thấy trạng thái: đã chuyển, xưởng đã xem, đã liên hệ.

**Tiêu chí chấp nhận**

- AC-PL02-01: Hỏi thăm có điểm ≤ 2 tạo nhãn "cần liên hệ khách" cho xưởng trong ≤ 1 phút.

---

#### PL-03 — Chỉ số đo hiệu quả

| Giai đoạn | Loại | MoSCoW |
| --- | --- | --- |
| P2-A | Phi chức năng | Must |

**Quy tắc nghiệp vụ**

- **BR-PL03-01:** Ghi sự kiện có cấu trúc cho mọi bước đặt lịch, gợi ý, chuyển người, tự nhận, huỷ, lỡ hẹn, check-in, bắt đầu và kết thúc làm, bàn giao.
- **BR-PL03-02:** Sự kiện không chứa thông tin cá nhân. Định danh người dùng được băm.
- **BR-PL03-03:** Có bảng tổng hợp cho các chỉ số ở mục 12, cập nhật hằng ngày.

**Tiêu chí chấp nhận**

- AC-PL03-01: Tính được đủ các chỉ số M-01…M-12 từ sự kiện, không cần truy vấn tay.

---

## 8. Bài toán lập lịch

Mục này mô hình hoá bài toán để nhóm thống nhất trước khi viết tài liệu kỹ thuật riêng (đề xuất đặt ở `docs/architecture/`). Có hai tầng, làm ở hai thời điểm khác nhau.

| Tầng | Câu hỏi | Tính năng | Loại | Giai đoạn |
| --- | --- | --- | --- | --- |
| 1. Thoả mãn ràng buộc | Có lịch nào hợp lệ không? Nếu có, đưa 1–3 lịch hợp lý | BK-01 | Chức năng | P2-A |
| 2. Tối ưu | Trong các lịch hợp lệ, lịch nào tốt nhất cho cả chủ xe và xưởng? | BK-10 | Phi chức năng | P2-C |

### 8.1 Thành phần của bài toán

| Thành phần | Nội dung |
| --- | --- |
| Đối tượng cần xếp | Lịch hẹn *b*: xe, hạng mục, thời lượng *d(b)*, ràng buộc của chủ xe |
| Tài nguyên | Xưởng *w*; khoang hoặc KTV *k* thuộc *w*, có kỹ năng và giờ làm |
| Biến quyết định | *x(b, w, k, t)* ∈ {0, 1}: lịch *b* bắt đầu ở xưởng *w*, khoang/KTV *k*, thời điểm *t* |
| Ràng buộc cứng | (1) Mỗi lịch được xếp đúng một lần. (2) Thời điểm thuộc khung rảnh của chủ xe, trước hạn chót của mốc. (3) Xưởng thuộc khu vực chủ xe chấp nhận. (4) Tại mọi thời điểm, mỗi khoang/KTV làm tối đa một xe; không vượt sức chứa sau khi trừ chỗ dự phòng và chỗ khoá. (5) Nằm trong giờ hoạt động của xưởng và giờ làm của KTV. (6) KTV có kỹ năng cho mọi hạng mục. (7) Phụ tùng có trước giờ bắt đầu, nếu chủ xe chọn "chỉ xưởng có sẵn". (8) Lịch đã `confirmed` không bị dời nếu chủ xe chưa đồng ý. |
| Ràng buộc mềm | Xưởng yêu thích, giờ hay chọn, mức giá, đánh giá: vi phạm thì cộng điểm phạt |

### 8.2 Năm mục tiêu thời gian

| Ký hiệu | Mục tiêu | Định nghĩa đề xuất | Có lợi cho | Cần chốt |
| --- | --- | --- | --- | --- |
| T₁ | Thời gian đặt lịch ngắn | Từ lúc chủ xe yêu cầu đến khi có lịch được xác nhận | Chủ xe | P2Q-10: có tính cả khoảng chờ đến ngày hẹn không? |
| T₂ | Thời gian xử lý bảo dưỡng ngắn | Thời gian KTV thực làm trên xe; giảm nhờ xếp đúng kỹ năng và có sẵn phụ tùng | Cả hai | — |
| T₃ | Thời gian nghỉ của xưởng ít | Tổng thời gian khoang và KTV để trống trong giờ hoạt động | Xưởng | Có tính chỗ dự phòng cho vãng lai không? |
| T₄ | Thời gian chờ bảo dưỡng ngắn | Từ lúc xe tới xưởng (check-in) đến lúc KTV bắt đầu làm | Chủ xe | — |
| T₅ | Thời gian giao nhận xe ngắn | Từ check-in đến lúc bàn giao xe (= chờ + xử lý + chờ bàn giao) | Chủ xe | — |

**Hàm mục tiêu** (dạng tổng có trọng số, trọng số chờ chốt ở P2Q-10):

```
min  w₁·T₁ + w₂·T₂ + w₃·T₃ + w₄·T₄ + w₅·T₅ + w₆·Phạt_sở_thích
với  x(b, w, k, t) ∈ {0, 1}, thoả mọi ràng buộc cứng ở 8.1
```

### 8.3 Đánh đổi cần biết

- **T₃ xung đột với T₄ và T₅.** Xếp lịch sát nhau để thợ không rảnh thì một xe trễ sẽ dồn trễ cho các xe sau, khách phải chờ. Trọng số quyết định xưởng nghiêng về phía nào.
- **T₁ xung đột với sở thích.** Xếp ngay vào chỗ trống sớm nhất thì có lịch nhanh, nhưng có thể không đúng xưởng yêu thích.
- Vì vậy BK-10 cho từng xưởng chỉnh trọng số trong giới hạn, và đo bằng A/B so với lời giải theo luật.

### 8.4 Cách giải đề xuất

| Giai đoạn | Cách giải | Ghi chú |
| --- | --- | --- |
| P2-A (BK-01) | Lọc theo ràng buộc cứng → chấm điểm theo luật có trọng số → lấy 1–3 phương án | Đủ nhanh, dễ giải thích, làm mốc so sánh |
| P2-C (BK-10) | Solver lập lịch ràng buộc (ví dụ OR-Tools CP-SAT). Chạy **theo lô** (mỗi đêm cho ngày mai, gán khoang/KTV) và **theo sự kiện** (huỷ, trễ, vãng lai, KTV nghỉ) | Chỉ sắp xếp lại lịch đang giữ chỗ và phân công nội bộ; lịch `confirmed` chỉ dời khi chủ xe đồng ý |

**Dữ liệu cần có trước khi làm BK-10:**
- Thời lượng thực tế từng hạng mục (WS-02, từ tiến độ 6 bước).
- Giờ khách thực tới so với giờ hẹn.
- Tỉ lệ lỡ hẹn theo xưởng và theo khung (BK-02).

Cần tối thiểu `OPT_MIN_DATA_WEEKS` (đề xuất 8) tuần dữ liệu thật của xưởng.

---

## 9. Nguyên tắc kiểm soát AI (bổ sung)

Giữ nguyên toàn bộ PRD MVP §7. Bổ sung các nguyên tắc sau:

| Nguyên tắc | Quy tắc |
| --- | --- |
| Constraint first | Bộ lập lịch là code xác định. LLM chỉ thu thập ràng buộc và diễn giải kết quả; không tự chọn xưởng hay giờ. |
| Consent for automation | Tự giữ chỗ, tự đặt, đồng bộ lịch, bộ nhớ dài hạn chỉ chạy khi chủ xe đã đồng ý (PL-01). |
| Range, not price | Tư vấn sửa chữa luôn là khoảng giá kèm ngày cập nhật; giá cuối chỉ đến từ báo giá được xưởng duyệt. |
| Safety before price | Triệu chứng an toàn: lời khuyên an toàn đứng trước mọi thông tin giá hoặc lịch. |
| Explainable suggestion | Mọi đề xuất tự động có lý do lấy từ dữ liệu xếp hạng thật (PS-03). |
| Memory transparency | Agent nói khi dùng bộ nhớ; chủ xe xem và xoá được (PS-01). |
| Style, not substance | Cá nhân hoá phong cách không đổi số liệu, nguồn, cảnh báo (PS-05). |
| Role boundary | Agent của KTV chỉ thấy dữ liệu xưởng mình; agent trong chat nhiều bên không hứa thay xưởng (TA-01, MC-02). |

---

## 10. Yêu cầu phi chức năng (bổ sung)

| ID | Nhóm | Yêu cầu |
| --- | --- | --- |
| NFR-01 | Tính đúng | Mọi lịch tạo ra qua bộ lập lịch đi qua service sức chứa duy nhất; không có đặt trùng kể cả khi chạy đồng thời. |
| NFR-02 | Tính đúng | Đổi xưởng, đổi lịch là nguyên tử: không có trạng thái mất cả lịch cũ lẫn lịch mới. |
| NFR-03 | Hiệu năng | BK-01 trả phương án ≤ 2 s (p90), với bán kính 10 km và cửa sổ 14 ngày. |
| NFR-04 | Hiệu năng | BK-10: giải theo lô ≤ 30 s cho một xưởng một ngày; giải theo sự kiện ≤ 3 s. |
| NFR-05 | Chất lượng lời giải (BK-10) | Hàm mục tiêu tốt hơn lời giải theo luật ≥ `OPT_MIN_GAIN` trên dữ liệu thử; không vi phạm ràng buộc cứng. |
| NFR-06 | Riêng tư | Dữ liệu lịch chỉ lấy bận/rảnh; bộ nhớ chỉ thuộc danh mục cho phép; xoá trong `DELETE_SLA_HOURS`. |
| NFR-07 | Chi phí | Google Maps và Google Calendar API có lưu đệm, giới hạn theo người dùng, cảnh báo khi đạt 80% ngân sách tháng. |
| NFR-08 | Khả dụng | API bản đồ hoặc lịch lỗi thì luồng đặt lịch vẫn chạy (danh sách, nhập tay). |
| NFR-09 | Quan sát | Mỗi lần lập lịch ghi: ràng buộc đầu vào (đã ẩn danh), số phương án, lý do loại, thời gian chạy. |
| NFR-10 | Bảo mật | Phân quyền KTV theo xưởng và theo lịch được giao; log hành động KTV. |
| NFR-11 | Khả năng tiếp cận | Gợi ý một chạm và thẻ trong chat dùng được bằng bàn phím và trình đọc màn hình; vùng chạm ≥ 44 px. |

---

## 11. Dữ liệu & tích hợp

### 11.1 Dữ liệu mới (dự kiến, chi tiết ở entity spec)

Tên dưới đây là tên làm việc. Mã `ENT-xxx` sẽ được cấp khi viết entity spec.

| Thực thể | Dùng cho | Nội dung chính |
| --- | --- | --- |
| `owner_scheduling_profile` | BK-01 | Khung rảnh, địa điểm và bán kính, xưởng yêu thích, mức tự động hoá |
| `booking_series` | BK-06 | Xe, xưởng, ràng buộc, trạng thái chuỗi |
| `booking_waitlist` | BK-07 | Chủ xe, xưởng, khung hoặc khoảng, thứ tự, lời mời đang mở |
| `owner_reliability_event` | BK-02 | Loại sự kiện (huỷ muộn, lỡ hẹn, miễn), điểm, lịch hẹn, lý do |
| `service_item_duration` | WS-02, BK-10 | Thời lượng chuẩn theo hạng mục và xưởng; thời lượng thực tế |
| `workshop_booking_rule` | WS-01 | Luật tự nhận và tham số |
| `technician` + `technician_skill` + `booking_assignment` | WS-03, TA-01 | KTV, kỹ năng, phân công |
| `repair_price` | AD-02 | Mã phụ tùng, giá phụ tùng, tiền công, thời lượng, ngày cập nhật |
| `workshop_part_stock` | BK-09 | Tồn kho đơn giản theo mã phụ tùng |
| `agent_memory` | PS-01 | Loại, giá trị, nguồn, hạn, trạng thái xoá |
| `user_consent` | PL-01 | Loại đồng ý, giá trị, thời điểm, lịch sử |
| `review_tag` | PS-02 | Tag đánh giá gắn với `follow_up` |
| `history_share_link` | HS-01 | Link chia sẻ, hạn, trạng thái thu hồi |
| `booking_thread` | MC-01 | Luồng chat theo lịch hẹn (sau khi chốt ADR) |
| `quote` (mở rộng) | AD-04 | Thêm loại "phát sinh", ảnh, ngưỡng đồng ý |

### 11.2 Tích hợp ngoài

| Hệ thống | Dùng cho | Ghi chú |
| --- | --- | --- |
| Google Maps Platform (bản đồ, tìm địa điểm, tuyến đường) | BK-05, BK-01 | Tính phí theo lượt; cần ngân sách (P2Q-07) |
| Google Calendar API | BK-04, BK-01 | OAuth với phạm vi tối thiểu (bận/rảnh, tạo sự kiện); cần màn đồng ý (PL-01) |
| Hệ thống hãng: bảo hành theo VIN | AD-03 | Cần xác nhận hãng (mock) có trả dữ liệu này (P2Q-05) |
| Hệ thống hãng: chiến dịch triệu hồi, cập nhật phần mềm | HS-02, TA-01 | Cần xác nhận nguồn (P2Q-06) |
| Phần mềm kho của xưởng | BK-09 | Không bắt buộc; mặc định nhập tay (P2Q-08) |
| OR-Tools (thư viện) | BK-10 | Thư viện mã nguồn mở, chạy trong worker |

---

## 12. Chỉ số thành công

| ID | Chỉ số | Mục tiêu đề xuất | Tính năng | Cách đo |
| --- | --- | --- | --- | --- |
| M-01 | Thời gian từ ý định đặt lịch đến xác nhận (median) | < 60 giây (MVP: < 2 phút) | BK-01, CH-01 | Sự kiện PL-03 |
| M-02 | Số chạm để đặt xong một lịch (median); số ký tự phải gõ | ≤ 6 chạm; 0 ký tự với luồng chuẩn | CH-01 | Sự kiện |
| M-03 | Yêu cầu đặt lịch có ≥ 1 phương án hợp lệ, hoặc lý do rõ kèm gợi ý nới ràng buộc | ≥ 95% | BK-01 | Log bộ lập lịch |
| M-04 | Tỉ lệ bấm gợi ý một chạm trên số lần hiển thị | Đo, đặt mục tiêu sau 4 tuần | CH-01 | Sự kiện |
| M-05 | Tỉ lệ lỡ hẹn, tỉ lệ huỷ muộn | Giảm so với baseline 4 tuần đầu | BK-02, BK-07 | Sự kiện |
| M-06 | Tỉ lệ lịch xưởng phải duyệt tay | ≤ 20% | WS-01 | Sự kiện |
| M-07 | Tỉ lệ chỗ bị huỷ được lấp lại từ danh sách chờ | Đo | BK-07 | Sự kiện |
| M-08 | Tỉ lệ câu hỏi giá, bảo hành, phụ tùng agent tự trả lời không cần chuyển xưởng | ≥ 80% | AD-01…04 | Log chat, PL-02 |
| M-09 | Thời gian chờ tại xưởng (T₄) và thời gian giao nhận xe (T₅), median | Đo baseline ở P2-A, mục tiêu đặt cho BK-10 | WS-02, BK-10 | Tiến độ 6 bước |
| M-10 | Thời gian nghỉ của KTV và khoang trong giờ hoạt động (T₃) | Như M-09 | WS-02, BK-10 | Phân công + tiến độ |
| M-11 | Tỉ lệ KTV dùng trợ lý ít nhất 1 lần/ngày làm việc | ≥ 50% sau 4 tuần | TA-01 | Log |
| M-12 | Tỉ lệ chủ xe giữ bộ nhớ dài hạn bật; số yêu cầu xoá | Đo | PS-01, PL-01 | Log đồng ý |

Như PRD MVP, các chỉ số liên quan xưởng thật và chủ xe thật chỉ có ý nghĩa khi chạy pilot thật. Trên dữ liệu mock, chỉ kiểm tra tính đúng và hiệu năng.

---

## 13. Kế hoạch phát hành (đề xuất, chờ PM chốt)

| Giai đoạn | Thời gian dự kiến | Nội dung | Tiêu chí hoàn thành |
| --- | --- | --- | --- |
| Chuẩn bị | 02/11–08/11/2026 | Chốt câu hỏi mở mức P2-A; khảo sát giả thuyết H2-xx; viết spec P2-A | P2Q-02, 03, 04, 07, 11 đã chốt; spec FF/API/Entity cho P2-A |
| **P2-A** | 09/11–06/12/2026 (4 tuần) | BK-01…05, HS-01, PS-01, CH-01, CH-02, AD-01, WS-01, WS-02, PL-01, PL-03 | AC của P2-A đạt; M-01, M-02, M-03 có số liệu |
| **P2-B** | 07/12/2026–31/01/2027 (8 tuần) | WS-03 trước, sau đó TA-01, AD-02…04, BK-06…08, HS-02, PS-02, PS-03, PL-02 | AC của P2-B đạt; có KTV thử nghiệm |
| **P2-C** | Từ 02/2027 | BK-09, BK-10, PS-04, PS-05, TA-02, MC-01, MC-02 | BK-10 chỉ bắt đầu khi đủ `OPT_MIN_DATA_WEEKS` tuần dữ liệu thật |

**Thứ tự trong P2-A:**
1. PL-01 và PL-03 làm trước, vì là nền.
2. Tiếp theo WS-02 và BK-01, cùng đụng tới service sức chứa nên làm cùng nhau.
3. Rồi CH-01, CH-02, WS-01, BK-02.
4. Cuối cùng là các màn hình BK-04, BK-05, HS-01.

---

## 14. Rủi ro

| Rủi ro | Mức | Giảm thiểu |
| --- | --- | --- |
| Thay đổi service sức chứa (WS-02) làm hỏng quy tắc chống đặt trùng của MVP | Cao | Giữ AC-F6-01 trong bộ test hồi quy; chuyển đổi dữ liệu cũ theo BR-WS02-03; bật theo từng xưởng |
| Tự giữ chỗ chủ động làm khoá nhiều chỗ ảo | Cao | Thời hạn giữ ngắn (BR-BK01-06); giới hạn số lịch giữ chủ động mỗi xưởng mỗi ngày |
| Chủ xe mất lòng tin khi hệ thống tự đặt | Trung bình | Mặc định mức "giữ chỗ sẵn"; luôn có lý do; huỷ không tính điểm trong 2 giờ đầu |
| Bảng giá sửa chữa, tồn kho do xưởng nhập bị lỗi thời | Trung bình | Hiện ngày cập nhật; tự hạ trạng thái khi quá hạn; giá cuối qua HITL |
| Chi phí Google API vượt ngân sách | Trung bình | Lưu đệm, giới hạn, cảnh báo 80%, phương án dự phòng dạng danh sách |
| Thiếu dữ liệu bảo hành theo VIN và chiến dịch triệu hồi từ hãng | Trung bình | AD-03 trả lời theo tài liệu chung và ghi rõ; HS-02 tắt cho tới khi có nguồn |
| BK-10 phức tạp, không chứng minh được lợi ích | Trung bình | Để P2-C; chỉ bật khi vượt `OPT_MIN_GAIN` so với lời giải theo luật |
| Nhầm lẫn tên vai trò "Kỹ thuật viên" trong mã nguồn hiện tại | Trung bình | Chốt P2Q-01 trước khi làm WS-03 |
| Pain point chưa kiểm chứng | Trung bình | Khảo sát giả thuyết H2-xx (Phụ lục B) trong giai đoạn Chuẩn bị |
| Phạm vi phình to | Cao | Bám mục 6; P2-B chỉ bắt đầu khi P2-A đạt AC |

---

## 15. Phụ thuộc & giả định

**Phụ thuộc:**
- MVP đạt M8 với service sức chứa, F5b, F9, us-057 chạy ổn định.
- Có ngân sách Google Maps Platform.
- Hệ thống hãng (mock) mở rộng được dữ liệu bảo hành theo VIN và chiến dịch triệu hồi.
- Xưởng thử nghiệm sẵn sàng nhập thời lượng, bảng giá sửa chữa, tài khoản KTV.

**Giả định:**
- Chủ xe sẵn sàng khai ràng buộc một lần để được tự xếp lịch.
- Xưởng chấp nhận luật tự nhận thay vì duyệt từng lịch.
- Thời lượng chuẩn theo hạng mục đủ ổn định để lập lịch.
- Tiến độ 6 bước được KTV cập nhật đều, để có dữ liệu thời gian thực tế.

---

## 16. Câu hỏi mở

| ID | Câu hỏi | Đề xuất | Cần chốt trước |
| --- | --- | --- | --- |
| P2Q-01 | Vai trò mới tên gì trong mã nguồn, khi `/technician/*` đang là của chủ xưởng? Đường chuyển từ `total_technicians` sang danh sách KTV? | Đổi route của chủ xưởng thành `/workshop/*`; vai trò mới `technician`; `total_technicians` tính từ số KTV đang hoạt động | WS-03 |
| P2Q-02 | Ràng buộc nào của chủ xe là cứng, nào là mềm? Xưởng yêu thích kín thì ưu tiên đổi giờ hay đổi xưởng? | Như bảng ở BK-01; ưu tiên đổi giờ cùng xưởng trước | BK-01 |
| P2Q-03 | Thời gian giữ chỗ chủ động; lịch định kỳ giữ trước bao nhiêu ngày; mỗi lần có bắt buộc xác nhận? | 24 giờ; 14 ngày; có | BK-01, BK-06 |
| P2Q-04 | Mốc huỷ muộn, thời gian ân hạn lỡ hẹn, cửa sổ đếm, trọng số huỷ muộn; cố định toàn hệ thống hay xưởng tự cấu hình? | 24 giờ; 30 phút; 90 ngày; 0,5; cố định toàn hệ thống ở P2-A | BK-02 |
| P2Q-05 | Dữ liệu bảo hành theo VIN theo từng hạng mục lấy từ đâu? Mock hãng có trả về không? | Mở rộng API mock hãng | AD-03 |
| P2Q-06 | Nguồn dữ liệu chiến dịch triệu hồi và cập nhật phần mềm của hãng? | Mở rộng API mock hãng | HS-02 |
| P2Q-07 | Ngân sách tháng cho Google Maps Platform; dùng những API nào? | Bản đồ + tuyến đường; tìm địa điểm chỉ khi cần | BK-05 |
| P2Q-08 | Tồn kho phụ tùng: xưởng nhập tay hay tích hợp phần mềm kho? | Nhập tay ở P2-C | BK-09 |
| P2Q-09 | Ngưỡng bảo dưỡng sớm theo chính sách hãng? Có ảnh hưởng bảo hành không? | Lấy từ tài liệu hãng; không có thì 30 ngày / 1.000 km và không khẳng định về bảo hành | BK-03 |
| P2Q-10 | Định nghĩa chính xác và trọng số của 5 mục tiêu thời gian; T₁ có tính khoảng chờ đến ngày hẹn không; xưởng được chỉnh trọng số trong giới hạn nào? | Định nghĩa như 8.2; trọng số đặt sau khi có baseline M-09, M-10 | BK-10 |
| P2Q-11 | Mặc định của các công tắc quyền riêng tư | Như BR-PL01-02 | PL-01 |
| P2Q-12 | Chat người–người cần realtime: giữ Supabase hay xem lại Firestore (ADR-01)? | Viết ADR-02 khi bắt đầu P2-C | MC-01 |
| P2Q-13 | Ngưỡng đồng ý bắt buộc cho chi phí phát sinh và ngưỡng xưởng tự duyệt | 10% tổng; tự duyệt do xưởng đặt, mặc định tắt | AD-04 |

---

## 17. Truy vết

| Mục PRD bổ sung | Tài liệu MVP liên quan |
| --- | --- |
| BK-01, BK-06, BK-07 | PRD MVP F6; `docs/specs/sprint-3/feature-functional/us-029`; `sprint-4/feature-functional/us-061`; `ai-agent/ai-004` |
| BK-02, BK-08 | PRD MVP F6b, F7; `sprint-3/feature-functional/us-033`, `us-053`, `us-037` |
| BK-03 | PRD MVP F3, F7; `sprint-2/feature-functional/us-017`, `us-021` |
| BK-04, BK-05 | `sprint-3/feature-functional/us-029`, `us-053` |
| BK-09, AD-01, AD-02 | PRD MVP F5; `sprint-2/feature-functional/us-045`; `ai-agent/ai-003` |
| BK-10, WS-02 | PRD MVP F6 (PQ-03); `sprint-4/feature-functional/us-057` |
| HS-01, HS-02 | PRD MVP F3 (đồng bộ lịch sử từ hãng) |
| PS-01, PS-03 | `ai-agent/ai-004` §13 Memory; `us-061` BR-1503 |
| PS-02, PL-02 | PRD MVP F9; `sprint-4/feature-functional/us-041` |
| CH-01, CH-02 | PRD MVP F4; `sprint-2/feature-functional/us-025`; `us-061` |
| AD-03 | PRD MVP F4; `ai-agent/ai-002` |
| AD-04 | PRD MVP F5b; `sprint-3/feature-functional/us-049`; `ai-agent/ai-005` |
| WS-01 | PRD MVP F6, F8; `us-029` BR-014, BR-015; `us-037` |
| WS-03, TA-01, TA-02 | PRD MVP §4 (thuật ngữ vai trò); F2 |
| MC-01, MC-02 | PRD MVP §9.1 (ADR-01) |
| Toàn bộ | Trang thuyết trình đề xuất (cột "Trang trình bày" ở mục 6) |

---

## Phụ lục A — Thuật ngữ

| Thuật ngữ | Nghĩa trong tài liệu này |
| --- | --- |
| Ràng buộc cứng | Điều kiện bắt buộc thoả mãn; lịch vi phạm thì không được đề xuất. Ví dụ: khung giờ rảnh, bán kính. |
| Ràng buộc mềm / sở thích | Điều kiện nên thoả mãn; vi phạm thì bị trừ điểm chứ không bị loại. Ví dụ: xưởng yêu thích. |
| Bộ lập lịch | Service backend tìm và giữ lịch hợp lệ (BK-01), sau này tối ưu (BK-10). |
| Giữ chỗ chủ động | Hệ thống tự giữ một chỗ cho chủ xe trước khi chủ xe yêu cầu, chờ xác nhận một chạm. |
| Chuỗi lịch định kỳ | Cấu hình để hệ thống tự tạo lịch cho từng mốc tại một xưởng (BK-06). |
| Huỷ muộn | Huỷ trong vòng `LATE_CANCEL_HOURS` trước giờ hẹn. |
| Lỡ hẹn (no-show) | Không đến, không báo, quá thời gian ân hạn. |
| Điểm tin cậy | Tổng điểm huỷ muộn và lỡ hẹn của chủ xe trong cửa sổ đếm (BK-02). Không phải điểm tín dụng. |
| Thời lượng chuẩn | Thời gian dự kiến để làm một hạng mục, dùng để tính sức chứa (WS-02). |
| Khoang | Vị trí làm việc có cầu nâng hoặc thiết bị; một xe chiếm một khoang trong thời gian làm. |
| Gợi ý một chạm (chip) | Nút bấm bên dưới khung chat, gửi một ý định đã định nghĩa sẵn (CH-01). |
| Thẻ tương tác | Khối thông tin có nút trong chat: thẻ xưởng, vé, báo giá (CH-02). |
| Báo giá phát sinh | Báo giá cho hạng mục phát hiện thêm khi xe đang làm (AD-04). |
| HITL | Human-in-the-loop: con người duyệt trước khi hệ thống thực hiện. |
| Chức năng / phi chức năng | Chức năng: hệ thống làm được việc gì. Phi chức năng: làm việc đó tốt đến đâu (nhanh, đúng, tối ưu, an toàn). |
| P2-A / P2-B / P2-C | Ba giai đoạn của Phase 2: làm sớm, tầm trung, dài hạn. |

## Phụ lục B — Giả thuyết cần khảo sát (đề xuất bổ sung vào surveys.md)

| ID | Giả thuyết | Pain point |
| --- | --- | --- |
| H2-01 | Chủ xe có khung giờ và khu vực cố định khi đi bảo dưỡng, và sẵn sàng khai một lần để được tự xếp lịch. | PP2-01 |
| H2-02 | Khi xưởng quen kín lịch, phần lớn chủ xe chấp nhận xưởng khác gần đó thay vì chờ. | PP2-01 |
| H2-03 | Chủ xe muốn được hệ thống giữ sẵn lịch cho mốc kế tiếp. | PP2-02 |
| H2-04 | Chủ xe không lưu được đầy đủ lịch sử bảo dưỡng và cần khi bán xe. | PP2-03 |
| H2-05 | Chủ xe từng muốn bảo dưỡng sớm nhưng không biết có nên không. | PP2-04 |
| H2-06 | Chủ xe thích bấm gợi ý hơn gõ khi dùng chat trên điện thoại. | PP2-05 |
| H2-07 | Câu hỏi về giá sửa chữa và bảo hành chiếm phần lớn cuộc gọi tới xưởng. | PP2-06, PP2-09 |
| H2-08 | Chủ xe thường phải chờ tại xưởng dù đến đúng giờ. | PP2-07 |
| H2-09 | Huỷ muộn và lỡ hẹn chiếm tỉ lệ đáng kể số chỗ bỏ trống của xưởng. | PP2-10 |
| H2-10 | Thời lượng hạng mục chênh lệch đủ lớn để cách tính "1 lịch = 1 thợ" gây quá tải hoặc thợ ngồi chơi. | PP2-11 |
| H2-11 | KTV thường phải hỏi đồng nghiệp hoặc lục sổ để biết lịch sử xe. | PP2-12 |
| H2-12 | Báo giá phát sinh qua điện thoại làm xe phải chờ lâu để khách đồng ý. | PP2-13 |

Ngưỡng xác nhận giống surveys.md §4.

## Phụ lục C — Tóm tắt thay đổi so với PRD MVP

| # | PRD MVP | Phase 2 đề xuất | Tính năng |
| --- | --- | --- | --- |
| 1 | 2 vai trò (Chủ xe, Chủ xưởng) | Thêm Kỹ thuật viên | WS-03 |
| 2 | 1 booking = 1 thợ × 1 khung | Sức chứa theo thời lượng hạng mục | WS-02 |
| 3 | Tự nhận: bật hoặc tắt | Bộ luật tự nhận có lý do | WS-01 |
| 4 | Xưởng chậm duyệt thì tự huỷ | Tự huỷ kèm phương án thay thế giữ sẵn | WS-02 |
| 5 | Đổi lịch chỉ trong cùng xưởng | Đổi xưởng trong một thao tác | BK-01 |
| 6 | Phạt lỡ hẹn ngoài phạm vi | Điểm tin cậy và bậc xử lý, không phạt tiền | BK-02 |
| 7 | Phi mục tiêu "quản lý phụ tùng" | Mở một phần: bảng giá sửa chữa, tồn kho đơn giản | AD-02, BK-09 |
| 8 | Phiếu hỗ trợ đã bỏ | Không đưa lại; dùng nhãn "cần liên hệ khách" | PL-02 |
| 9 | Bộ nhớ agent: hội thoại + xưởng ưa thích | Bộ nhớ dài hạn có kiểm soát | PS-01, PL-01 |
| 10 | Không tích hợp bản đồ, lịch | Google Maps, Google Calendar | BK-04, BK-05 |
