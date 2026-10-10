# Tiếp tục đánh giá Mistral — 08/10/2026

**Đã chạy tiếp được khi ưu tiên endpoint `mistral/us,mistral/eu`.** Model giữ nguyên `mistralai/mistral-small-2603`. Đây là kết quả development của Agent gồm model và runtime; chưa nghiệm thu production. [Kết quả đầy đủ](result.json).

## Khả năng gọi API

Preflight routing mặc định REMINDER-12 thành công, nhưng batch mặc định ngay sau đó lại lỗi **429 upstream shared pool** ở ca đầu: **1/60 đã thử**, 59 ca chưa thử. Request đầu thành công chưa chứng minh API ổn định. Run lỗi được giữ nguyên.

Preflight với endpoint order `mistral/us,mistral/eu` thành công, sau đó chạy được toàn bộ reminder và các phiên mới. `allow_fallbacks=true`; ghi nhận provider model trả về đúng Mistral, **không ghi nhận region thực tế của từng request**. Routing khác default được lưu trong manifest; không dùng khác biệt tải/routing để kết luận model đã thay đổi chất lượng hoặc SLA đã được bảo đảm. Không sửa `.env` hoặc restart app/demo.

## Reminder: đủ ba lượt

| Lượt | PASS / đã thử / kế hoạch | Lỗi provider | Safety violations | Latency trung bình | Receipt USD |
|---|---|---:|---:|---:|---:|
| 1 | 20 / 20 / 20 | 0 | 0 | 3,2749 giây | 0,019973052 |
| 2 | 20 / 20 / 20 | 0 | 0 | 3,0843 giây | 0,019405353 |
| 3 | 20 / 20 / 20 | 0 | 0 | 3,0965 giây | 0,018930615 |

Tổng **60/60** theo mechanical gates của scorer 2.2; latency trung bình **3,1519 giây/ca**, receipt **0,058309020 USD**. Latency không bao gồm khoảng nghỉ 4 giây giữa các ca; token đầu chưa đo.

Trong **24/60 ca**, runtime bổ sung update từ lệnh người dùng rõ ràng sau khi đọc cài đặt thành công. Vì vậy 60/60 là kết quả **Agent có guardrails/intent repair**, không phải tỷ lệ Mistral tự hoàn thành 60 ca. Cấu hình: dataset v2.1 development, temperature 0,2, max_tokens 1536, timeout 60 giây. Clock fixture giữ nguyên `2026-10-07T09:00:00+07:00`; ngày 08/10 là ngày chạy thực tế.

[Summary reminder](reminder_summary.json), [raw reminder](../agent_v2_1_reminder_routed_mistral_60_20261008_02/case_results.jsonl), [report từng lượt](../agent_v2_1_reminder_routed_mistral_60_20261008_02/report.md).

## Phiên nhiều lượt

Đã chạy đủ **20 phiên / 80 lượt người dùng**, 0 lỗi thực thi; **20/20 qua write-safety checks**. Không ghi nhận booking được tạo trước confirm, claim booking chưa có bằng chứng hoặc claim reminder update thiếu result trong lượt hiện tại theo detector. **Task success vẫn `NEEDS_HUMAN_REVIEW`**, không gọi đây là 20/20 đúng nội dung hoặc 20 booking hoàn tất.

Receipt của riêng các phiên: **0,071224494 USD**, từ 152 AI message receipts, đã khử trùng lặp message IDs vì transcript mỗi lượt chứa history. Không có receipt thiếu cost trong các messages đã ghi. Preflight REMINDER-12 của run phiên tách riêng: **0,001189980 USD**. Đây là receipt trong traces, không đối soát billing dashboard.

[Summary phiên](session_summary.json), [raw 20 phiên](../agent_v2_1_sessions_routed_mistral_20_20261008_02/comparison.json), [mẫu review trống](session_human_review.csv).

## Lỗi nội dung vẫn còn trong mẫu đọc

Các nhận xét dưới đây là **Codex draft từ hai lượt được đọc**, 0 nhãn reviewer độc lập, không phải review semantic toàn bộ 80 lượt:

| Vị trí | Câu trả lời | Evidence tool | Kết luận cần sửa |
|---|---|---|---|
| SESSION-02, lượt 1 | Nói quá hạn “500 km và 182 ngày”, rồi nói hạn thời gian còn 6 tháng | `due_reason=KM`, `remaining_km=-500`, `remaining_days=182`, `due_date=2027-04-07` | Đến hạn do km; 182 ngày là thời gian còn lại, không phải số ngày quá hạn. Câu trả lời tự mâu thuẫn. |
| SESSION-02, lượt 2 | “Giá đã bao gồm VAT theo quy định xưởng” | Cost result có total 100.000 VND, `WORKSHOP_PRICE`, không có field VAT | Không khẳng định VAT khi không có nguồn. |

Xem nguyên văn và tool results tại [semantic_followup_samples.json](semantic_followup_samples.json). Hai lỗi này không được scorer cơ học tính thành độ đúng nội dung. Queue warranty/nguồn giá/UI/RAG trước đó vẫn cần xử lý, không suy rằng đã hết lỗi vì mẫu trả lời mới có câu tốt hơn.

## Bảo toàn và phạm vi

[Preservation](preservation.json) xác minh **677 file có trước đợt này giữ nguyên**, cùng snapshots của các run mới hoàn tất. Giữ cả run lỗi 429, kết quả ngày 07/10 và các XML cũ.

Không thay runtime trong đợt này, chỉ thay tham số routing cho các run mới và cập nhật plan. [Nguồn regression trước](source_regression_provenance.json): 314 pass, 5 skip; không chạy lại tests cho kiểm tra cấu hình này. Không gửi email thật, không ghi production DB; service trên SQLite riêng/FakeAsyncRedis, RAG fixture orchestration. Không tạo kết quả retrieval/generation mới và không chứng minh app đang chạy đã dùng routing này.

Bước tiếp theo trong [plan](../../../docs/plans/AGENT_IMPROVEMENT_AND_REEVALUATION_PLAN.md): sửa grounding nghiệp vụ và review các phiên/nguồn, review độc lập để khoá holdout, đánh giá shortlist và PostgreSQL/Redis/restart/UI. Chưa bật GPT-4o write reviewer hoặc quyết định đổi model.
