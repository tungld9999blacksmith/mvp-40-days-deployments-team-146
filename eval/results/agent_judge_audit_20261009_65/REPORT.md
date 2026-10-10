# Đối soát offline và dự toán phần còn lại — checkpoint65

Ngày: 09/10/2026. Đã kiểm tra đủ 14 mẫu bị đánh dấu trong 60 đáp án checkpoint64. Không gọi Agent, judge, embedding hoặc Qdrant; **phí API mới: 0 USD**. Chỉ thêm artifact mới, không thay đổi verdict, raw trace, receipt hoặc manifest cũ.

## Kết quả và giới hạn

| Mẫu | Cấu hình | Nhãn gốc giữ nguyên | Kết luận đối soát |
| --- | --- | --- | --- |
| sample-012 / NEW-B01 | Mistral | FAIL | Số lượng, từng giờ, chỗ còn lại, ngày và xưởng khớp tool |
| sample-014 / NEW-B03 | Mistral | FAIL | Số lượng, từng giờ, chỗ còn lại, ngày và xưởng khớp tool |
| sample-044 / NEW-B03 | Gemma | FAIL | Số lượng, từng giờ, chỗ còn lại, ngày và xưởng khớp tool |
| sample-002 / NEW-R02 | Mistral | UNVERIFIABLE | Bỏ sót quy trình đã có trong nguồn và request generation; judge lại chấm cả correctness/faithfulness/task_success PASS |
| sample-032 / NEW-R02 | Gemma | FAIL | Bỏ sót cùng quy trình trong cùng chunk; judge phát hiện lỗi ở mẫu này |
| sample-005 / NEW-R05 | Mistral | FAIL | Không có citation; judge đưa lời giới hạn thiếu bằng chứng vào factual claims, gây citation FAIL. Cần phân định abstention với khẳng định về tài liệu |
| sample-003, 004, 006 | Mistral | UNVERIFIABLE | Truy vết trạng thái chưa xác minh từ response RAG; không chuyển thành PASS |
| sample-031, 033, 034, 035, 036 | Gemma | UNVERIFIABLE | Truy vết trạng thái chưa xác minh từ response RAG; không chuyển thành PASS |

Ba phản đối booking của judge bị dữ liệu tool bác bỏ trong phạm vi phát biểu availability. Không suy ra toàn bộ đáp án đạt và không đổi 3 FAIL thành PASS. Kết quả gốc vẫn **46 PASS / 5 FAIL / 9 UNVERIFIABLE**, không dùng để xếp hạng chất lượng production.

**NEW-R02 là lỗi dùng bằng chứng trong RAG generation ở cả hai cấu hình.** Chunk `quy_trinh_ung_dung_ALL_chk_0002` có đủ ba bước tìm trạm bằng Bản đồ; hash nội dung trong hai mẫu giống nhau và toàn bộ chunk xuất hiện trong request generation. Cả hai dùng `mistralai/mistral-small-2603` cho generation, rồi chuyển nguyên câu trả lời tool ra final. Đây không phải bằng chứng lỗi riêng Agent Gemma hoặc thiếu retrieval. Judge bỏ qua lỗi ở Mistral nhưng phát hiện ở Gemma. Chi tiết từng bước và provenance có trong [audit.json](audit.json).

**Chín UNVERIFIABLE không phải chín câu trả lời sai.** Cả chín có `fallback_required=true`; chỉ hai mẫu NEW-R04 đồng thời có `source_rule_verified=false` với lý do `coolant_source_value_unverified`. Bảy mẫu còn lại không có trường xác minh nguồn rõ ràng. Trong `automatic_review_complete_evidence.build_sample`, fallback hoặc source_rule_verified=false đều gộp thành source_uncertainty; `combined_status` giữ UNVERIFIABLE nếu không có FAIL. Cần tách mức đầy đủ bằng chứng, tính đúng trong evidence và độ tin cậy/hiệu lực nguồn trong revision evaluator mới. Thiếu trường xác minh không chứng minh nguồn đúng; không bỏ gate để tăng điểm.

NEW-R05 của Mistral không cung cấp cam kết bảo hành cụ thể; không nên tự thêm citation để làm đẹp điểm. Phải khóa quy tắc phân biệt lời giới hạn trên tập đoạn truy xuất với khẳng định kỹ thuật/phủ định toàn bộ tài liệu. Kiểm tra này không chứng nhận hiệu lực chính sách, nhãn độc lập vẫn bằng 0.

## Thứ tự sửa trước đợt trả phí mới

1. Tạo revision evaluator mới: dùng kiểm tra xác định cho số slot/ngày/xưởng/chỗ trống; vẫn chấm riêng tính đủ, thực hiện yêu cầu và an toàn. Thêm controls chứa lỗi số lượng, lặp giờ, slot không khả dụng, sai ngày/xưởng và bỏ sót quy trình dù có citation.
2. Tách trạng thái `fallback_required` khỏi trạng thái xác minh nguồn; báo riêng correctness trong evidence, completeness, citation và source authority. Chưa hiệu chuẩn độc lập thì vẫn không nghiệm thu production.
3. Sửa generation để trả phần quy trình trực tiếp có trong một nguồn phù hợp, giữ citation và các giới hạn phạm vi; không nối bước thiếu từ nguồn khác. Kiểm thử cả truy vấn có/không đủ bước, chunk bị cắt, sai mục và nguồn không phù hợp. Không chỉ sửa đáp án của NEW-R02.
4. Kiểm thử ranh giới abstention/claim của NEW-R05 bằng các ca đối nghịch. Giữ nguyên golden/corpus/dataset/test_agents/kết quả cũ; mọi chạy mới dùng revision và thư mục mới.
5. Chạy pilot nhỏ trước hồi quy trả phí; nếu scorer còn phản đối sai dữ liệu tool hoặc bỏ sót lỗi đã biết thì dừng pilot, không chấm lại toàn bộ. Bộ 30 vẫn development regression, không đổi tên thành holdout.

## Dự toán tiền LLM còn lại

Đây là ước tính dựa trên receipt, không phải hóa đơn hay mức trần được đảm bảo. Chi phí pipeline 180 đáp án hoàn chỉnh ở61 là **0,14840061 USD**, trung bình **0,000824448 USD/đáp án**, gồm Agent và các stage được gọi. 60 nhãn unique ở63/64 tốn **0,16880852 USD**, trung bình **0,002813475 USD/đáp án**. Không cộng lại pilot hoặc 25 nhãn tái sử dụng khi tính đơn giá. Judge chiếm khoảng 77% phí sinh + chấm theo workload này.

| Phạm vi | Ước tính tiền LLM mới |
| --- | ---: |
| Đối soát65 và kiểm tra code offline | 0 USD API |
| Chấm thêm 120 đáp án cũ, không sinh lại | Khoảng 0,338 USD trước pilot; chưa đề xuất chạy khi judge chưa đáng tin |
| Một đợt development 30 câu × 2 cấu hình × 3 lần, sinh + chấm đủ180 | Cơ sở 0,655 USD; dự trù 0,85–1,40 USD với pilot/biến động |
| Phần plan còn lại: 220 câu + 20 phiên × 2 cấu hình × 3 lần | **Khoảng 9–16 USD** |
| Mở rộng thành 3 cấu hình ×3 | Khoảng 13–24 USD, chỉ là kịch bản nếu cấu hình thứ ba có đơn giá tương đương |

Plan quy định mỗi phiên 3–6 lượt: hai cấu hình ×3 tạo khoảng **1.680–2.040 đáp án**, không phải1.440. Nếu chấm từng đáp án một lần với payload tương tự30 câu, cơ sở sinh + chấm là **6,112–7,421 USD**. Khoảng9–16 USD dùng dự phòng30% ở đầu thấp/100% ở đầu cao cho lịch sử hội thoại, workload và độ dài evidence, cộng0,90–1,10 USD cho một vòng development/pilot/staging. Dự phòng là giả định lập ngân sách; chưa đo token của bộ nghiệm thu, không đảm bảo chi phí tối đa. Mỗi vòng tối ưu/chạy lại bổ sung làm tăng phí.

Phạm vi55–64 đã có receipt **0,45933872225 USD**. Cộng với dự toán chi tiết phần còn lại hai cấu hình được khoảng **9,305–16,402 USD**, **không phải tổng hóa đơn toàn dự án**: các đợt trước55 chưa cộng vào con số này. [Công thức và dữ liệu](cost_estimate.json).

Chưa gồm embedding (kể cả69 calls cũ), receipt403 thiếu, request đang chạy lúc dừng60, hosting/Qdrant/Redis, phí Resend, phí nạp/tax, công rà soát độc lập hoặc thử với15–30 người. Không thể định giá toàn bộ việc nghiệm thu production nếu chưa chốt các phần này và số vòng tối ưu.

Cap receipt bước5 đã duyệt vẫn **0,75 USD**, headroom theo receipt chỉ còn **0,29066127775 USD**, chưa trừ phí chưa biết. Ngay cả chấm120 còn lại cũng vượt headroom. Các dự toán trên **không tự tăng cap hoặc mở batch trả phí**. Đợt65 chỉ chạy offline.

Giá niêm yết kiểm tra09/10/2026 để đối chiếu, không thay receipt: [Mistral Small2603](https://openrouter.ai/mistralai/mistral-small-2603) 0,15/0,60 USD; [Gemma26B](https://openrouter.ai/google/gemma-4-26b-a4b-it) 0,042/0,22 USD; [Gemini3.5FlashLite](https://openrouter.ai/google/gemini-3.5-flash-lite) 0,30/2,50 USD cho mỗi triệu input/output token. Provider/cache có thể làm phí thực tế khác giá này. Giữ Rewrite/generation Mistral, không dùng GPT-4o.

## Kiểm chứng

13 kiểm thử audit/ước tính PASS, Ruff PASS. Hash trước/sau xác nhận **29 file master64, 2.945 file lịch sử/dataset/test_agents và341 source** nguyên vẹn. Source runtime, `.env`, golden và dữ liệu production không đổi. [Bằng chứng](after_preservation.json). Những gì còn mở: revision sửa RAG/evaluator, hiệu chuẩn nguồn/judge, holdout độc lập, latency p90≤8s, integration/UI và thử người dùng.
