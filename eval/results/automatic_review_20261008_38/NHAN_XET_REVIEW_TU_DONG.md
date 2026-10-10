# Review tự động — đáp án đã lưu

Judge: `google/gemini-3.5-flash-lite`, ẩn model tạo đáp án; phase báo cáo: **full**. Không chạy lại Agent/RAG hoặc retrieval/embedding.

| Cấu hình gốc | Selected | Attempted | PASS | FAIL | UNVERIFIABLE | ERROR | Chưa chạy |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Mistral | 30 | 6 | 2 | 0 | 3 | 1 | 24 |
| Gemma | 30 | 5 | 1 | 0 | 4 | 0 | 25 |

Receipt judge đã biết **0.044054090 USD**, **0 receipt thiếu**. Pilot và full ghi riêng; không cộng đáp án trùng thành accuracy.

Pilot kiểm 4 ca kiểm soát: đổi 12.000 thành 120.000 km; báo booking từ proposal; bỏ cảnh báo nguồn chưa xác minh; fallback giữ cảnh báo. Nhãn kiểm soát là dữ liệu thử có chủ đích, không phải nhãn người chấm hoặc chứng minh judge chính xác với mọi tình huống.

Điểm dựa vào nguồn/tool outputs đã lưu. UNVERIFIABLE, lỗi và câu chưa chạy giữ nguyên mẫu số; không xem là PASS hoặc tự loại khỏi báo cáo. Quote/citation validation chỉ kiểm provenance cấu trúc, entailment vẫn do model judge đánh giá.

Không có hiệu chuẩn với người chấm; không xác nhận sự thật của nguồn, holdout độc lập hoặc production readiness. Kết quả human_review.csv, verdict kỹ thuật, dữ liệu/golden/corpus cũ giữ nguyên. Rule/auto-judge verdict nằm ở file riêng; chưa đổi model ứng dụng, không GPT-4o/Write/email thật/.env write.

Revision 38 giữ literal evidence cards, ràng buộc citation/chunk và card cho SUPPORTED ở validator local. Schema API field tường minh và card bắt buộc cho claim; hành vi từ chối/chào/mời hỗ trợ được đánh giá ở task_success/reasons. Bổ sung hợp đồng booking trích nguyên văn prompt gốc, chỉ chứng minh quy tắc/capabilities, không chứng minh WRITE đã xảy ra. Payload compact bỏ metadata lặp và dòng trích trùng cùng source, giữ nguyên mọi span/path/role khác nhau; nguồn đầy đủ vẫn lưu nguyên văn. RAG tool text không được làm bằng chứng gốc. Entailment vẫn do judge, chưa hiệu chuẩn với người chấm.

Pilot fresh 4 control +10 đáp án, gồm RAG-001/007, GUARD-01, BOOK-19, REMINDER-03 của hai cấu hình. Protocol/payload mới nên không tái sử dụng verdict hoặc ghép phần full37 vào full38. Kết quả cũ và human_review.csv giữ nguyên.

Tổng receipt gồm mọi pilot/full trước và lượt này: **0.138418790 USD**; xem all_attempts_cost.json.
