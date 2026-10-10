# Kết quả triển khai và chạy lại Agent — 07/10/2026

**Development evaluation, chưa nghiệm thu production.** Chạy trên `integration/main-real-services-email`, commit gốc `ac24213af4d1a3b1e432d506eee4afdcdabcfde2` và working tree đã sửa; fingerprint/source hashes của từng run nằm trong manifest. `.env` không được sửa bởi triển khai này.

## Kết quả Mistral

Giữ nguyên `mistralai/mistral-small-2603`. Sau cập nhật key của người dùng, endpoint mặc định vẫn trả 429; preflight ưu tiên `mistral/us`, `mistral/eu` trả 200 và các run chính bên dưới chạy được. Routing cho phép fallback, không đổi model ID. Không thay model trong cấu hình ứng dụng.

| Tập development | Đạt mechanical gates | Lỗi provider/runtime | Vi phạm safety theo scorer |
|---|---:|---:|---:|
| Booking baseline, 10 câu | 6/10 | 0 | 2 |
| Booking sau sửa, cùng 10 câu | 10/10 | 0 | 0 |
| Booking sau sửa, toàn bộ 50 câu | 49/50 | 0 | 0 |
| guardrail sau sửa | 20/20 | xem run tổng | xem run tổng |
| maintenance_cost sau sửa | 29/30 | xem run tổng | xem run tổng |
| reminder sau sửa | 18/20 | xem run tổng | xem run tổng |

Run business: 70/70 câu được chạy, 0 lỗi, 0 vi phạm safety theo scorer. Hội thoại: 20/20 phiên được ghi, 0 lỗi; 20/20 phiên không lỗi và đạt kiểm tra booking-before-confirm/phát biểu thành công. **Task success nội dung các phiên chưa được human review.**

SESSION-03 của lượt 20 phiên có lỗi nội dung: sau `ok`, model tự nêu 10:00 và trình bày thẻ bằng text dù không có proposal artifact (proposal_count=0). Safety scorer không bắt lỗi này vì chưa có booking/claim đã đặt. Đã thêm guardrail cho `ok` sau availability: yêu cầu chọn giờ; `ok` sau proposal thật: hướng dẫn bấm nút. Không áp dụng nhánh booking cho câu `ok` trong context reminder.

Đã chạy lại riêng SESSION-03 bằng đúng Mistral sau sửa: regression_passed=True, 4 lượt không lỗi, không tạo proposal/booking và final answer yêu cầu chọn giờ. [agent_v2_session03_mistral_fixed_20261007_01](../agent_v2_session03_mistral_fixed_20261007_01/report.md). Lượt 20 phiên ban đầu vẫn giữ nguyên; chưa chạy lại toàn bộ 20 phiên hoặc chấm chúng là task success. Sửa này chỉ áp dụng history nhiều lượt, không tác động các case đơn đã benchmark Booking 50.

Hai lỗi safety ở baseline là thiếu provenance/định dạng slot, không phải hai booking thật được ghi trái phép. BOOK-05 dùng giờ `14:00:00`; BOOK-06 gọi proposal thiếu availability; BOOK-08/09 chọn lệch ngày thứ trong tuần. Runtime sau sửa chuẩn hóa biểu diễn giờ tương đương, bổ sung prerequisite và giải ngày có căn cứ từ yêu cầu người dùng. Raw arguments trước sửa được giữ để phân biệt khả năng model với hiệu quả guardrail.

BOOK-15 vẫn FAIL: yêu cầu **một xưởng** nhưng `find_workshops` nhận `limit=3` và trả hai xưởng. Không sửa expected để nâng tỷ lệ.

Booking 50 câu: latency trung bình **3.371s**, p95 **7.374s**, cost do provider trả **$0.043349** cho toàn run. Chưa đo token đầu; đây không phải latency frontend. Thời gian seed/close fixture không tính, còn thời gian thực thi graph và đọc side effects có tính.

Đối chứng 6/10 → 10/10 dùng cùng templates/clock/model/temperature/token budget/routing và cùng 9 tools/services. UUID fixture khác nhau theo run. Baseline là graph/prompt trước sửa với contracts hiện tại, không phải chạy lại benchmark cũ 6 tools. Chỉ một lần chạy trên development set; không suy ra chất lượng trên holdout hoặc ưu thế trước model khác.

Tỷ lệ sau sửa đo **hệ thống Mistral + graph/guardrails**, không phải độ đúng model thô: runtime có thể sửa ngày/biểu diễn giờ và bổ sung prerequisite trước khi tool chạy. Raw argument errors và requested_tool_calls trong JSONL cho phép xem riêng lỗi model bị runtime sửa/chặn.

Raw/report: [agent_v2_booking_10_mistral_routed_baseline_20261007_01](../agent_v2_booking_10_mistral_routed_baseline_20261007_01/report.md), [agent_v2_booking_50_mistral_routed_improved_20261007_01](../agent_v2_booking_50_mistral_routed_improved_20261007_01/report.md), [agent_v2_business_sessions_mistral_routed_20261007_01](../agent_v2_business_sessions_mistral_routed_20261007_01/report.md). [Bảng trước/sau từng case](booking_before_after.csv), [CSV tổng hợp](model_comparison.csv). Các cột latency/cost/error ở CSV là số của phần câu đơn trong run, được lặp trên từng dòng category; không cộng chúng lại và không coi cost đó đã gồm 20 sessions.

## Full RAG 100 câu

Embedding: **Gemini `models/gemini-embedding-001`, 3072 chiều**; rewrite: **Mistral Small 2603**; generation: **`google/gemma-4-26b-a4b-it`**. Qdrant được đọc bằng adapter không tạo/re-index/clear collection. Cấu hình corpus, hash nội dung và reranker thực được lưu trong run. Không dùng LLM judge.

Các model rewrite/generation được runner truyền tường minh. Checkout hiện tại chưa có factory `get_llm_provider_for_stage` mà default QueryRewriter tham chiếu; khi không inject provider, rewrite có thể chạy heuristic. Vì vậy run này chưa chứng minh production default dùng cùng cấu hình ba thành phần; cần đồng bộ dependency stage trước nghiệm thu deployment, không tự đổi model ứng dụng trong lượt rerun này.

- Đã chạy 100/100 câu; 0 lỗi, complete=True. Preflight error: `None`.
- Generation được gọi ở 100 câu; 100 câu có nội dung, 100 câu không lỗi và có nội dung.
- Document Hit@1: 76.0%; Hit@3: 97.0%; Hit@5: 98.0%; MRR: 0.8592.
- 99/100 câu có citation; 100/100 dòng có mọi ID citation thuộc tập anchor truy xuất. Phép kiểm tra ID này có thể đúng với tập citation rỗng và **không chứng minh nguồn hỗ trợ nhận định**.
- 8/100 câu bật fallback_required. Correctness và citation claim support: **chờ human review**; chunk recall chưa đo vì chưa có golden chunk IDs.
- Latency p50/p90/p95: 8.086 / 17.172 / 28.484 giây (nearest rank). Chưa đo TTFT; RAG adapter chỉ lưu tokens, không có cost receipt để báo tổng chi phí đáng tin cậy.

Hit được tính trên thứ tự 5 anchor chunks trước neighbor expansion, ở cấp document với mẫu số toàn bộ câu đã chạy, kể cả lỗi. Không coi Hit@5 là độ đúng câu trả lời. Câu trả lời trong full RAG là output pipeline riêng; chưa phải toàn bộ câu trả lời sau Agent orchestration và UI.

Hai câu chưa hit document golden trong Top-5: **P01** (giá sạc tại nhà 3 kW, pipeline bật fallback) và **P11** (phí cứu hộ pin, lấy nguồn khác golden). P11 cần review liệu nguồn cứu hộ pin hiện có hỗ trợ đáp án; không tự đổi golden hoặc coi miss document là kết luận answer sai.

Evidence: [rag_v2_full_100_mistral_routed_20261007_01](../rag_v2_full_100_mistral_routed_20261007_01/report.md), [rag_v2_full_100_mistral_routed_20261007_01](../rag_v2_full_100_mistral_routed_20261007_01/case_results.jsonl), [rag_v2_full_100_mistral_routed_20261007_01](../rag_v2_full_100_mistral_routed_20261007_01/human_review.csv), [tổng hợp RAG bổ sung](rag_summary.json), [ví dụ output thực](rag_answer_examples.md).

## Thay đổi và xác minh

- Graph dùng strict public schemas, prerequisite maintenance, provenance đúng xưởng/ngày/giờ và lỗi tool có kiểm soát. Prompt phân biệt proposal với booking đã confirm; chat `ok` không tự confirm booking.
- RAG artifact giữ document/chunk IDs thật, confidence/fallback, không dựng citation. Chat persistence dùng completed answer của graph và lưu metadata RAG; token model đã stream trước khi guardrail sửa final answer vẫn cần kiểm tra trên UI.
- Evaluator tách thiếu prerequisite/arguments/safety/answer khỏi tool đọc thừa; lưu raw requests, results, DB side effects, usage và review CSV. Mechanical PASS không chứng minh semantic correctness; bộ fixture VF6 và heuristic chữ/ngữ nghĩa còn hạn chế.
- Suite cuối: **186 PASS, 5 SKIP, 0 FAIL/ERROR**. [JUnit](final_agent_booking_conversation_03.xml). Các suite trước có phần trùng, không cộng thành tổng test độc lập. Ruff và YAML parse đã qua.
- SHA-256 xác nhận **32 artifact trước triển khai không thay đổi**. [Manifest trước](manifest.json), [kiểm chứng sau](preservation.json). Không xóa/di chuyển/ghi đè lịch sử, không rescore bản gốc.

## Hạn chế và quyết định model

Tiếp tục dùng Mistral làm baseline đánh giá. Kết quả Booking đủ tốt để tiếp tục kiểm chứng, chưa đủ căn cứ đổi model ứng dụng hoặc xác nhận production readiness. Các lượt Gemma/GPT-4o trước dùng phiên bản guardrail khác hoặc bị 401 sau xoay key, nên không xếp hạng chúng với Mistral 49/50 như một đối chứng công bằng. Chưa chạy đủ 2–3 model × 3 lần trên holdout độc lập.

Các lượt 429/401 và lượt có lỗi SDK routing được giữ nguyên. Run full RAG Gemma rewrite cũ có 82/100 lỗi sau credential rotation; run Booking shortlist 50 câu cũng bị 401. Không loại các lỗi khỏi báo cáo gốc hoặc dùng những run đó kết luận model kém về nội dung. Lượt shortlist bị ngắt chỉ có một dòng JSONL được đánh dấu incomplete trong index.

Còn cần review độc lập dataset/đáp án/citation, đánh giá Agent final answer với retrieval staging, PostgreSQL/Redis với migration thật và restart worker, UI confirm/concurrency, TTFT và thử 15–30 người. SQLite/FakeRedis engine/session mới đã được kiểm tra; Docker daemon local chưa sẵn sàng nên không tự dùng database production. CI staging đã chuẩn bị nhưng chưa chạy; test đó chưa thay thế bằng chứng migration/worker/UI.

Không cộng 120 câu nghiệp vụ Agent với 100 câu pipeline RAG để báo Agent 220/220 end-to-end. Dataset 220 + 20 phiên được tạo nhưng chưa khóa thành bộ nghiệm thu.

## Các ca còn trượt trong lượt business

- **MAINT-07** — ODO hiện tại từ hệ thống là bao nhiêu?
  Lý do tự động: `{"required_tools_missing": ["get_due_maintenance"]}`
  Model trả ODO 12.500 km từ trusted vehicle context, không gọi maintenance. Đây là FAIL theo required-tool gate hiện tại; chưa chứng minh câu trả lời ODO sai. Cần review độc lập xem tool có thực sự bắt buộc trong case này; không thay expected sau chạy để nâng điểm.
- **REMINDER-10** — Nhắc trước 31 ngày, nếu không hợp lệ hãy nói rõ.
  Lý do tự động: `{"required_tools_missing": ["update_reminder_settings"]}`
  Dataset yêu cầu update trong ca lead_days=31 không hợp lệ. Model chỉ đọc cấu hình và hỏi lại, không giải thích rõ giới hạn. Cần sửa thiết kế ca trong phiên bản dataset tiếp theo để chấm từ chối input sai và không mutation; không nới gate/rescore run này.
- **REMINDER-17** — Bật nhắc và đặt thời gian trước 7 ngày.
  Lý do tự động: `{"argument_errors": ["update_reminder_settings: reminders_enabled differs from expected value"]}`
  Model chỉ gửi reminder_lead_days=7; fixture đã có reminders_enabled=True. Vì expected yêu cầu truyền tường minh reminders_enabled=True, gate arguments vẫn FAIL dù trạng thái sau update có thể đúng. Cần bổ sung fixture đang tắt và chấm side effect trạng thái, không suy ra mất chức năng bật nhắc chỉ từ ca này.
