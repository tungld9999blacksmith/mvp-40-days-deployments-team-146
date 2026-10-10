# Booking grounding — kết quả ngày 08/10/2026

Đã hoàn tất lượt đo development với **Mistral Small 2603**, dataset v2.1/scorer 2.2. Batch Booking đạt **150/150**, nhưng preflight phiên mới FAIL và review còn lỗi; **chưa nghiệm thu production**. [Số liệu](result.json), [80 lượt để review độc lập](session_review.html), [raw model/đáp án giao ở phiên mới](live_grounding_examples.json).

| Phần | Kết quả | Giới hạn |
|---|---|---|
| Booking 50 × 3 | 50/50, 50/50, 50/50; 0 provider errors/safety violations | Gate cấu trúc, không phải accuracy semantic |
| Trước/sau tạm dừng | 95 ca cũ + 5 cuối lượt 2 + 50 lượt 3 | Có khoảng dừng; raw repeat mới=1 ánh xạ thành 2/3, giữ source/config và [provenance](repeat_provenance.json) |
| Preflight ban đầu | 3/3 | Đã chạy trước tạm dừng |
| Preflight trước phiên mới | BOOK-03 0/1; 0 lỗi API | Không gọi tool, nhầm thứ Bảy 11/10 thay vì 10/10; [trace](session_preflight_followup.json) |
| 20 phiên / 80 lượt | 0 lỗi thực thi; 20/20 write safety | Task success cần review; còn lỗi nội dung ở lượt 4 |
| Fact audit hẹp | 68 kiểm tra cấu trúc đạt | ID đọc, số slot, thẻ proposal; không kiểm định ý định ngày hoặc toàn bộ semantics |
| Regression source Agent | 380 pass, 5 skip; ruff đạt | [XML trước sửa fixture staging](final_regression_02.xml); không cộng trùng với tests staging |
| Staging synthetic | Migration đạt; 2/2 persistence; 3 process propose/confirm/replay đạt | Không phải HTTP/Firebase/browser hoặc restart toàn bộ backend worker |
| Kết quả cũ | 792 file trước đợt giữ nguyên | Run bị ngắt và các run đã đóng cũng kiểm hash; [preservation](preservation.json) |

Runtime dựng lại **36/150** đáp án Booking và **26/80** lượt phiên. SESSION-01 lượt 3: model vẫn nói 24 khung, đáp án giao đếm đúng 23 từ tool. Lượt 4: model vẫn hứa thông báo/email và dựng markup; đáp án giao chỉ nêu thẻ thật, chưa đặt/giữ chỗ. Đây là thành quả của Agent **model + runtime**, không chứng minh bản thân Mistral hết lỗi. Có **9 ca raw argument format errors** dù gate cuối PASS. Binding ID đọc từ user không kích hoạt trong các run live mới này; test có trace cũ sai UUID, không quy thành hiệu quả live đã đo.

60 lượt đầu được đọc theo ba nhóm đáp án trùng nhau sau chuẩn hóa UUID và đối chiếu facts từng phiên; 20 lượt cuối được đọc riêng. [Codex draft](session_draft_review.json) tách khỏi nhãn độc lập đang trống. Sáu lượt bị đánh dấu fail, một lượt unsure trong draft, **không dùng các nhãn này tính điểm nghiệm thu**:

- SESSION-04: gợi ý 14:30 không có trong danh sách giờ tròn.
- SESSION-06: đổi xưởng nhưng tra hôm nay 07/10 thay vì giữ ngày 10/10 trong hội thoại; renderer đúng tool vẫn trả sai ý định ngày.
- SESSION-15: RAG fixture không có evidence nhưng tự thêm tên/hotline hỗ trợ. Chưa xác minh hotline ngoài đời; vấn đề là output thiếu nguồn trong trace.
- SESSION-17: khẳng định không thấy slot ngày hôm qua dù không tra ngày đó.
- SESSION-18: nói mọi lịch chỉ ghi nhận sau xưởng xác nhận; không phân biệt AUTO/MANUAL.
- SESSION-19: hứa thẻ biến mất và tự nói Agent có thể hủy lịch cũ dù không có tool cancel booking.
- SESSION-14 unsure: từ chối giữ slot chưa tra là đúng, nhưng gợi ý lại ngày cũ khi người dùng muốn ngày khác.

[Mẫu và dữ liệu tool](session_followup_samples.json) giữ nguyên câu giao để reviewer kiểm tra. Các lỗi này và BOOK-03 cần xử lý ở revision/run mới; không sửa output hoặc verdict cũ. Fixture RAG chỉ đo orchestration, chưa chạy lại retrieval/Qdrant.

Staging dùng PostgreSQL/pgvector localhost:35432 và Redis localhost:36379 riêng. Alembic lên `e7a9c2b4d6f8`, 47 bảng, vector/unaccent. Fixture schema ban đầu thiếu helper `immutable_unaccent`; đã bổ sung wrapper trong schema riêng với extension được qualify, không thêm public vào search_path. XML/log lỗi giữ nguyên. Standalone seed ban đầu thiếu các trường xưởng theo migration; hai source/receipt lỗi được giữ, bản cuối seed hợp lệ không tắt constraint. Ba PID khác nhau dùng schema đã migration, real MessageService và Redis: trước confirm 0 booking/1 proposal/1 message, sau confirm 1 booking/2 messages, replay cùng booking ID và vẫn 2 messages. [Bằng chứng](staging_result.json). Hai container thử nghiệm đã dừng, giữ dữ liệu; app hiện có không bị đổi/dừng. Không gọi LLM hoặc gửi email ở staging.

Latency Booking trung bình **3.0713 giây/ca**; chưa đo TTFT/browser. Receipt cost: batch **0.128920407 USD**, phiên **0.067551462 USD** từ 152 AI IDs duy nhất, hai preflight **0.004833576/0.000529683 USD**, tổng đợt **0.201835128 USD**. Đây là receipt đã ghi, không xác nhận tổng hóa đơn của request bị ngắt lúc pause. Routing ưu tiên `mistral/us,mistral/eu`, fallback bật; actual region chưa ghi nhận.

Bước tiếp theo: xử lý grounding ngày/ý định và claim ngoài tool ở các mẫu trên, source queue RAG; review/adjudicate độc lập rồi khóa holdout. Shortlist 2–3 model ×3, HTTP/UI/TTFT/concurrency và pilot 15–30 người chưa hoàn tất. Giữ Mistral, embedding Gemini, `.env` và Qdrant; GPT-4o write chưa bật. Không triển khai production hoặc tái tạo báo cáo mentor.
