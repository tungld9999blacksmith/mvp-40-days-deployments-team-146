# Nhận xét Rewrite — bước 4, 08/10/2026

Đã sửa code Rewrite để gửi JSON schema 7 trường và phân biệt mốc bảo dưỡng với ODO. Cả ba qua pilot 5/5 trên cùng revision; các full run dưới đây dùng đúng 30 câu nguyên văn (24 golden +6 v2.1), không cộng pilot thành 35 case độc lập/model. Cấu hình model trong `.env` giữ nguyên, ứng dụng chưa restart.

| Model | Hoàn tất | JSON thuần đạt | Trường đầu vào khớp | Document Hit@5 (golden draft) | Rewrite TB (giây) | Receipt Rewrite full (USD) |
| --- | --- | --- | --- | --- | --- | ---: |
| mistralai/mistral-small-2603 | 30/30 | 30 | 30 | 23/24 | 1.127 | 0.003173065 |
| google/gemma-4-26b-a4b-it | 30/30 | 30 | 30 | 23/24 | 4.039 | 0.003073576 |
| google/gemini-3.5-flash-lite | 30/30 | 30 | 30 | 23/24 | 1.353 | 0.016533600 |

Lượt Gemma đầu dừng **2/30** ở M02 do **Gemini embedding trả 503**, không phải API Rewrite của Gemma. Giữ nguyên trace/verdict/receipt **0.000191880 USD**. Gemma được chạy **mới toàn bộ 30 câu**, không ghép một câu thành công cũ với phần chạy bù. Mistral/Gemini dùng các full run đã đóng cùng revision; không gọi lại hai model này chỉ vì lỗi embedding ở Gemma.

Receipt Rewrite cho pilot +các full run được chọn: **0.026780803 USD**. Cộng cả lượt Gemma dừng lỗi: **0.026972683 USD**. Phí query embedding chưa có receipt, nên đây chưa phải tổng phí pipeline đầy đủ. Báo cáo/CSV chính dùng các full run được chọn; chi phí mọi attempt nằm trong `all_attempts_cost.json`. Không gọi generation, Write, GPT-4o hoặc model thứ tư.

Theo receipt của các full run được chọn, Gemma thấp hơn Mistral **3.1%**; Gemini Flash Lite bằng **5.21 lần** Mistral. Routing, cache và tải nhà cung cấp chưa được kiểm soát; các tỷ lệ này mô tả lượt chạy thực tế, chưa chứng minh mức tiết kiệm ổn định.

**Giữ Mistral làm baseline.** Gemma tiếp tục là ứng viên Rewrite để đánh giá chi phí/tốc độ cùng chất lượng nội dung. Gemini Flash Lite chưa có lợi thế chi phí trong lượt này. Đối chiếu các lỗi raw/trường đầu vào trong bảng trước khi coi model đủ điều kiện kỹ thuật; xem `shortlist_by_stage.json`.

Hit@5/category dùng golden draft chưa xác minh, không phải semantic accuracy hoặc chất lượng câu trả lời. Các câu lệch category/không hit tài liệu được ghi ở `draft_case_followup.json`; không tự sửa golden hoặc kết luận model sai từ các nhãn chưa review. Review người dùng vẫn tạm hoãn, 0 nhãn độc lập. Holdout ×3, cấu hình ghép và integration/UI chưa chạy; chưa nghiệm thu production.

Bước tiếp: nếu còn lỗi kỹ thuật trong full thì xử lý bằng revision mới và chạy lại baseline cùng điều kiện; nếu không, chuyển sang generation Mistral/Gemma, kiểm lỗi contract Gemma M01 đã lưu trước khi mở rộng. Mọi kết quả cũ ở test agents/eval, golden/dataset và corpus được giữ nguyên.
