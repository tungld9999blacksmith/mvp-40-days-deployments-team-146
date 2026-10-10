# Bước5 — bộ mới đã khóa, chạy lặp3 lần

Hai cấu hình Agent Mistral/Gemma; Rewrite/generation Mistral, Gemini embedding.30 câu mới, không trùng nguyên văn220 câu development cũ. Bộ do AI tạo, các intent có thể gần development; **chưa chứng nhận holdout độc lập hoặc nghiệm thu production**. Không sửa runtime/prompt/dataset giữa các lượt. Pilot không cộng vào full accuracy.

| Agent | Lượt | Kỹ thuật đạt/attempted/30 | Nhãn tự động | TB giây | p90 giây | Receipt pipeline USD |
| --- | ---: | --- | --- | ---: | ---: | ---: |
| Mistral | 1 | 29/30/30 | {} | 5.6465000000000005 | 13.0873 | 0.033200211 |

Receipt mới55 **0.089040717 USD**, pipeline0.089040717, judge0.000000000; 24 embedding calls chưa có receipt. Thiếu 0 receipt pipeline/0 judge. Không phải hóa đơn toàn dự án.

Các lỗi task/arguments được giữ trong mẫu số; không tối ưu từ output rồi chạy lại để che lỗi. Nếu batch dừng vì safety/provider/receipt/budget, ghi đúng attempted và phần chưa chạy, không tuyên bố đủ×3. UNVERIFIABLE không tính PASS. Nhãn tự động chưa hiệu chuẩn; actual tool/state và expected criteria được giữ riêng.

Giữ Mistral baseline, không đổi.env hoặc model production. Không GPT-4o/Write/email thật/DB production; corpus chỉ đọc, golden/dataset/test_agents và kết quả cũ giữ nguyên. Staging/UI, nguồn chuẩn và các mẫu số nghiệm thu PRD lớn hơn vẫn chưa đủ;30 câu này không tự đáp ứng≥60RAG/≥50NLU.

Chi tiết: manifest.json, selected_cases.json, rubric.json, prior_flag_audit.json, result.json, all_attempts_cost.json và flagged_judgments.json.
