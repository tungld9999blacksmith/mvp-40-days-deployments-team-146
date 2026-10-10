# Bước5 — bộ mới đã khóa, chạy lặp3 lần

Hai cấu hình Agent Mistral/Gemma; Rewrite/generation Mistral, Gemini embedding.30 câu mới, không trùng nguyên văn220 câu development cũ. Bộ do AI tạo, các intent có thể gần development; **chưa chứng nhận holdout độc lập hoặc nghiệm thu production**. Không sửa runtime/prompt/dataset giữa các lượt. Pilot không cộng vào full accuracy.

| Agent | Lượt | Kỹ thuật đạt/attempted/30 | Nhãn tự động | TB giây | p90 giây | Receipt pipeline USD |
| --- | ---: | --- | --- | ---: | ---: | ---: |
| Mistral | 1 | 30/30/30 | {} | 4.842833333333333 | 11.627300000000002 | 0.033496551 |
| Mistral | 2 | 30/30/30 | {} | 4.9992 | 10.220500000000001 | 0.036277940 |
| Mistral | 3 | 30/30/30 | {} | 4.8924666666666665 | 9.639300000000004 | 0.031916016 |
| Gemma | 1 | 30/30/30 | {} | 8.3662 | 16.5669 | 0.016483406 |
| Gemma | 2 | 30/30/30 | {} | 8.425166666666666 | 14.5153 | 0.015386887 |
| Gemma | 3 | 30/30/30 | {} | 8.227933333333333 | 13.9375 | 0.014839810 |

Receipt mới55 **0.257063102 USD**, pipeline0.257063102, judge0.000000000; 69 embedding calls chưa có receipt. Thiếu 0 receipt pipeline/0 judge. Không phải hóa đơn toàn dự án.

Các lỗi task/arguments được giữ trong mẫu số; không tối ưu từ output rồi chạy lại để che lỗi. Nếu batch dừng vì safety/provider/receipt/budget, ghi đúng attempted và phần chưa chạy, không tuyên bố đủ×3. UNVERIFIABLE không tính PASS. Nhãn tự động chưa hiệu chuẩn; actual tool/state và expected criteria được giữ riêng.

Giữ Mistral baseline, không đổi.env hoặc model production. Không GPT-4o/Write/email thật/DB production; corpus chỉ đọc, golden/dataset/test_agents và kết quả cũ giữ nguyên. Staging/UI, nguồn chuẩn và các mẫu số nghiệm thu PRD lớn hơn vẫn chưa đủ;30 câu này không tự đáp ứng≥60RAG/≥50NLU.

Chi tiết: manifest.json, selected_cases.json, rubric.json, prior_flag_audit.json, result.json, all_attempts_cost.json và flagged_judgments.json.

Resume61: bộ30 đã dùng sửa reminder/booking nên là **development regression**, không phải holdout độc lập. Mistral repeat1 được sao chép nguyên vẹn từ producer60 đã kiểm tra seal/source/config/corpus; không gọi model lại, không tính phí hoặc embedding lần hai. Gemma21 câu bị dừng theo người dùng giữ nguyên ở60 và loại khỏi sáu full repeat; Gemma repeat1 ở61 chạy mới đủ30.

Chi phí trong bảng và ledger chỉ là receipt đã biết. Yêu cầu đang chạy khi dừng60 có phí chưa xác định, không được coi bằng0. Reserve0,01USD dùng cho kiểm tra ngân sách, không phải receipt hay giới hạn phí đã được chứng minh; embedding cũng chưa định giá. Cap receipt0,75USD giữ nguyên.
