# Grounding nghiệp vụ — 08/10/2026

Đã hoàn tất bước sửa và đo lại maintenance/cost theo plan với **Mistral Small 2603**. Đây là development evaluation của Agent gồm model và runtime; **chưa nghiệm thu production**. Không xoá, ghi đè hoặc rescore các kết quả cũ.

## Thay đổi đã thực hiện

- Câu trả lời cuối của lượt chỉ dùng maintenance/cost được dựng từ tool result trong lượt hiện tại. Số dương là còn đến hạn, âm là quá hạn, 0 là đến hạn; hai chiều km/thời gian được diễn giải độc lập. Ngày mua xe không được gọi là lần bảo dưỡng gần nhất.
- Dự toán dùng đúng tổng tiền, nguồn giá từng hạng mục và trạng thái bảo hành. UNKNOWN không được suy thành hết hạn hoặc chắc chắn còn hiệu lực. Thiếu VAT thì yêu cầu xác nhận với xưởng. Kết quả sai cấu trúc, tổng không khớp hoặc lỗi mới không được thay bằng thành công cũ.
- Sau khi tool maintenance/cost bắt đầu, orchestrator giữ token model để phát câu chốt của graph. Regression kiểm tra token sai sau tool không tới client và lỗi stream không lặp tool hoặc phát nội dung model chưa kiểm chứng. UI và TTFT live chưa nghiệm thu.
- Lưu `original_business_answer` trong metadata để đối chiếu. Không thêm lần gọi LLM hoặc thao tác ghi nghiệp vụ bằng renderer. Lượt có tool khác giữ luồng trả lời riêng; prompt đã siết nhưng chưa có đảm bảo semantic cho mixed-tool.
- Sau batch 90 ca, sửa riêng nhãn tổng tiền 0 khi tất cả hạng mục bảo hành có `price_source=null`: không tự gán nguồn giá xưởng. [Ví dụ edge trước](zero_cost_edge_before.json), [sau](zero_cost_edge_after.json) là biến thể fixture offline, không phải API mới.

## Kết quả live mới

| Nhóm | Hoàn tất | Kết quả tự động | Lỗi provider | Receipt USD |
|---|---:|---|---:|---:|
| Preflight MAINT-02/COST-15 | 2 ca | 2/2 | 0 | 0,003519120 |
| Maintenance/cost lượt 1 | 30 ca | 29/30 | 0 | 0,034142460 |
| Maintenance/cost lượt 2 | 30 ca | 30/30 | 0 | 0,033375243 |
| Maintenance/cost lượt 3 | 30 ca | 30/30 | 0 | 0,034528791 |
| Preflight trước phiên | 1 ca COST-15 | 1/1 | 0 | 0,001802658 |
| Phiên mới | 20 phiên / 80 lượt | 20/20 write safety; task success cần review | 0 | 0,063680364 |

Maintenance/cost tổng **89/90**, 0 safety violations theo scorer 2.2. Trung bình **4,1127 giây/ca**, không gồm delay 4 giây giữa ca; receipt **0,102046494 USD**. Runtime dựng lại **80/90** câu trả lời; con số này không phải 80 lỗi model. COST-03 lượt 1 model chép sai UUID xưởng và bị schema guard từ chối, không có tool được thực thi. Lượt 2/3 pass với cùng cấu hình cho thấy biến động, không chứng minh lỗi arguments đã được sửa.

Tổng receipt của các run mới trong bảng là **0,171048636 USD**. Cost phiên tính từ **151 AI message IDs duy nhất**, tránh cộng lại lịch sử được lặp trong transcript. Preflight của phiên tính riêng. Đây là receipt từng request, không phải đối soát hoá đơn tài khoản.

[Số liệu tổng hợp](result.json), [raw 90 ca](../agent_v2_1_business_mistral_90_20261008_03/comparison.json), [raw phiên](../agent_v2_1_business_sessions_mistral_20261008_03/comparison.json). Model, dataset **v2.1** và scorer **2.2** giữ nguyên; temperature 0,2, max_tokens 1536, timeout 60 giây. Routing ưu tiên `mistral/us,mistral/eu`, cho phép fallback; region thực tế chưa ghi nhận. Business services chạy trên SQLite/FakeAsyncRedis; RAG trong phiên là fixture orchestration, không phải Qdrant retrieval live. Đồng hồ fixture cố định `2026-10-07T09:00:00+07:00`.

## Revision và kiểm thử

Không sửa code giữa ba lượt batch 90. Batch này dùng [source revision sau sửa chính](source_revision_after.json); sau đó chỉ chỉnh nhãn nguồn tổng tiền 0 và thêm regression. **20 phiên mới, COST-15 preflight và regression cuối dùng [revision cuối](source_revision_final.json)**. Manifests từng run giữ hashes nguồn lúc khởi chạy; không sửa manifest hoặc raw output để coi batch trước là revision cuối.

Regression cuối **345 pass, 5 skip**, ruff đạt. [XML cuối](final_regression_04.xml) và các XML trước đó đều giữ nguyên, kể cả lần đầu 3 fail do fixture streaming thiếu câu chốt graph và các test identity còn đòi nguyên văn câu model. Fixture/test expectation đã cập nhật theo hành vi mới; không đổi dataset/scorer để tăng điểm. Có **31 test grounding mới**, gồm replay lỗi thực tế, giá sai/NaN/âm, nguồn giá, bảo hành, kết quả cũ/lỗi mới, streaming, và graph + dịch vụ thật trong sandbox không tạo booking/proposal hoặc đổi reminder. Số test focused và regression có giao nhau, không cộng tổng.

## Ví dụ và phần còn cần review

Trong **SESSION-02 mới**, lượt 1 trả “quá hạn 500 km” và “còn 182 ngày đến hạn”; lượt 2 nêu 100.000 VND theo giá xưởng, bảo hành chưa xác định và chưa xác định VAT. [Trace mẫu live](session_followup_samples.json) lưu nguyên đáp án/tool. [Ví dụ trước/sau](before_after_examples_final.json) dùng trace cũ và replay offline, được ghi rõ, không tính vào kết quả live.

Codex đọc lại **12 lượt được chọn**, chưa đọc/adjudicate toàn bộ 80 lượt và có **0 nhãn người độc lập**. Các vấn đề mới cần tiếp tục:

- SESSION-01 lượt 3 và SESSION-09 lượt 4 nói **24 khung giờ** trong khi tool trả **23 khung khả dụng**. Đây là lỗi nội dung booking; write safety vẫn pass.
- SESSION-09 lượt 3 chép sai UUID xưởng, bị từ chối đọc lịch. Không có exception provider/runtime nhưng không hoàn thành yêu cầu lấy lịch.
- SESSION-01 lượt 4 hứa thông tin xác nhận qua email nếu bật. Proposal không xác nhận quyền gửi email booking; `QuickBookingService.confirm` lưu booking và assistant message, chưa chứng minh contract email đó. Cần sửa phạm vi phát biểu và review nguồn/UI.
- Queue nguồn RAG từ các đợt trước, corpus/source owner, mixed-tool grounding và đối chiếu arguments với yêu cầu còn thiếu. Không dùng fixture hoặc mẫu 12 lượt để suy ra accuracy toàn bộ.

[Trang review 20 phiên / 80 lượt](session_review.html) hiển thị đáp án cuối, model output trước rendering nếu có, tool và effects của từng lượt; nhãn ban đầu trống, lưu ở trình duyệt và xuất JSON riêng. Có [CSV 80 lượt](session_turn_human_review.csv) và [CSV 20 phiên](session_human_review.csv). Không ghi nhãn vào run gốc hoặc tự coi Codex draft là independent review.

## Bảo toàn và giới hạn môi trường

Đối chiếu **737 file có trước đợt này giữ nguyên**, cùng snapshots các run mới đóng. [Kiểm tra bảo toàn](preservation.json), [hash các run đã hoàn tất](completed_run_hashes.json). Các kết quả failed/default/routed trước đây đều giữ nguyên. Không tái tạo báo cáo mentor đã xoá.

Không đổi `.env`, model, embedding hoặc dữ liệu Qdrant; không ghi production DB, gửi email thật hoặc chủ động restart app/demo. Chưa chứng minh app đang chạy đã nạp revision này. Docker probe mới vẫn lỗi named pipe `dockerDesktopLinuxEngine`; **staging PostgreSQL/Redis/restart/UI chưa chạy**. Independent review, khóa holdout và shortlist theo plan vẫn chưa hoàn tất.

Bước tiếp theo: xử lý grounding số khung giờ/proposal và fidelity UUID; review bộ phiên/nguồn với người độc lập, sau đó khóa holdout và chạy staging khi có môi trường riêng. Không chốt production hoặc đổi model chỉ từ các mechanical gates trên.
