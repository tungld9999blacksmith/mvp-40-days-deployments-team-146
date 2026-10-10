# Kết quả đánh giá Agent / RAG

Các run ngày 07/10/2026 dùng dataset development; chưa phải nghiệm thu production. Kết quả lịch sử giữ nguyên.

## Kết quả chính sau cập nhật OpenRouter

- [Báo cáo tổng hợp](implementation_20261007_122213_010409/report.md): Booking Mistral 49/50; cùng 10 câu trước/sau 6/10 → 10/10; các nhóm business, sessions, full RAG và giới hạn phép chấm.
- [Booking 50 câu](agent_v2_booking_50_mistral_routed_improved_20261007_01/report.md) · [baseline 10 câu](agent_v2_booking_10_mistral_routed_baseline_20261007_01/report.md) · [business + sessions](agent_v2_business_sessions_mistral_routed_20261007_01/report.md).
- [Full RAG 100 câu](rag_v2_full_100_mistral_routed_20261007_01/report.md) · [ví dụ câu trả lời](implementation_20261007_122213_010409/rag_answer_examples.md) · [review CSV](rag_v2_full_100_mistral_routed_20261007_01/human_review.csv).
- [Bảo toàn 32 artifact cũ](implementation_20261007_122213_010409/preservation.json) · [JUnit cuối](implementation_20261007_122213_010409/final_agent_booking_conversation_03.xml) · [Sửa lỗi ok tự chọn giờ](agent_v2_session03_mistral_fixed_20261007_01/report.md).

## Lịch sử và run dùng chẩn đoán

Bảng 10 model cũ: [benchmark report](../../backend/tests/test_agents/evaluationLLM/results/benchmark_report.md). Contract/scorer cũ khác runtime hiện tại; không xếp hạng chung với các run v2. [Rà soát Booking](booking_review_20261007_121335_fe5d12/report.md). `report.md` lịch sử tại thư mục này vẫn giữ nguyên.

| Run | Trạng thái artifact |
|---|---|
| [agent_v2_booking_10_mistral_routed_baseline_20261007_01](agent_v2_booking_10_mistral_routed_baseline_20261007_01/report.md) | Run chính; review nội dung chưa hoàn tất |
| [agent_v2_booking_50_mistral_retry_20261007_01](agent_v2_booking_50_mistral_retry_20261007_01/report.md) | Completed artifacts; xem errors/complete trong báo cáo, không mặc định là PASS |
| [agent_v2_booking_50_mistral_routed_improved_20261007_01](agent_v2_booking_50_mistral_routed_improved_20261007_01/report.md) | Run chính; review nội dung chưa hoàn tất |
| [agent_v2_booking_50_shortlist_20261007_01](agent_v2_booking_50_shortlist_20261007_01/report.md) | Completed artifacts; xem errors/complete trong báo cáo, không mặc định là PASS |
| [agent_v2_booking_mistral_baseline_20261007_01](agent_v2_booking_mistral_baseline_20261007_01/report.md) | Completed artifacts; xem errors/complete trong báo cáo, không mặc định là PASS |
| [agent_v2_booking_mistral_improved_20261007_01](agent_v2_booking_mistral_improved_20261007_01/report.md) | Completed artifacts; xem errors/complete trong báo cáo, không mặc định là PASS |
| [agent_v2_booking_shortlist_baseline_20261007_01](agent_v2_booking_shortlist_baseline_20261007_01/report.md) | Completed artifacts; xem errors/complete trong báo cáo, không mặc định là PASS |
| [agent_v2_booking_shortlist_improved_20261007_01](agent_v2_booking_shortlist_improved_20261007_01/manifest.json) | Incomplete/interrupted; không dùng làm kết quả chất lượng |
| [agent_v2_booking_shortlist_improved_20261007_02](agent_v2_booking_shortlist_improved_20261007_02/report.md) | Completed artifacts; xem errors/complete trong báo cáo, không mặc định là PASS |
| [agent_v2_business_sessions_mistral_routed_20261007_01](agent_v2_business_sessions_mistral_routed_20261007_01/report.md) | Run chính; review nội dung chưa hoàn tất |
| [agent_v2_session03_mistral_fixed_20261007_01](agent_v2_session03_mistral_fixed_20261007_01/report.md) | Run chính; review nội dung chưa hoàn tất |
| [booking_review_20261007_121335_fe5d12](booking_review_20261007_121335_fe5d12/report.md) | Completed artifacts; xem errors/complete trong báo cáo, không mặc định là PASS |
| [mistral_updated_openrouter_endpoint_retry_20261007_01](mistral_updated_openrouter_endpoint_retry_20261007_01/preflight.json) | Preflight endpoint/completion; không phải benchmark chất lượng |
| [mistral_updated_openrouter_preflight_20261007_01](mistral_updated_openrouter_preflight_20261007_01/preflight.json) | Preflight endpoint/completion; không phải benchmark chất lượng |
| [rag_v2_full_100_gemma_rewrite_20261007_01](rag_v2_full_100_gemma_rewrite_20261007_01/report.md) | Completed artifacts; xem errors/complete trong báo cáo, không mặc định là PASS |
| [rag_v2_full_100_mistral_routed_20261007_01](rag_v2_full_100_mistral_routed_20261007_01/report.md) | Run chính; review nội dung chưa hoàn tất |
| [rag_v2_full_gemma_rewrite_smoke_20261007_01](rag_v2_full_gemma_rewrite_smoke_20261007_01/report.md) | Completed artifacts; xem errors/complete trong báo cáo, không mặc định là PASS |
| [rag_v2_full_mistral_routed_smoke_20261007_01](rag_v2_full_mistral_routed_smoke_20261007_01/report.md) | Completed artifacts; xem errors/complete trong báo cáo, không mặc định là PASS |
| [rag_v2_full_mistral_routed_smoke_20261007_02](rag_v2_full_mistral_routed_smoke_20261007_02/report.md) | Completed artifacts; xem errors/complete trong báo cáo, không mặc định là PASS |
| [rag_v2_full_smoke_20261007_01](rag_v2_full_smoke_20261007_01/report.md) | Completed artifacts; xem errors/complete trong báo cáo, không mặc định là PASS |
| [rag_v2_retrieval_smoke_20261007_01](rag_v2_retrieval_smoke_20261007_01/report.md) | Completed artifacts; xem errors/complete trong báo cáo, không mặc định là PASS |
