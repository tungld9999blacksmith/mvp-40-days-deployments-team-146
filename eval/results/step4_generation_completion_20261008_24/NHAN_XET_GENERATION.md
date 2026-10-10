# Nhận xét generation — bước 4, 08/10/2026

Hai model dùng cùng 30 câu golden nguyên văn, cùng bằng chứng/prompt/schema, 3.000 token/temperature 0,1. Giữ Mistral baseline trong ứng dụng. Pilot 6 câu/model được ghi riêng; không cộng pilot thành 36 câu độc lập.

| Model | Hoàn tất | Raw JSON/provider calls | Runtime gate trước provider | Lỗi full được chọn | Provider TB (giây) | Receipt full (USD) |
| --- | --- | --- | --- | --- | --- | ---: |
| mistralai/mistral-small-2603 | 30/30 | 25/25 | 5 | 0 | 1.870 | 0.013030908 |
| google/gemma-4-26b-a4b-it | 30/30 | 25/25 | 5 | 0 | 3.992 | 0.010831068 |

Gemma receipt full thấp hơn Mistral **16.9%**, provider latency TB bằng **2.13 lần** Mistral trong các full run được chọn. Routing/cache/tải provider chưa kiểm soát; chưa chứng minh lợi ích ổn định hoặc độ đúng nội dung. Xem `generation_decision.json` và `shortlist_by_stage.json` trước khi coi model đủ điều kiện kỹ thuật.

Lượt Mistral gốc bị ngắt do lỗi kết nối OpenRouter ở G03, **23/30 attempted, 22 technical PASS**, **17 JSON hợp lệ/17 phản hồi thành công**, 1 request lỗi kết nối chưa có receipt. Giữ nguyên run/trace/verdict cũ; chạy mới toàn bộ 30 câu trên cùng revision, không ghép 22 câu cũ với phần chạy bù. Các lỗi gốc nằm trong manifest và master trước.

Tổng receipt generation đã biết cho pilot +mọi full attempts: **0.038296139 USD**, còn **1 receipt thiếu**, nên chưa chứng nhận hóa đơn đầy đủ nếu còn thiếu. Không retrieval/embedding, không gọi GPT-4o/Write/model thứ tư, không sửa `.env`, corpus, golden/dataset hoặc kết quả cũ.

Runtime gates không phải đáp án model tự sinh. Citation identity/tag/range không chứng minh claim support. `runtime_and_raw_audit.json` giữ raw output, scope/conflict repair và fallback riêng. Review người dùng vẫn tạm hoãn, 0 nhãn độc lập; chất lượng nội dung chưa đánh giá. Holdout ×3, cấu hình ghép và integration/UI còn trong plan; chưa nghiệm thu production.

Nếu các full run qua gate kỹ thuật, bước tiếp là thu hẹp ứng viên theo vai trò và khóa cấu hình ghép development; giữ Mistral nếu chưa có bằng chứng chất lượng tương ứng. Không đổi model chỉ từ raw JSON hoặc giá token. Mọi run trước vẫn được bảo toàn qua hashes.
