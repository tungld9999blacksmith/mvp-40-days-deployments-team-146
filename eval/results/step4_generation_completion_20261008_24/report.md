# Bước 4 — generation Mistral/Gemma, 08/10/2026

Đã sửa duy nhất phần hướng dẫn định dạng JSON trong prompt generation; parser/schema/các gate nguồn giữ nguyên. Gemma M01 cũ đã có request JSON schema nhưng vẫn trả Markdown; giữ nguyên run/verdict cũ, không sửa điểm bằng parser hoặc làm sạch raw output. Revision mới chạy lại cả hai model cùng 6 câu pilot trước khi mở rộng 30 câu/model đủ điều kiện.

30 câu lấy nguyên văn từ golden lịch sử: cùng 24 câu golden ở Rewrite +6 câu golden khác; không thay golden bằng dataset mới, không phải holdout. Evidence 1–5 đoạn/câu lấy từ full RAG đã lưu và khóa hash, không retrieval/embedding mới. Các mốc/chính sách nguồn chưa review giữ nguyên.

| Lượt | Model | Hoàn tất | Raw JSON/provider calls | Runtime xử lý trước provider | Lỗi | Provider TB (giây) | Receipt generation (USD) |
| --- | --- | --- | --- | --- | --- | --- | ---: |
| pilot | mistralai/mistral-small-2603 | 6/6 | 5/5 | 1 | 0 | 2.505 | 0.003042138 |
| full | mistralai/mistral-small-2603 | 30/30 | 25/25 | 5 | 0 | 1.870 | 0.013030908 |
| pilot | google/gemma-4-26b-a4b-it | 6/6 | 5/5 | 1 | 0 | 3.262 | 0.001789916 |
| full | google/gemma-4-26b-a4b-it | 30/30 | 25/25 | 5 | 0 | 3.992 | 0.010831068 |

Tổng receipt các attempt generation mới: **0.028694030 USD**, **0 receipt thiếu**. Provider latency chỉ đo các câu có model call, không gộp thời gian gate thành model latency, không phải TTFT hoặc latency toàn ứng dụng. Không cộng pilot/full cùng câu thành các case độc lập.

Đủ gate kỹ thuật của full không chứng nhận độ đúng nội dung. Citation membership/range/tag chỉ kiểm cấu trúc và danh tính; không chứng minh nguồn hỗ trợ claim. `runtime_and_raw_audit.json` ghi raw JSON, các gate, fallback/scope/conflict repair riêng. Correctness/claim support **chưa đánh giá**, người dùng đang tạm hoãn review, 0 nhãn độc lập.

Giữ Mistral làm baseline ứng dụng; xem số liệu full trước khi đề xuất stage khác. Chưa đổi `.env`, không gọi GPT-4o/Write/model thứ tư, không sửa golden/dataset/corpus hoặc kết quả cũ. Nếu full không đạt thì giữ lỗi và xử lý bằng revision/run mới; chỉ ứng viên đủ điều kiện kỹ thuật mới đi tới thu hẹp/cấu hình ghép. Bước 5 holdout ×3 và integration/UI chưa chạy.

Đã kiểm chứng cùng query/context/evidence/prompt/schema/config và request thực tế. Routing/cache/tải provider chưa được kiểm soát, các lượt là một lần development/model. Prompt cũ khác revision mới nên không dùng chênh lệch với run lịch sử để kết luận model A/B. Preservation/hash ở `final_preservation.json`, `closed_master_hashes.json`, từng producer; nguồn code trước sửa ở `before_generator.py`.
