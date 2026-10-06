# PRD — EV Care MVP (Team 4 người)

> AI Agent chăm sóc sau bán & lịch bảo dưỡng xe điện · Mã đề tài VF020-06
>
> **Nguồn chuẩn:** `docs/specs/**` (sprint-1 FF/API/Entity, `core.entity.md` v1.4) và `docs/project/ProjectCharter_EV_Care_MVP.docx`. Khi PRD này khác với `docs/specs`, `docs/specs` là chuẩn và PRD phải được cập nhật.
>
> **Pain point chưa kiểm chứng** (đề xuất bổ sung) không nằm trong PRD này — xem [surveys.md](../../personal/tungld-03005/surveys.md).

---

## 0. Thông tin tài liệu

| Field | Value |
| --- | --- |
| Product | EV Care — AI Agent Chăm sóc sau bán & lịch bảo dưỡng xe điện |
| Version | v3.5 |
| Status | Draft — chờ PO/Mentor duyệt |
| Product Owner | Lê Đức Tùng |
| Project Manager | Mai Văn Trung |
| Tech Lead | Nguyễn Lê Phước Tiến · Đinh Kim Thái · Lê Đức Tùng |
| Mentor | Phạm Văn Ngoan |
| Ngày cập nhật | 28/09/2026 |
| Khung thời gian | 21/09 → 30/10/2026 |

### Change log

| Version | Ngày | Thay đổi |
| --- | --- | --- |
| v1 | 18/09/2026 | `AI_MVP_PRD_Team4.docx` — 5 luồng chi tiết (nhắc, giá, lên lịch, CDP, tiến độ) |
| v2 | 26/09/2026 | `Update_AI_MVP_PRD_Team4.docx` — gọn lại 3 module, thêm no-show, QR |
| v3.0 | 28/09/2026 | Hợp nhất v1 + v2, căn theo `docs/specs` |
| v3.1 | 28/09/2026 | Sửa pain point gốc cho chuẩn; tách pain point đề xuất sang `surveys.md`; bổ sung acceptance criteria, NFR, release plan, phụ lục thay đổi |
| v3.2 | 28/09/2026 | Bổ sung yêu cầu lưu & truy vấn hội thoại (F4, AC-F4-04…06); ADR-01 so sánh Firestore và Supabase cho tin nhắn chat; PQ-09, PQ-10 |
| v3.3 | 28/09/2026 | F3: ODO và lịch sử dịch vụ chỉ đồng bộ từ hãng (job định kỳ + webhook), bỏ nhập ODO tay; sửa AC-F3-02, AC-F3-03 |
| v3.4 | 28/09/2026 | Kênh thông báo: MVP chỉ gửi qua **Discord** (mặc định, người dùng chưa cấu hình kênh); Email/SMS/Telegram/Slack và màn cài đặt kênh chuyển sang phase sau (Phụ lục B, NOTI-01); PQ-05, PQ-11 |
| v3.5 | 28/09/2026 | Chốt PQ-11: mỗi chủ xe nhận thông báo ở **kênh Discord riêng** (bot + liên kết tài khoản Discord một lần, ENT-417); chốt Q-310: mock hãng gửi webhook |
| v3.6 | 28/09/2026 | F7: số ngày nhắc trước do chủ xe cấu hình (mặc định 2 ngày); khung cài đặt kênh thông báo (mặc định Discord) đưa vào MVP, các kênh khác chờ adapter (NOTI-01 một phần) |
| v3.7 | 02/10/2026 | **Bỏ khỏi phạm vi:** kết nối Discord (ENT-417), báo giá HITL (F5b, `quote`/`quote_item`) và phiếu hỗ trợ (`support_ticket`). Mọi thông báo hiện trong mục Thông báo của app; khung cài đặt kênh giữ lại, các kênh ngoài (Zalo/Telegram/SMS/Email) "Sắp có". F9 chỉ còn hỏi thăm và ghi nhận phản hồi. |

---

## 1. Tóm tắt

**Vấn đề:** Chủ xe điện phải tự theo dõi mốc bảo dưỡng, khó tra hạng mục/chi phí đúng xe mình, không rõ điều kiện bảo hành, và khó có lịch ở xưởng. Phía xưởng, người điều phối bị chiếm thời gian bởi trao đổi lặp lại và dễ nhận lịch vượt số thợ.

**Giải pháp MVP:** Web app mobile-first có AI Agent hội thoại, chạy trên một luồng xuyên suốt:

```
Xe đã xác thực → Trạng thái đến hạn → Hỏi đáp có trích nguồn (RAG) → Dự toán chi phí
→ Đặt lịch theo sức chứa xưởng
→ Check-in → Hoàn tất → Hỏi thăm sau dịch vụ
```

**Thành công của MVP:** Demo 2 chạy trọn luồng trên dữ liệu hãng mock; mọi khẳng định kỹ thuật/bảo hành của AI có trích nguồn; không có booking nào vượt sức chứa xưởng kể cả khi đặt đồng thời.

---

## 2. Vấn đề (Pain points)

Cột **Bằng chứng** cho biết mức độ đã kiểm chứng. Pain point ở mức "Giả định" cần được xác nhận trong khảo sát ([surveys.md](../../personal/tungld-03005/surveys.md) §3) nhưng vẫn giữ trong PRD vì là tiền đề của đề tài.

### 2.1 Phía chủ xe

| ID | Pain point | Bằng chứng | Tính năng |
| --- | --- | --- | --- |
| PP-01 | **Áp lực tuân thủ lịch bảo dưỡng định kỳ.** Hãng quy định bảo dưỡng theo mốc km hoặc thời gian (cái nào đến trước). Chủ xe phải tự nhớ mốc; bỏ lỡ hoặc trễ đáng kể có thể ảnh hưởng quyền lợi bảo hành **theo điều kiện trong chính sách bảo hành của hãng**. | Có nguồn hãng (lịch bảo dưỡng VinFast — Charter phụ lục A) | F3, F7 |
| PP-02 | **Khó có lịch bảo dưỡng phù hợp.** Chủ xe phải gọi hoặc thử nhiều xưởng mới tìm được khung giờ còn nhận xe, thường chỉ gọi được trong giờ hành chính. | Giả định — có phản ánh đơn lẻ từ cộng đồng, chưa có số liệu | F6 |
| PP-03 | **Không có nơi tra hạng mục & chi phí theo đúng xe của mình.** Thông tin có nhưng rải rác theo từng mẫu xe trên blog/forum, không chính hãng, không cá nhân hoá theo mốc ODO thực tế. | Giả định — quan sát từ nguồn công khai | F4, F5 |
| PP-04 | **Không hiểu rõ điều kiện bảo hành** (điều gì làm mất hiệu lực, hạng mục nào được miễn phí, quy trình khiếu nại) nên dễ bất ngờ hoặc bực bội khi bị từ chối. | Giả định | F4, F5, F5b |

### 2.2 Phía xưởng dịch vụ

> Trong MVP, vai trò điều phối tại xưởng (cố vấn dịch vụ) do **chủ xưởng** đảm nhận — `core.entity.md` §4.1, W-11.

| ID | Pain point | Bằng chứng | Tính năng |
| --- | --- | --- | --- |
| PP-05 | **Người điều phối xưởng quá tải vì giao tiếp**, không phải vì thiếu kỹ năng: vừa nghe điện thoại hỏi giá/hạng mục, vừa xác nhận và đổi lịch, vừa trả lời khách hỏi tiến độ. MVP giảm tải ở phần **hỏi đáp và xác nhận lịch**; phần phụ tùng nằm ngoài phạm vi. | Giả định | F4, F5, F6, F8 |
| PP-06 | **Nhận lịch vượt số kỹ thuật viên khả dụng (overbooking)** trong cùng khung giờ, dẫn tới trễ hẹn dây chuyền và khách không hài lòng. MVP ngăn vượt sức chứa **đối với lịch đặt qua EV Care**; lịch từ kênh khác do chủ xưởng khoá tay. | Giả định | F6, F8 |
| PP-07 | **Khách không đến đúng hẹn (no-show)** mà không báo trước, làm lãng phí khung giờ đã giữ cho khách. | Giả định | F7 |

---

## 3. Mục tiêu & phi mục tiêu

### 3.1 Mục tiêu

| # | Mục tiêu | Pain point |
| --- | --- | --- |
| G1 | Chủ xe biết xe đang **Bình thường / Sắp đến hạn / Quá hạn** và mốc tiếp theo cần làm gì. | PP-01 |
| G2 | Thông tin hạng mục, chi phí, bảo hành đúng model + mốc, **có trích nguồn chính hãng**; không có nguồn thì không khẳng định. | PP-03, PP-04 |
| G3 | Đặt được lịch qua chat 24/7, **không vượt sức chứa** xưởng. | PP-02, PP-06 |
| G4 | Chủ xưởng xem và xử lý lịch hẹn trên một màn hình; giảm hỏi đáp lặp lại. | PP-05 |
| G5 | Nhắc lịch hẹn và cho phép huỷ/đổi sớm để giải phóng slot. | PP-07 |

### 3.2 Phi mục tiêu

Tối ưu doanh thu xưởng, upsell, dự đoán hỏng hóc, chẩn đoán lỗi qua ảnh, tổng đài/omnichannel, quản lý phụ tùng.

---

## 4. Người dùng

| Persona | Mô tả | Kênh | Spec |
| --- | --- | --- | --- |
| **Chủ xe** | Chủ **01** xe điện đã được hãng xác nhận sở hữu. Ưu tiên tài xế dịch vụ chạy 100–200 km/ngày và người mới mua xe. | Web App chủ xe (mobile-first) | FEAT-AUTH-001, 002 |
| **Chủ xưởng** | Người quản lý **01** xưởng thuộc mạng lưới hãng, được hãng xác nhận qua Gmail + CCCD. Kiêm vai trò cố vấn dịch vụ. | Workshop Portal (desktop-first) | FEAT-AUTH-003, 004 |
| **Hệ thống hãng (mock)** | Nguồn sự thật: chủ xe, xe, model, ODO, bảo hành, xưởng, lịch sử dịch vụ. | API mock | `mock-system/proposed_erd.latest.md` |

Không có role Service Advisor, nhân viên xưởng, Admin trong MVP.

### Use case tiêu biểu

- **UC-A — Tra cứu chi phí & bảo hành:** Chủ xe VF6 đạt 11.600 km hỏi *"Mốc 12.000 km cần làm gì, hết bao nhiêu, cái nào được miễn phí?"* → AI trả hạng mục theo mốc, tách miễn phí/tính phí, gắn nhãn "ước tính", trích dẫn tài liệu. Nếu hỏi về điều kiện mất bảo hành mà tài liệu không nêu → AI nói rõ chưa có nguồn và gợi ý liên hệ xưởng.
- **UC-B — Đặt lịch khi xưởng kín:** *"Đặt lịch 9h sáng thứ 7 ở Smart City"* → khung đã đủ thợ → AI đề xuất 14h cùng ngày hoặc xưởng Mỹ Đình 9h30 → chủ xe chọn → thẻ tóm tắt → bấm Xác nhận → nhận Booking Ticket + QR.

---

## 5. Phạm vi

| Ưu tiên | ID | Tính năng | Sprint |
| --- | --- | --- | --- |
| Must | F1 | Đăng ký/đăng nhập Google + onboarding + xác thực xe với hãng — chủ xe | S1 (đã có spec) |
| Must | F2 | Đăng ký/đăng nhập Google + onboarding + xác thực Gmail/CCCD với hãng — chủ xưởng | S1 (đã có spec) |
| Must | F3 | Hồ sơ xe & trạng thái đến hạn | S1–S2 |
| Must | F4 | Chat RAG có trích nguồn | S2 |
| Must | F5 | Dự toán chi phí theo model + mốc | S2 |
| Must | F6 | Đặt lịch hội thoại theo sức chứa | S3 |
| Must | F8 | Workshop Board | S3 |
| Should | F7 | Nhắc mốc bảo dưỡng + nhắc lịch hẹn | S3–S4 |
| Should | F6b | Booking Ticket + QR, huỷ/đổi lịch | S3–S4 |
| Could | F9 | Hỏi thăm sau dịch vụ | S4 |
| Could | F8b | Tiến độ chi tiết 6 bước (`service_progress`) | S4 |

**Out of scope (MVP):** báo giá HITL do chủ xưởng duyệt và phiếu hỗ trợ (bỏ ở v3.7); kết nối Discord (bỏ ở v3.7); đăng nhập SĐT/OTP; nhiều xe/tài khoản; nhiều xưởng/chủ xưởng; Zalo Mini App; app native; các kênh Email/SMS/Telegram/Slack/Zalo/push (phase sau — Phụ lục B); khung cài đặt kênh và số ngày nhắc trước đã có (v3.6); chẩn đoán lỗi qua ảnh; telematics/OBD/SOH; thanh toán/đặt cọc; kho phụ tùng (WMS/ERP); voicebot; CDP hành vi; role nhân viên xưởng/Admin; xưởng ngoài mạng lưới hãng; nhiều ca/ngày, giờ nghỉ trưa, lịch nghỉ lễ.

> F5b và F9 xuất phát từ `core.entity.md` (BR-004, BR-006) và Charter §4.1, không phải từ pain point đã kiểm chứng.

---

## 6. Yêu cầu tính năng

### F1 / F2 — Xác thực & onboarding

Đặc tả đầy đủ tại `docs/specs/sprint-1/feature-functional/us-001, us-005, us-009, us-013`. PRD không định nghĩa lại, chỉ chốt:

- Chỉ **Google OAuth qua Firebase Authentication**.
- Chủ xe khai **VIN / biển số**; hãng xác thực và trả về model, thông tin bảo hành, thông số kỹ thuật. Không có dropdown chọn model.
- Chủ xưởng không chọn xưởng; hãng trả về đúng một xưởng theo Gmail + CCCD.

### F3 — Hồ sơ xe & trạng thái đến hạn

- Mốc tiếp theo tính từ `maintenance_rule` theo `model_id`, ODO hiện tại và ngày bảo dưỡng gần nhất (lịch sử dịch vụ từ hãng, hoặc ngày mua nếu chưa có).
- Quy tắc: mốc km **hoặc** mốc thời gian, cái nào đến trước.
- Trạng thái: `NORMAL`, `DUE_SOON` (còn ≤ 500 km hoặc ≤ 14 ngày — PQ-01; ngưỡng đặt trong `.env`, sau này có thể theo xưởng / gói bảo hành), `OVERDUE`, `UNKNOWN` (chưa đồng bộ dữ liệu hãng hoặc model chưa có định mức).
- **ODO và lịch sử dịch vụ chỉ đến từ hãng.** Hãng thu thập ODO từ xe; EV Care nhận về bằng **job đồng bộ định kỳ** (pull API hãng) và/hoặc **webhook** hãng gọi khi có dữ liệu mới. Chủ xe **không** nhập hay sửa ODO.
- Dữ liệu hãng được lưu lại ở EV Care; màn hình và AI Agent đọc bản đã lưu, không gọi hãng mỗi lần xem. Luôn hiển thị thời điểm hãng cập nhật ODO.
- ODO đã ghi nhận không giảm: số hãng gửi nhỏ hơn số trước được lưu để truy vết nhưng không dùng.
- Không có ODO → chỉ tính theo thời gian, ghi rõ "hãng chưa có dữ liệu ODO" (EDGE-001).
- Tính toán do backend; LLM chỉ diễn giải.

**Acceptance criteria**
- AC-F3-01: *Given* xe có ODO 11.600 và mốc 12.000 km, *when* mở Home, *then* hiển thị `DUE_SOON`, còn 400 km, kèm tên mốc.
- AC-F3-02: *Given* xe không có ODO từ hãng, *when* tính trạng thái, *then* chỉ dựa trên thời gian và ghi rõ chưa có dữ liệu ODO từ hãng.
- AC-F3-03: *Given* hãng gửi ODO mới qua đồng bộ định kỳ hoặc webhook, *when* chủ xe mở Home sau đó, *then* trạng thái được tính theo ODO mới và hiển thị thời điểm hãng cập nhật.

### F4 — Chat RAG có trích nguồn

- Nguồn: `official_document` (owner_manual, maintenance_manual, warranty_policy, service_bulletin) → `document_chunk` (pgvector, 1024 chiều).
- Ngữ cảnh xe (model, ODO, trạng thái bảo hành, trạng thái đến hạn) được nạp tự động; không hỏi lại thông tin đã có.
- Mỗi khẳng định kỹ thuật/bảo hành kèm trích dẫn: tên tài liệu, phiên bản, đoạn.
- Không tìm thấy đoạn đủ liên quan → không khẳng định, nói rõ chưa có dữ liệu chính hãng, gợi ý liên hệ xưởng.
- **Không tự nêu** thời gian ân hạn (grace period) hay ngưỡng km mất bảo hành nếu tài liệu hãng không ghi (PQ-07).
- Câu hỏi ngoài bảo dưỡng định kỳ (va chạm, độ xe) → nói rõ ngoài phạm vi, gợi ý liên hệ xưởng.

**Lưu trữ & truy vấn hội thoại** (dùng chung cho mọi tính năng chat: F4, F5, F6)

- Mỗi chủ xe có các **hội thoại** (`conversation`) gắn với tài khoản và xe; mỗi hội thoại gồm các **tin nhắn** (`chat_message`) theo thứ tự thời gian.
- Lưu tin nhắn của người dùng, của trợ lý và kết quả tool call. Mỗi tin nhắn của trợ lý lưu kèm trích dẫn nguồn, tool đã gọi, id đối tượng nghiệp vụ được tạo (booking) và trace id.
- Backend là nơi **duy nhất** ghi tin nhắn. Câu trả lời của trợ lý được stream về client bằng SSE; chỉ lưu tin nhắn hoàn chỉnh.
- Trạng thái Agent giữa các lượt (LangGraph checkpoint) lưu cùng database với tin nhắn.
- Truy vấn cần hỗ trợ:
  - Mở lại app → tải hội thoại gần nhất (phân trang theo thời gian, mới nhất trước).
  - Danh sách hội thoại của chủ xe theo xe, theo thời gian.
  - Tìm theo từ khoá trong lịch sử chat của chính chủ xe.
  - Chủ xưởng xem đoạn hội thoại dẫn tới một booking của xưởng mình (chỉ đọc).
  - Xuất tin nhắn theo khoảng thời gian cho bộ eval và phân tích (ẩn danh).
- Chủ xe chỉ đọc hội thoại của mình. Chủ xe yêu cầu xoá thì xoá toàn bộ hội thoại và checkpoint liên quan.
- Thời gian lưu giữ: PQ-09.
- Cấu trúc bảng chi tiết cần một entity spec mới trong `docs/specs/entity` (dải `ENT-4xx`).

**Acceptance criteria**
- AC-F4-01: Câu trả lời có khẳng định kỹ thuật luôn có ít nhất 1 trích dẫn hợp lệ.
- AC-F4-02: Câu hỏi không có nguồn trong kho tài liệu → câu trả lời từ chối khẳng định, không bịa số liệu.
- AC-F4-03: Chủ xe không phải nhập lại model/ODO trong chat.
- AC-F4-04: Đóng app giữa chừng rồi mở lại → thấy đủ tin nhắn đã hoàn tất và Agent tiếp tục đúng ngữ cảnh (vd. đang chờ xác nhận đặt lịch).
- AC-F4-05: Một chủ xe gọi API đọc hội thoại của chủ xe khác → bị từ chối.
- AC-F4-06: Booking tạo từ chat truy ngược được về tin nhắn xác nhận của chủ xe.

### F5 — Dự toán chi phí

- Tool tính: hạng mục của mốc (`maintenance_rule`) × giá của xưởng (`service_price`, ghép `model_id` + `item_code`). Xưởng thiếu giá → dùng `maintenance_rule.estimated_cost` và ghi "giá tham khảo" (EDGE-004).
- Tách hạng mục **trong bảo hành** và **tính phí**; tổng = tổng các mục tính phí.
- Mọi con số gắn nhãn **"Chi phí ước tính"**.
- LLM không tự cộng hay sửa số; chỉ hiển thị kết quả tool.

**Acceptance criteria**
- AC-F5-01: Tổng dự toán bằng đúng tổng giá các hạng mục tính phí do tool trả về.
- AC-F5-02: Hạng mục không có giá xưởng hiển thị giá tham khảo kèm nhãn.

### F5b — Báo giá HITL (đã bỏ ở v3.7)

Không còn trong phạm vi. Chủ xe xem dự toán (F5) rồi đặt lịch trực tiếp; chi phí cuối cùng do xưởng xác nhận khi kiểm tra xe.

### F6 — Đặt lịch theo sức chứa

- Agent thu thập xưởng (mặc định xưởng ưa thích/gần nhất), ngày, giờ; hạng mục lấy từ mốc đến hạn.
- **Quy tắc sức chứa:** trong một khung giờ, số booking ở trạng thái `pending | confirmed | checked_in | in_progress` phải nhỏ hơn `total_technicians − emergency_slots_reserved − số chỗ chủ xưởng đã khoá`. Mỗi booking chiếm 1 thợ trong 1 khung giờ (PQ-03). Tính theo thời lượng từng hạng mục là phase sau.
- Chỉ nhận khung giờ nằm trong giờ hoạt động của xưởng (1 khung/ngày theo FEAT-AUTH-003).
- Hết chỗ → đề xuất 2–3 phương án: khung gần nhất cùng xưởng, hoặc xưởng khác cùng khu vực.
- Hiển thị thẻ tóm tắt; **chỉ tạo booking khi chủ xe bấm Xác nhận**.
- Giữ chỗ: booking `pending` với `hold_expires_at` (PQ-02); khoá bằng Redis và kiểm tra lại trong transaction DB. Hết hạn → `cancelled` (EF-001).
- Tool đặt lịch của Agent và API đặt lịch trên UI dùng **chung một service** kiểm tra chỗ trống.

**Acceptance criteria**
- AC-F6-01: 20 request đồng thời vào khung còn 1 chỗ → đúng 1 booking thành công, 19 nhận phương án thay thế.
- AC-F6-02: Không có booking nào được tạo khi chưa có xác nhận của chủ xe.
- AC-F6-03: Booking `pending` quá hạn giữ chỗ tự chuyển `cancelled` và giải phóng chỗ.

### F6b — Booking Ticket, QR, huỷ/đổi

- Ticket gồm mã booking, QR check-in, xưởng, địa chỉ, ngày giờ, hạng mục, chi phí ước tính, giấy tờ cần mang.
- Huỷ → giải phóng chỗ ngay. Đổi lịch → kiểm tra sức chứa khung mới rồi mới giải phóng khung cũ.

### F7 — Nhắc

- **Nhắc mốc bảo dưỡng:** job hằng ngày theo cấp `early / warning / urgent / expired`; tối đa 1 lần/xe/tuần (PQ-04); dừng khi mốc đã có booking. Xe hết bảo hành → bỏ nội dung cảnh báo bảo hành.
- **Nhắc lịch hẹn:** 24h trước giờ hẹn, nút Xác nhận / Đổi / Huỷ.
- **Thời điểm nhắc mốc do chủ xe cấu hình:** mặc định nhắc **trước ngày đến hạn 2 ngày** (đổi được 0–30 ngày, hoặc tắt nhắc). Chi tiết: [us-021 FF](../specs/sprint-2/feature-functional/us-021-sprint-2-spec.ff.md).
- **Kênh: trong app.** Mọi lần nhắc được ghi lại và hiện trong mục **Thông báo** của app (bỏ kết nối Discord ở v3.7). Chủ xe có màn cài đặt kênh; khung cấu hình liệt kê Zalo / Telegram / SMS / Email nhưng MVP chưa có adapter nào, các kênh này hiện "Sắp có". Bật nhắc không bắt buộc chọn kênh ngoài.
- Nội dung nhắc không chứa dữ liệu nhạy cảm: không VIN, SĐT, email, CCCD; biển số che một phần; kèm link mở app.
- Khi có kênh ngoài: gửi thất bại → thử lại theo backoff; vẫn lỗi thì ghi nhận thất bại cho lần nhắc đó, không chuyển sang kênh khác.
- Dùng chung một service gửi thông báo (`NotificationService`) có adapter theo kênh, để phase sau thêm Zalo/Email/SMS/Telegram mà không đổi logic nhắc (NOTI-01).
- Nhắc lịch hẹn 24h (F7) và hỏi thăm sau dịch vụ (F9) cũng hiện trong mục Thông báo.

**Acceptance criteria**
- AC-F7-01: Mọi xe `DUE_SOON` chưa có booking nhận nhắc trong lần chạy job kế tiếp, không quá 1 lần/tuần.
- AC-F7-02: Huỷ từ nhắc 24h giải phóng chỗ ngay lập tức.

### F8 — Workshop Board

- Danh sách booking hôm nay / 7 ngày tới, lọc theo trạng thái.
- Chuyển trạng thái theo state machine: `confirmed → checked_in → in_progress → completed`, hoặc `cancelled`. Check-in bằng quét QR hoặc bấm tay.
- `completed` kích hoạt: cập nhật lịch sử và mốc tiếp theo; lên lịch hỏi thăm (F9).
- Khoá bớt chỗ trong một khung giờ (khách gọi điện, khách vãng lai).
- Chủ xưởng chỉ thấy dữ liệu xưởng mình.

**Acceptance criteria**
- AC-F8-01: Không thể chuyển trạng thái trái state machine (vd. `confirmed → completed`).
- AC-F8-02: Khoá chỗ làm giảm số chỗ còn nhận của khung giờ đó ngay với chủ xe.

### F9 — Hỏi thăm sau dịch vụ

- 12h sau `completed` gửi 1 câu hỏi thăm (Q-412). Phản hồi được phân loại và ghi nhận trên `follow_up` (`has_issue`); không tạo phiếu hỗ trợ (bỏ ở v3.7). Có dấu hiệu an toàn → hiện lời khuyên dừng xe và số hotline xưởng.
- Mỗi booking tối đa 1 follow-up (BR-006).

---

## 7. Nguyên tắc kiểm soát AI

| Nguyên tắc | Quy tắc |
| --- | --- |
| Official-source first | Thông tin kỹ thuật/bảo hành chỉ từ tài liệu chính hãng đã ingest, có trích dẫn. |
| No source = no claim | Không tìm thấy nguồn đủ liên quan → không khẳng định, chuyển xưởng. |
| Deterministic rules | Trạng thái đến hạn, giá, sức chứa, tạo booking do backend/tool xử lý. LLM chỉ gọi tool và diễn giải. |
| Confirm before side effect | Không tạo booking, huỷ lịch khi chưa có xác nhận rõ của người dùng. |
| Estimate label | Mọi con số chi phí gắn nhãn "ước tính". |
| Privacy | Chủ xe chỉ thấy dữ liệu của mình; chủ xưởng chỉ thấy dữ liệu xưởng mình. Không đưa CCCD/VIN vào prompt khi không cần. |
| Escalation | Tranh chấp bảo hành, yêu cầu đặc biệt → AI thừa nhận giới hạn và chuyển xưởng kèm tóm tắt ngữ cảnh. |

---

## 8. Yêu cầu phi chức năng

| Nhóm | Yêu cầu |
| --- | --- |
| Hiệu năng | Chat streaming: token đầu ≤ 1,5 s (p50); trả lời đầy đủ ≤ 8 s (p90). API nghiệp vụ ≤ 500 ms (p90). Tải 50 tin nhắn gần nhất ≤ 300 ms (p90). |
| Tính đúng | Kiểm tra sức chứa và tạo booking là nguyên tử; DB có ràng buộc chống vượt sức chứa. |
| Bảo mật | Mọi API xác minh Firebase ID token; phân quyền theo chủ sở hữu dữ liệu; secret qua biến môi trường. |
| Riêng tư | Chỉ lưu dữ liệu cần cho tính năng; audit đăng nhập/đăng xuất lưu 60 ngày (FEAT-AUTH-002/004); lịch sử chat lưu theo PQ-09 và xoá được theo yêu cầu chủ xe. |
| Quan sát | Log có trace id cho mỗi phiên chat và tool call; lưu nguồn trích dẫn của từng câu trả lời. |
| Chi phí | Ưu tiên free tier; rate limit chat theo người dùng; cảnh báo chi tiêu LLM. |
| Khả dụng | Pilot trên staging; không cam kết SLA. |
| Ngôn ngữ | Tiếng Việt; đơn vị km, VNĐ, múi giờ Asia/Ho_Chi_Minh (lưu UTC). |

---

## 9. Kiến trúc & công nghệ

| Thành phần | Lựa chọn | Vai trò |
| --- | --- | --- |
| Auth | Firebase Authentication (Google) | Cấp ID token; backend verify bằng Firebase Admin SDK. Firebase **chỉ** dùng cho auth. |
| Backend | FastAPI + LangGraph | API nghiệp vụ và Agent (intent → tool → xác nhận → phản hồi). |
| Database | Supabase PostgreSQL | Toàn bộ dữ liệu nghiệp vụ theo `core.entity.md`; migration Alembic. |
| Lưu hội thoại | Supabase PostgreSQL (`conversation`, `chat_message`) + LangGraph Postgres checkpointer | Lưu và truy vấn tin nhắn chat, trạng thái Agent. Firestore là phương án đã cân nhắc — xem 9.1. |
| Realtime | SSE từ FastAPI | Stream câu trả lời của trợ lý. Supabase Realtime chỉ cân nhắc cho cập nhật trực tiếp trên Workshop Board (phase sau) — xem 9.1. |
| Vector | Supabase pgvector | `document_chunk.embedding vector(1024)`, index HNSW — **nguồn duy nhất cho RAG lúc chạy**. |
| Vector (thử nghiệm) | ChromaDB | Chỉ dùng thử chiến lược chunking/eval offline. |
| File | Supabase Storage | PDF tài liệu chính hãng (nguồn ingest). |
| Thông báo | Feed trong app (MVP) | Nhắc mốc, nhắc lịch hẹn, hỏi thăm hiện trong mục Thông báo. Zalo/Email/SMS/Telegram ở phase sau qua adapter của `NotificationService` (NOTI-01). |
| Cache / queue | Redis | Khoá giữ chỗ (TTL = thời gian giữ), rate limit, hàng đợi job: đồng bộ ODO/lịch sử dịch vụ từ hãng, nhắc mốc, nhắc 24h, follow-up, thu hồi token. |
| Frontend | Next.js + Tailwind | Web App chủ xe (mobile-first), Workshop Portal (desktop-first). |
| Đóng gói | Docker / docker-compose | backend, worker, redis; Postgres/Storage dùng Supabase. |
| LLM | Gemini Flash-tier đang được hỗ trợ — chốt ở Tech Spec | Function calling tiếng Việt. |
| Embedding | `bge-m3` (1024 chiều, đa ngôn ngữ) | Khớp `vector(1024)` (Q-408). |

**Tích hợp:** hệ thống hãng mock (`Owner`, `Vehicle`, `VehicleModel`, `VehicleUsage`, `ServiceCenter`, `ServiceHistory`) — dùng cho xác thực, ODO, lịch sử dịch vụ, thông tin xưởng. ODO (`VehicleUsage`) và lịch sử dịch vụ (`ServiceHistory`) được đồng bộ về EV Care bằng job định kỳ (Redis queue) và webhook của hãng; hãng là nguồn duy nhất của ODO.

### 9.1 Quyết định: nơi lưu tin nhắn chat (ADR-01)

**Trạng thái:** Đề xuất — chờ PO và Tech Lead chốt.

**Bối cảnh:** Chat là hội thoại 1-1 giữa chủ xe và AI. Backend sinh câu trả lời, gọi tool và ghi dữ liệu nghiệp vụ. Client không ghi tin nhắn trực tiếp. Các bảng Supabase hiện chặn truy cập bằng anon key (không có policy), nên mọi truy cập đi qua backend.

**Các phương án:**

| Tiêu chí | A. Supabase PostgreSQL (+ Realtime khi cần) | B. Firestore |
| --- | --- | --- |
| Truy vấn cần có (F4) | SQL: join với `user_vehicle`, `booking`; full-text search; tổng hợp cho eval | Truy vấn theo 1 collection; không join; tìm từ khoá cần dịch vụ ngoài; tổng hợp hạn chế |
| Truy ngược booking ↔ tin nhắn (AC-F4-06) | FK và cùng transaction với booking | Hai database, không có transaction chung; phải tự đồng bộ |
| LangGraph checkpoint | Có checkpointer Postgres chính thức | Không có checkpointer chính thức; phải tự viết hoặc dùng thư viện cộng đồng |
| Realtime | Không cần cho chat (đã có SSE). Supabase Realtime dùng được cho Board nếu cần | Mạnh nhất ở realtime + offline trên client — nhưng chat này không cần client tự đồng bộ |
| Auth / phân quyền | Backend kiểm tra Firebase token như mọi API khác | Security Rules dùng Firebase UID trực tiếp; nhưng phải ánh xạ UID sang `user_id`/`workshop_id` của Postgres → logic phân quyền nằm ở 2 nơi |
| Xoá dữ liệu theo yêu cầu | Một chỗ, một transaction | Hai hệ thống phải xoá đồng bộ |
| Chi phí | Nằm trong quota Supabase đang dùng | Tính theo số lượt đọc/ghi document; tải lại lịch sử chat tốn nhiều lượt đọc |
| Vận hành cho team 4 người | Không thêm hệ thống mới | Thêm một database, SDK, emulator khi test, cách backup riêng |

**Quyết định đề xuất:** **Phương án A** — lưu tin nhắn trong Supabase PostgreSQL; stream bằng SSE; không dùng Supabase Realtime cho chat trong MVP.

**Khi nào xem lại Firestore:** có chat người–người thời gian thực (chủ xe ↔ chủ xưởng) cần đồng bộ nhiều thiết bị và chạy offline, hoặc làm app mobile native. Lúc đó cũng cần so sánh lại với Supabase Realtime (Broadcast/Postgres Changes, xác thực bằng Firebase qua Third-Party Auth của Supabase).

---

## 10. Chỉ số thành công

Đo trong điều kiện thật của dự án: hệ thống hãng mock, 3–5 xưởng mock, người thử dùng tài khoản dựng sẵn.

| Nhóm | Chỉ số | Mục tiêu | Cách đo |
| --- | --- | --- | --- |
| Luồng | Luồng xuyên suốt chạy end-to-end | 100% bước ở Demo 2 | Kịch bản demo + e2e test |
| RAG | Độ đúng câu trả lời | ≥ 90% | Bộ eval ≥ 60 câu có đáp án chuẩn |
| RAG | Trích dẫn cho câu kỹ thuật | 100% | Eval tự động |
| RAG | Từ chối đúng khi ngoài nguồn | ≥ 95% | ≥ 15 câu "bẫy" trong eval |
| Giá | Dự toán khớp công thức | 100% | Unit test tool giá |
| NLU | Trích xuất đúng xưởng/ngày/giờ | ≥ 90% | Bộ eval ≥ 50 câu đặt lịch |
| Booking | Vượt sức chứa | 0 lần | AC-F6-01 |
| Booking | Thời gian từ ý định đến xác nhận (median) | < 2 phút | Log trace |
| Booking | Hoàn tất khi có ý định đặt | ≥ 60% | Log phiên với 15–30 người thử |

**Chuyển sang pilot thật (không đo trong MVP):** số chủ xe thật tham gia, mức giảm thời gian trao đổi của xưởng, tỷ lệ xác nhận có mặt sau nhắc hẹn. Lý do: OEM mock khiến chủ xe thật không xác thực được xe, và chưa có baseline từ xưởng thật.

---

## 11. Kế hoạch phát hành

| Mốc | Thời gian | Nội dung | Tiêu chí hoàn thành |
| --- | --- | --- | --- |
| M3 | 28/09–04/10 | Thiết kế giải pháp | Spec F3, F4, F5 + tool contract + chốt PQ-01…07 |
| M4 — Demo 1 | 05–11/10 | Xác thực → trạng thái đến hạn → RAG → dự toán | AC-F3, AC-F4, AC-F5 đạt |
| M5 | 12–18/10 | Đặt lịch + Board | AC-F6, AC-F8 đạt |
| M6 — Demo 2 | 19–25/10 | Luồng xuyên suốt + nhắc | Chỉ số mục 10 có số liệu |
| M7 — Pilot | 26–30/10 | Deploy staging, runbook | Người thử dùng được |
| M8 | 30/10 | Đánh giá cuối kỳ | Báo cáo + roadmap phase sau |

---

## 12. Rủi ro

| Rủi ro | Mức | Giảm thiểu |
| --- | --- | --- |
| AI bịa thông tin bảo hành/giá | Cao | No-source-no-claim, giá qua tool, eval chạy trong CI |
| Double-booking khi đặt đồng thời | Cao | Redis lock + kiểm tra lại trong transaction + ràng buộc DB |
| Thiếu tài liệu chính hãng để ingest | Cao | Chốt danh sách trước 04/10; thiếu thì giới hạn model hỗ trợ |
| Scope creep | Cao | Bám mục 5; Could chỉ làm khi Must đạt Demo 2 |
| Lịch từ kênh khác không có trong hệ thống | Trung bình | Chủ xưởng khoá chỗ thủ công (F8) |
| Pain point chưa kiểm chứng | Trung bình | Khảo sát theo [surveys.md](../../personal/tungld-03005/surveys.md) trước Demo 2 |

---

## 13. Phụ thuộc & giả định

**Phụ thuộc:** Firebase project; Supabase project (Postgres + pgvector + Storage); hệ thống hãng mock; tài liệu chính hãng dạng PDF; API key LLM.

**Giả định:** 3–5 xưởng mock có đủ `total_technicians`, giờ hoạt động và `service_price`; mỗi model hỗ trợ có đủ `maintenance_rule` theo mốc; người thử truy cập bằng tài khoản Google gắn với chủ xe mock.

---

## 14. Câu hỏi mở

| ID | Câu hỏi | Đề xuất |
| --- | --- | --- |
| PQ-01 | Ngưỡng `DUE_SOON` | 500 km hoặc 14 ngày |
| PQ-02 | Thời gian giữ chỗ | 10 phút |
| PQ-03 | Độ dài một khung giờ đặt lịch | 60 phút |
| PQ-04 | Tần suất nhắc mốc tối đa | 1 lần/xe/tuần |
| PQ-05 | Kênh follow-up; tự đóng khi không phản hồi (Q-413) | Mục Thông báo trong app; tự đóng sau 72h |
| PQ-06 | Tài liệu chính hãng nào ingest, cho model nào | Chốt trước 04/10 |
| PQ-07 | Có thời gian ân hạn (grace period) không, lấy từ tài liệu nào | Không có nguồn thì không đề cập |
| PQ-08 | Đánh số User Story: Charter/workbook dùng US-001…011, spec sprint-1 dùng US-001…016 | Thống nhất theo spec sprint-1, cập nhật workbook |
| PQ-09 | Thời gian lưu lịch sử chat | 180 ngày kể từ tin nhắn cuối của hội thoại; bản ẩn danh cho eval giữ lâu hơn |
| PQ-10 | Chốt ADR-01: nơi lưu tin nhắn chat | Supabase PostgreSQL (mục 9.1) |
| PQ-11 | Discord MVP: gửi vào kênh chung hay kênh riêng từng chủ xe? | **Không còn áp dụng (v3.7):** bỏ kết nối Discord, thông báo hiện trong app. `user_discord_link` (ENT-417) đã xoá. |

---

## 15. Truy vết

| Mục PRD | Tài liệu gốc |
| --- | --- |
| F1 | `docs/specs/sprint-1/feature-functional/us-001`, `us-005` |
| F2 | `docs/specs/sprint-1/feature-functional/us-009`, `us-013` |
| F3 | `docs/specs/sprint-2/feature-functional/us-017`, `api/us-017`, `entity/us-017` |
| F3, F7 | `docs/specs/entity/maintenance/maintenance_rule`, `reminder` |
| F4 | `docs/specs/entity/knowledge/*` |
| F5 | `docs/specs/entity/workshop/service_price` |
| F6, F6b, F8 | `docs/specs/entity/maintenance/booking`, `workshop/workshop` |
| F9 | `docs/specs/entity/crm/follow_up` |
| Mốc, rủi ro | `docs/project/ProjectCharter_EV_Care_MVP.docx` |

---

## Phụ lục A — Các điểm đã sửa so với PRD v1/v2

### A.1 Pain point

| Pain point cũ | Đã sửa |
| --- | --- |
| "Một chủ xe gọi tới 3 trung tâm… kể cả lỗi nhỏ chỉ cần xóa mã lỗi" | Bỏ giai thoại và ví dụ xoá mã lỗi (thuộc sửa chữa, ngoài phạm vi); giữ bản chất khó có lịch, gắn nhãn "Giả định" (PP-02). |
| Cố vấn dịch vụ "6 đầu việc dồn vào một người" (chỉ liệt kê 4), gồm "đuổi theo bộ phận phụ tùng" | Bỏ con số 6 và việc phụ tùng; nêu rõ MVP chỉ giảm tải hỏi đáp + xác nhận lịch; vai trò do chủ xưởng đảm nhận (PP-05). |
| "Overbooking là lỗi phổ biến trong ngành"; v2 hứa "triệt tiêu hoàn toàn" | Bỏ khẳng định không có nguồn và lời hứa tuyệt đối; giới hạn phạm vi vào lịch đặt qua EV Care (PP-06). |
| v2 Case 1: "đi quá bao nhiêu km thì mất bảo hành pin", "grace period" | Không giả định có ân hạn/ngưỡng km; chỉ nói khi tài liệu hãng có (F4, PQ-07). |
| Mất quyền lợi bảo hành khi trễ mốc | Giữ, thêm "theo điều kiện trong chính sách bảo hành của hãng" (PP-01). |
| No-show kèm mục tiêu ≥ 70% xác nhận | Giữ pain point; bỏ mục tiêu khỏi MVP vì xưởng là mock (PP-07, mục 10). |

### A.2 Sản phẩm & kỹ thuật

| # | v1/v2 | `docs/specs` / Charter | v3.1 |
| --- | --- | --- | --- |
| 1 | Đăng nhập SĐT hoặc Google | Chỉ Google qua Firebase; OTP phase sau | Chỉ Google |
| 2 | Chọn model từ dropdown | Khai VIN/biển số, hãng xác thực | Theo spec; ODO chỉ đồng bộ từ hãng (định kỳ / webhook), chủ xe không nhập |
| 3 | Người dùng phụ là Service Advisor | Không có role Advisor (W-11) | Chủ xưởng |
| 4 | v2 không có HITL báo giá | BR-004: chủ xưởng duyệt `quote` | Không làm (bỏ F5b ở v3.7) |
| 5 | Sức chứa theo thợ × thời lượng | `workshop` chỉ có số thợ, slot khẩn cấp | Đếm theo đầu thợ/khung |
| 6 | Mini-board chỉ Check-in/Huỷ | `booking.status` có `in_progress`, `completed` | Board chuyển đủ trạng thái |
| 7 | v2 bỏ follow-up/tiến độ | Entity có `service_progress`, `follow_up` | F9 (không phiếu hỗ trợ), F8b (Could) |
| 8 | DB Firebase; Vector Chroma + FAISS; Terraform, Cloud Run | Supabase Postgres + pgvector | Supabase; Chroma chỉ để thử nghiệm |
| 9 | Embedding `text-embedding-3-small` (1536 chiều) | `vector(1024)` | `bge-m3` |
| 10 | LLM Gemini 1.5 Flash / Gemini-3.5-Flash | — | Flash-tier đang hỗ trợ, chốt ở Tech Spec |
| 11 | Web hoặc Zalo Mini App | Google OAuth trên web | Chỉ web |
| 12 | v1 hỗ trợ nhiều xe | us-001: nhiều xe out-of-scope | 01 xe |
| 13 | v1 Case 2: gửi ảnh lỗi táp-lô | Không có trong spec | Out of scope |
| 14 | 150–200 chủ xe thật trong 4 tuần | OEM mock | 15–30 người thử bằng tài khoản dựng sẵn |

---

## Phụ lục B — Backlog tính năng phase sau

Các tính năng đã thống nhất **không làm trong MVP**, ghi lại để lên kế hoạch sau.

| ID | Tính năng | Hiện trạng MVP | Phạm vi dự kiến | Ghi chú kỹ thuật |
| --- | --- | --- | --- | --- |
| NOTI-01 | **Kênh nhận thông báo ngoài app** | Chỉ feed trong app; màn cài đặt kênh có sẵn, các kênh ngoài "Sắp có" | Chủ xe (và chủ xưởng) tự chọn một hoặc nhiều kênh: **Zalo, Email, SMS, Telegram**; xác minh địa chỉ nhận (OTP email/SMS, `/start` bot Telegram, OA Zalo); bật/tắt theo loại thông báo; kênh dự phòng khi kênh chính lỗi | Cần entity mới lưu kênh + địa chỉ đã xác minh theo người dùng; thêm adapter cho `NotificationService`; mở rộng `reminder_channel_enum`; consent nhận tin (SMS có phí) |

