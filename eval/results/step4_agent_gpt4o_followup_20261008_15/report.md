# Bước 4 — bổ sung GPT-4o cho Agent, 08/10/2026

Đã chạy preflight, lượt Agent GPT-4o và chạy bù có pacing. Giữ Mistral Small 2603 trong ứng dụng. Đây là sàng lọc kỹ thuật development; review nội dung đang tạm hoãn, 0 nhãn độc lập, chưa nghiệm thu production.

## Kết quả thực tế

| Model / lượt | Selected | Attempted | PASS scorer | Lỗi provider | Latency TB / p90 (giây) | Receipt đã biết (USD) |
| --- | ---: | ---: | ---: | ---: | --- | ---: |
| Mistral Small 2603, lượt cũ giữ nguyên | 30 | 30 | 30 | 0 | 4.130 / 7.518 | 0.029214768 |
| Gemma 4 26B A4B, lượt cũ giữ nguyên | 30 | 30 | 30 | 0 | 8.438 / 13.537 | 0.013019318 |
| GPT-4o, lượt đầu | 30 | 27 | 22 | 5 | 3.115 / 5.818 | 0.358935000, thiếu 4 receipt |
| GPT-4o, chạy bù 8 case | 8 | 8 | 8 | 0 | 4.519 / 9.862 | 0.136320000 |
| GPT-4o, phủ 30 ID qua hai lượt | 30 | 30 | 30 | 0 trong các dòng được chọn | 3.765 / 5.818 | 0.479205000 |

Hàng cuối lấy 22 case PASS lượt đầu và kết quả chạy bù cho 8 ID còn lại. **Không phải một full run 30/30 hoặc lần lặp độc lập.** 5 lỗi 429 của lượt đầu vẫn được giữ và tính vào lịch sử độ ổn định/chi phí. Mean lượt đầu bị kéo xuống bởi các lỗi trả nhanh; không dùng để kết luận GPT-4o nhanh hơn. Pacing 15 giây giữa case chạy bù làm tăng thời gian cả batch; thời gian ngủ không nằm trong latency từng case, không phải latency UI/TTFT.

Preflight BOOK-05: 1/1 PASS, đúng `openai/gpt-4o`, receipt **0.03527000 USD**. Tổng receipt đã biết cho preflight + lượt đầu + chạy bù: **0.530525000 USD**, còn **4 case thiếu receipt**, nên đây là tổng tối thiểu đã quan sát, không phải hóa đơn đầy đủ. Receipt phủ 30 ID loại phần chi phí lần gọi lỗi và preflight; không dùng làm tổng chi phí rollout.

## Lỗi API và cách xử lý

OpenRouter trả `429`, `new-account-rpm/openai/gpt-4o`, `limit_source=openrouter_new_account`: hạn 20 requests/phút cho GPT-4o ở tài khoản này. Một case Agent gọi model nhiều lần, nên nghỉ 1 giây/case không đủ. Đây là lỗi giới hạn request, không phải bằng chứng model trả lời sai hay cần thay key.

- Lượt đầu: BOOK-05, BOOK-15, COST-11, REMINDER-03, REMINDER-05 lỗi 429; REMINDER-10, REMINDER-12, REMINDER-16 chưa chạy sau ngưỡng dừng 3 lỗi liên tiếp.
- Chạy bù 8 ID trong thư mục mới, giữ runtime/prompt/schema/dataset/scorer, chỉ tăng khoảng nghỉ từ 1 lên 15 giây/case. Không retry toàn bộ 30 câu để xóa lịch sử lỗi. Pacing giữa case không bảo đảm giới hạn từng model request cho mọi workload.
- Raw traces và lượt lỗi giữ nguyên. Không ghi đè `result.json`, `model_comparison.csv` hoặc producer cũ; kết quả bổ sung nằm ở `completion_result.json`, `recovery_summary.json`, `stage_comparison.csv`.

## Điều kiện và giới hạn đánh giá

30 ID development giống smoke Mistral/Gemma, gồm 8 Booking, 6 maintenance/cost, 5 reminder, 5 guardrail và 6 RAG. Dùng production graph với services SQLite/FakeRedis riêng; RAG tool là fixture. Token budget 2.048, temperature 0,2, timeout 60 giây, clock cố định, scorer 2.2; public schema và các điều kiện chung khớp. Không đo retrieval hoặc generation thật trong batch Agent này.

Routing Mistral ưu tiên `mistral/us,mistral/eu`, Gemma/GPT-4o tự động. Các run diễn ra tuần tự ở thời điểm khác nhau, UUID fixture khác nhưng cùng vai trò. Không khẳng định toàn bộ Agent requests giống từng byte. 45 kiểm tra offline được tái sử dụng vì source runtime/evaluator không đổi; Ruff các helper mới đạt.

Phủ GPT-4o: 0 safety violations theo detector, 0 case lỗi raw arguments, 0 truncation. Chỉ là kết quả các detector trong phạm vi đã chọn, không chứng nhận mọi câu trả lời đúng hoặc mọi yêu cầu booking an toàn. Audit raw proposal/calls nằm trong `completion_result.json`; runtime chặn/sửa không bị tính là model tự làm đúng. Semantic correctness vẫn `NOT_MEASURED` hoặc `NEEDS_HUMAN_REVIEW` với RAG; các CSV review trống.

## Nhận xét chọn model và bước tiếp

Receipt phủ 30 ID của GPT-4o khoảng **16.4 lần Mistral** trong các lượt này, chưa có nhãn độc lập chứng minh lợi ích nội dung tương ứng. Giữ Mistral làm baseline; Gemma là ứng viên giảm chi phí Agent nhưng chậm hơn trong smoke. GPT-4o ở nhóm dự phòng, cần pacing và bằng chứng chất lượng nếu muốn đưa vào shortlist nghiệm thu. `WRITE_MODEL` vẫn inactive.

Tiếp theo mục 7.4 đợt 2: khóa 30 query Rewrite từ bộ golden/v2.1 hiện có, điều kiện và rubric; pilot 3–5 query/model Mistral/Gemma/Gemini Flash Lite, rồi mới mở rộng nếu đạt. Chưa chạy Rewrite, generation GPT-4o, cấu hình ghép hoặc holdout ×3 trong đợt này. Review nguồn/nội dung vẫn tạm hoãn theo yêu cầu người dùng.

Kết quả cũ, dataset, corpus, source runtime và `.env` được kiểm hash trước/sau; xem `final_preservation.json` và file verification bên ngoài thư mục master. Không đổi cấu hình model ứng dụng.
