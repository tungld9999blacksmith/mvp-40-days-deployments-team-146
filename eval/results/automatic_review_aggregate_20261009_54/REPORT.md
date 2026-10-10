# Kết quả sửa Agent và đánh giá tự động — 09/10/2026

Judge `google/gemini-3.5-flash-lite` chấm component trên 60 đáp án lưu ở revision49. Runner tính overall/citation_support theo quy tắc cố định; hai trường này không được model sinh nên không sửa output model. Raw component/trace lưu nguyên vẹn. Không gọi lại Agent/RAG hoặc thay model production.

| Agent | Attempted/30 | PASS | FAIL | Chưa xác minh | ERROR |
| --- | ---: | ---: | ---: | ---: | ---: |
| Mistral | 30/30 | 25 | 2 | 3 | 0 |
| Gemma | 30/30 | 25 | 1 | 4 | 0 |

Nhãn tự động chưa hiệu chuẩn với người chấm; source authority không được chứng nhận. UNVERIFIABLE giữ trong mẫu số. Không cộng pilot vào full accuracy. Protocol mới khác47/52/53 nên không quy toàn bộ thay đổi điểm cho runtime. Với nhận định RAG thực tế mà không trả citation cho client, citation metric FAIL dù factual metric có thể PASS; xem flagged_cases để tách lỗi nội dung và thiếu citation.

Judge54 pilot+full: **0.157322370 USD**, 0 receipt mới thiếu. Đợt sửa/chạy tiếp48–54: **0.284533698 USD** receipt đã biết, gồm các lượt lỗi; **22 embedding calls chưa có receipt**. Tổng judge lịch sử có receipt **0.549382090 USD**, còn **4** receipt lịch sử thiếu. Không phải hóa đơn toàn dự án.

Hai full runtime đã đạt 30/30 kỹ thuật/regression, booking8/8 mỗi cấu hình. COST06 giải thích nguồn giá; RAG056 trích các bước có nguồn và giữ cảnh báo; GUARD07 từ chối thiếu nguồn không thêm số. 66 kiểm tra offline,144 booking/API (1skip),32 frontend logic PASS theo phạm vi riêng.

Giữ Mistral Agent/Rewrite/generation; Write inactive, không GPT-4o. Gemma giảm50,50% receipt LLM full pipeline nhưng TB2,10 lần Mistral. p90 Mistral8,773s/Gemma16,959s đều vượt mục tiêu8s. Chưa nghiệm thu production: còn nguồn chuẩn/holdout độc lập×3, staging PostgreSQL/Redis và browser/Firebase/UI. Docker daemon chưa sẵn sàng; thiếu EVAL_DATABASE_URL/EVAL_REDIS_URL, không thay bằng DB production.

Corpus/dataset/golden/test_agents/kết quả cũ/.env được bảo vệ và kiểm hash. Không ghi human_review, không email thật hoặc ghi DB production. Full dừng theo receipt0,25USD; pilot cũ và output lỗi giữ nguyên.
