# Kết quả development regression sau sửa reminder và booking

Ngày09/10/2026. Đã hoàn tất30 câu ×2 cấu hình ×3 lần trên runtime59/evaluator60. Bộ30 đã dùng sửa Agent nên là **development regression**, không phải holdout độc lập.90 quan sát mỗi model là30 câu chạy lặp3 lần.

| Agent | PASS kỹ thuật | Booking | Reminder | TB tác vụ (giây) | p90 gộp (giây) | Receipt LLM3 full (USD) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Mistral Small2603 | 90/90 | 24/24 | 15/15 | 4,9115 | 10,9021 | 0,101690507 |
| Gemma4 26B A4B | 90/90 | 24/24 | 15/15 | 8,3398 | 14,5153 | 0,046710104 |

Mỗi lượt đều30/30. Không ghi nhận safety violation, lỗi raw arguments, provider/retrieval hoặc thiếu receipt LLM trong sáu full. NEW-B04, NEW-N01, NEW-N02 và NEW-N03 đều PASS. **Chưa chấm nội dung/citation cho180 đáp án:0 judge calls**, không suy ra semantic correctness từ technical PASS.

Gemma giảm54,07% receipt LLM nhưng thời gian TB bằng1,70 lần Mistral. p90 từng lượt Mistral11,6273/10,2205/9,6393s; Gemma16,5669/14,5153/13,9375s. Cả hai chưa đạt p90≤8s. Đây là so sánh cấu hình toàn pipeline: Agent có thể đổi query/evidence/số calls dù Rewrite/generation cùng Mistral. Giữ Mistral baseline, chưa đổi `.env` hoặc model production.

Riêng180 quan sát full có receipt **0,148400610USD**. Tổng phạm vi55–61 gồm mọi pilot/lượt dở cũ và full mới là **0,25706310225USD đã biết**; hai dòng chồng phạm vi, không cộng chúng. Mistral repeat1 tái sử dụng từ60, không tính phí/embedding lại. Gemma21 câu bị dừng giữ nguyên ở60, phí vẫn tính nhưng không ghép vào accuracy.69 embedding calls chưa định giá; phí yêu cầu đang chạy lúc dừng60 chưa xác định. Reserve0,01USD chỉ là dự phòng ngân sách, không phải receipt hoặc giới hạn phí đã chứng minh.

Judge inputs180 đã chuẩn bị. Automatic approval review từ chối pilot vì chưa xác định quyền gửi trace/evidence tới `google/gemini-3.5-flash-lite` qua OpenRouter. Người dùng yêu cầu đề xuất, chưa cấp quyền này. Đề xuất tiết kiệm: pilot7 controls +2 đáp án, rồi chấm60 đáp án của repeat1 mỗi model; lấy nguyên30 câu/model, không chọn câu PASS hoặc cherry-pick lượt tốt. Phí judge dự kiến0,16–0,18USD, tổng55–61 khoảng0,417–0,437USD đã biết nếu chạy thành công; chưa gồm embedding/phí đang thiếu. Chấm180 dự kiến0,44–0,46USD, chỉ cần khi muốn kiểm tra nội dung biến động giữa cả ba lượt. Cap chung0,75USD giữ nguyên. Không tự đổi mục tiêu: nếu chỉ chấm60, semantic review×3 vẫn chưa hoàn tất.

Các producer đã đóng và kiểm hash. Source/config/dataset/corpus/test_agents/kết quả cũ được bảo toàn; ba file pilot Gemma57 lệch seal cũ đã đối soát ở58, không giả lập phục hồi hoặc sửa seal57. Không GPT-4o, email thật, DB production hoặc restart backend/frontend. Holdout độc lập/source truth/staging/UI và nghiệm thu production còn thiếu.

Chi tiết: [so sánh kỹ thuật](technical_comparison.json), [kiểm tra bảo toàn](technical_completion_verification.json), [manifest](manifest.json), [provenance Mistral](reused_producer_provenance.json).
