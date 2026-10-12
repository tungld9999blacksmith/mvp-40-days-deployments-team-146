# P2 — Giờ nhận nhắc bảo dưỡng

Trạng thái: đã triển khai và kiểm tra kỹ thuật ngày 11/10/2026; chưa rollout thật. Đây là P2 của [tính năng cá nhân hoá](../../../../DRIVING_HABIT_RESULTS_AND_USAGE.md), mở rộng [contract P1](driving-habit-reminders-phase2-spec.md). Áp dụng cho nhắc bảo dưỡng theo mốc; không thay lịch nhắc cuộc hẹn hay follow-up.

## Contract cài đặt

`GET/PUT /api/v1/notification-settings` vẫn owner-scoped, trả envelope `data`; PUT hỗ trợ cập nhật từng field theo contract hiện có.

| Field JSON | Quy tắc |
|---|---|
| `sendScheduleAvailable` | Backend thật trả `true`; mặc định schema `false` cho backend cũ/demo. UI chỉ gửi patch lịch khi có khả năng này. |
| `preferredSendTime` | `HH:mm` 24 giờ hoặc `null` để bỏ giờ chọn. |
| `quietHours` | `{ "start": "22:00", "end": "07:00" }` hoặc `null` để tắt; start khác end. |
| `timezone` | Tên IANA hợp lệ; mặc định `Asia/Ho_Chi_Minh`; không nhận `null`. |

Field không có trong PUT giữ nguyên. `null` chỉ xoá giờ chọn/giờ yên lặng; không tự tắt nhắc, đổi kênh hoặc bật consent cá nhân hoá. Input sai trả 422 và không ghi một phần. Cài đặt chung cho các xe thuộc tài khoản. Tài khoản cũ không có giờ chọn/giờ yên lặng tiếp tục gửi ngay khi đủ điều kiện.

Ví dụ body PUT:

```json
{
  "preferredSendTime": "19:00",
  "quietHours": { "start": "22:00", "end": "07:00" },
  "timezone": "Asia/Ho_Chi_Minh"
}
```

## Tính giờ và lưu lịch

- Feed xuất hiện ngay khi evaluator quyết định cần nhắc. Không đổi `Reminder.scheduled_at` sang giờ tương lai. Giờ kênh ngoài nằm ở `ReminderDelivery.next_eligible_send_at`, lưu UTC; chi tiết nhắc trả `nextEligibleSendAt` cho UI.
- Delivery mới đợi giờ chọn gần nhất trong tương lai. Tạo trong đúng phút đã chọn vẫn gửi được dù đồng hồ có giây. Qua giờ chọn thì đợi ngày sau. Nếu chỉ bật quiet hours, gửi ngay ngoài khoảng yên lặng.
- Quiet hours gồm thời điểm bắt đầu và không gồm thời điểm kết thúc, hỗ trợ khoảng qua nửa đêm. Giờ chọn nằm trong khoảng này được chuyển đến giờ kết thúc quiet hours.
- Tính theo ngày địa phương của timezone đã lưu. Giờ DST không tồn tại được chuẩn hoá tiến tới giờ hợp lệ; giờ lặp chọn instant không sớm hơn thời điểm yêu cầu. Dispatcher ngay sau nửa đêm có grace tối đa 15 phút cho slot cuối ngày; grace không vượt quiet hours hoặc gửi trước due instant.
- Retry/downtime cho phép gửi sau giờ chọn trong ngày nếu đang ngoài quiet hours. Không tạo các lượt gửi bù theo số ngày đã bỏ lỡ. Delivery có lịch hết hạn sau 7 ngày; chỉnh giờ không gia hạn vô hạn. Khi kích hoạt lịch cho delivery cũ, hạn được đặt một lần nếu chưa có.

## Dispatcher và tính đồng thời

Giữ evaluator hằng ngày. Beat `reminder.dispatch_due` chạy mỗi 900 giây, đọc tối đa 500 ID delivery đã tới giờ bằng index, rồi enqueue `reminder.dispatch_delivery`. Không quét toàn fleet hoặc tạo Celery ETA dài. Email retry tick mỗi phút chỉ dispatch delivery tồn tại đã tới hạn; không tạo reminder mới.

Trước transport, đọc lại quyền/chủ xe/trạng thái xe, kênh, điều kiện mốc, booking và cài đặt giờ. Hai worker tranh cùng delivery dùng claim/lease trong database. Commit claim trước I/O; không giữ transaction trong lúc gọi transport. ID, attempts và payload email đã bắt đầu gửi được giữ qua restart/retry/đổi giờ.

Sửa cài đặt, tắt nhắc hoặc bỏ kênh sẽ reschedule/cancel các delivery chưa gửi trong transaction cài đặt. Booking hiện tại/tương lai phù hợp huỷ delivery đang chờ trong transaction booking; rollback booking cũng rollback huỷ. Thu hồi consent huỷ payload forecast đang chờ. Delivery huỷ không tự được reset khi bật lại; receipt đã gửi giữ lịch sử chống trùng. Không thể thu hồi transport đã bắt đầu hoặc email provider đã nhận.

## Retry và kết quả chưa rõ

Email có lịch cho phép deadline nghiệp vụ tới 72 giờ từ lần thử đầu, giới hạn thêm bởi hạn delivery và max attempts. Backoff tăng 5 phút theo attempt, tiếp tục tuân giờ chọn/quiet hours. Tài khoản không dùng lịch giữ deadline email cũ 23 giờ.

Deadline nghiệp vụ không mở rộng thời gian provider giữ idempotency key. Resend lưu key 24 giờ theo [tài liệu chính thức](https://resend.com/docs/dashboard/emails/idempotency-keys). `uncertain_attempt_at` được ghi trước I/O và giữ lần chưa rõ sớm nhất qua timeout, lỗi kết nối hoặc crash. Khi lần retry kế tiếp nằm ngoài 23 giờ từ mốc này, chuyển `needs_reconciliation` và bỏ lịch retry tự động. HTTP 429 xác nhận từ chối có thể retry ngày sau trong deadline nghiệp vụ; 429 không xoá một timeout chưa rõ trước đó. Migration backfill mốc chưa rõ cho outbox cũ chưa có acceptance.

Kênh khác chưa có contract idempotency provider: claim hết lease mà chưa biết kết quả chuyển `DELIVERY_UNCERTAIN`, không replay tự động. Đối soát provider thật là bước vận hành riêng; webhook email xác thực có thể bổ sung receipt acceptance. Không tuyên bố bảo đảm exactly-once từ provider.

## UI và triển khai

Trang Cài đặt thông báo có công tắc giờ nhận, giờ yên lặng, time input và timezone. Giá trị gợi ý khi bật lần đầu là 19:00, quiet hours 22:00–07:00; chỉ ghi khi bấm Lưu. Chi tiết nhắc phân biệt feed hiện tại và giờ kênh ngoài dự kiến, hiển thị timezone rõ ràng. Không suy luận giờ lái xe từ timestamp ODO.

Migration mới `e4b6c8d0f2a3` nối sau `c7d9b1e3f5a2`: settings giờ/timezone, các cột lịch/claim của delivery, index due và mốc email chưa rõ. Áp dụng trên đích Phase 2 riêng trước khi chạy backend/worker mới; khởi động lại worker và Beat để nhận task/lịch mới. Nhịp 15 phút là chu kỳ chọn việc, không phải SLA giao nhận: còn phụ thuộc hàng đợi, retry và provider.

Kiểm tra và các giới hạn rollout tại [bản kết quả và hướng dẫn](../../../../DRIVING_HABIT_RESULTS_AND_USAGE.md#verification).
