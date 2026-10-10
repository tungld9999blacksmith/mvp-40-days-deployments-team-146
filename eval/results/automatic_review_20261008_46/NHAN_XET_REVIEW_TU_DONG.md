# Review tự động — đáp án đã lưu

Judge: `google/gemini-3.5-flash-lite`, ẩn model tạo đáp án; phase báo cáo: **pilot**. Không chạy lại Agent/RAG hoặc retrieval/embedding.

| Cấu hình gốc | Selected | Attempted | PASS | FAIL | UNVERIFIABLE | ERROR | Chưa chạy |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Mistral | 6 | 6 | 3 | 1 | 2 | 0 | 0 |
| Gemma | 6 | 6 | 4 | 1 | 1 | 0 | 0 |

Receipt judge đã biết **0.030009600 USD**, **0 receipt thiếu**. Pilot và full ghi riêng; không cộng đáp án trùng thành accuracy.

Pilot kiểm 4 ca kiểm soát: đổi 12.000 thành 120.000 km; báo booking từ proposal; bỏ cảnh báo nguồn chưa xác minh; fallback giữ cảnh báo. Nhãn kiểm soát là dữ liệu thử có chủ đích, không phải nhãn người chấm hoặc chứng minh judge chính xác với mọi tình huống.

Điểm dựa vào nguồn/tool outputs đã lưu. UNVERIFIABLE, lỗi và câu chưa chạy giữ nguyên mẫu số; không xem là PASS hoặc tự loại khỏi báo cáo. Quote/citation validation chỉ kiểm provenance cấu trúc, entailment vẫn do model judge đánh giá.

Không có hiệu chuẩn với người chấm; không xác nhận sự thật của nguồn, holdout độc lập hoặc production readiness. Kết quả human_review.csv, verdict kỹ thuật, dữ liệu/golden/corpus cũ giữ nguyên. Rule/auto-judge verdict nằm ở file riêng; chưa đổi model ứng dụng, không GPT-4o/Write/email thật/.env write.

Revision 46 dùng structured schema theo tập keyword đã probe45 kiểm chứng: type/properties/items/required/enum/additionalProperties. API buộc đúng field và reference enum; đầy đủ cardinality, coverage citation inline và verdict consistency vẫn bắt buộc ở validator local. Schema đầy đủ kèm payload.output_schema; không sửa output hoặc ép verdict. Ref ghép sẵn citation/card, claim nhiều chunk chọn nhiều ref đúng nguồn, quote do runner resolve. RAG tool text không làm bằng chứng gốc; contract booking không chứng minh WRITE. Entailment vẫn do judge, chưa hiệu chuẩn với người chấm.

Pilot fresh4control+12đápán gồmRAG001/007/083,GUARD01,BOOK19,REMINDER03 của hai cấu hình. Không dùng lại control vì API format/payload đổi. Full fresh60 sau gate; không ghép full dở dang/nhãn pilot. Dự toán mean receipt×60+15%, ngưỡng dừng receipt full thực tế0,20USD.

Receipt đã biết toàn bộ attempts **0.179575690 USD**, **4 request không có receipt**, gồm các provider400 trước đó; probe45 riêng 0.000907500 USD. Không coi request bị từ chối là phí0; xem all_attempts_cost.json.
