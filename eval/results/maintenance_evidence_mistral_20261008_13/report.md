# Bước 3 — bảng bảo dưỡng thiếu cột — 08/10/2026

Đã hoàn tất đợt development này; chưa nghiệm thu production. Giữ Mistral Small 2603, Gemini embedding, golden/dataset/scorer và corpus. Không retrieval mới, gửi mail thật, ghi DB production hoặc restart app.

M07: trích nguyên dòng coolant 12.000 km/120 tháng và yêu cầu xác minh; không tự sửa thành 120.000 km. M18: giữ tên hạng mục có trong bảng nhưng không gán thao tác/chu kỳ cho các dòng trống. M23: bảng thiếu cột không đủ căn cứ lập danh sách phụ tùng bắt buộc thay tại 40.000 km. Đây là xử lý thiếu bằng chứng, không chứng nhận lịch bảo dưỡng hiện hành.

Probe phát hiện bảng đầy đủ viết gọn có ô trống cuối dòng bị hiểu nhầm là mất cột. Đã sửa parser giữ đúng các ô trống; [probe fail](compact_matrix_probe_01.json) và [probe cùng input sau sửa](compact_matrix_probe_02.json) được lưu riêng. Preflight/revision01/XML đầu giữ nguyên; revision02 được đóng trước full 100, không đổi code giữa run.

| Run | Hoàn tất | Lỗi | Request JSON hợp lệ | Trả trước provider | Fallback |
|---|---:|---:|---:|---:|---:|
| Mistral trước | 100 | 0 | 93/93 | 7 | 30 |
| Preflight | 3 | 0 | 0/0 | 3 | 3 |
| Mistral mới100 | 100 | 0 | 90/90 | 10 | 33 |

Offline: {'passed': 519, 'skipped': 5, 'failures': 0, 'errors': 0, 'focused_final_passed': 89}. [JUnit cuối](final_regression_01.xml); Ruff passed. [6/6 kiểm tra mục tiêu](targeted_checks.json) không thay thế semantic accuracy.

[100 câu trước/sau](rag_review.html) và [hash cùng input](same_input_comparison.json). Citation membership chỉ kiểm identity, không thay citation support. Ba câu mục tiêu được xử lý trước provider, không tính thành model tự suy luận đúng. Không có retrieval mới.

Đối chứng ở đây là run Mistral trước với cùng input/prompt/request schema. Paired comparison bên trong producer metrics dùng Gemma lịch sử với prompt-only JSON, nên khác điều kiện; số lỗi schema trong bản baseline sao chép không phải lỗi API hiện tại hoặc bằng chứng model A/B cùng điều kiện.

Chi phí receipt đợt này: 0.033152229 USD; thiếu 0 receipts.

[Preservation](preservation.json): 1165 artifact/dataset cũ và 43 file corpus không đổi; mọi run mới có thư mục riêng.

Người dùng đã chọn trực tiếp review, nhưng chưa nộp nhãn; [hướng dẫn](REVIEW_INSTRUCTIONS.md) và [assignment](reviewer_assignment.json). Reviewer độc lập hiện vẫn 0 nhãn. Chủ nguồn còn phải xác minh coolant/scope/phiên bản; [queue nguồn](source_owner_review_queue.json) giữ trạng thái pending. Holdout, shortlist và HTTP/UI/TTFT/pilot chưa hoàn tất. Không sửa kỳ vọng golden hoặc rescore output cũ để nâng điểm.
