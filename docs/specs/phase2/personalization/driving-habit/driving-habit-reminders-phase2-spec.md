# Cá nhân hoá nhắc theo mức sử dụng xe — contract P1

Trạng thái: Review. Feature tạm: `DRIVING-HABIT-REMINDER`.
Nguồn: [kết quả và hướng dẫn tính năng](../../../../DRIVING_HABIT_RESULTS_AND_USAGE.md).
Mở rộng F3/F7 của MVP và liên quan PL-01/PS-03; chưa cấp mã PS mới.

## Hành vi

- Quyền cá nhân hoá mặc định tắt ở cấp chủ xe, độc lập nhắc tổng, Email và bộ nhớ agent.
- Chỉ dùng ODO đã quan sát từ hãng, không ghi ODO dự đoán vào lịch sử nguồn.
- Lấy điểm cuối mỗi ngày Việt Nam trong 30 ngày, dùng đoạn liên tục hợp lệ cuối cùng.
- Đủ dữ liệu: ít nhất 3 ngày có điểm đo, độ phủ 14 ngày, khoảng trống tối đa 7 ngày, anchor không quá 7 ngày tuổi.
- Tốc độ = tổng km tăng / thời gian quan sát thực. Ngày không tăng km được tính trong khoảng quan sát; thiếu điểm đo không được coi là đứng xe.
- Loại khoảng ODO giảm, tốc độ vượt `USAGE_MAX_DAILY_KM` (mặc định 1000), timestamp tương lai hoặc anchor không trùng ODO hiệu lực của F3.
- Khi tốc độ 14 ngày gần nhất lệch quá hệ số 2 so với cả đoạn, kết quả `LOW_CONFIDENCE`.
- Ngày km dự kiến tính từ thời gian đo anchor và số km còn lại; horizon tối đa 90 ngày từ anchor. Không chia cho 0 khi xe đứng.
- Ngày dự kiến qua rồi chỉ đánh dấu `possiblyReached`; không đổi trạng thái bảo dưỡng chính thức sang `OVERDUE`.
- ODO static bị chặn. Quá 6000 snapshot trong cửa sổ trả `DATA_LIMIT`, không lấy tuỳ tiện đoạn bị cắt để dự báo.
- `off`: không cung cấp forecast. `shadow` (mặc định): tính forecast có consent, log so sánh nhưng gửi theo luật cố định. `on`: bổ sung điều kiện ngày km dự kiến nằm trong cửa sổ nhắc trước.
- `PERSONALIZED_REMINDERS_CANARY_USER_IDS`: danh sách ID chủ xe nguyên dương, phân cách bằng dấu phẩy. Khi server `on` và danh sách không rỗng, chỉ người trong danh sách có mode hiệu lực `on`; người ngoài dùng `shadow`. Danh sách rỗng áp dụng `on` cho mọi người đã opt-in. Không cấp consent từ danh sách; cấu hình sai bị từ chối khi khởi động. Mode `off`/`shadow` luôn ưu tiên hơn danh sách.
- Một mốc vẫn tối đa một `EARLY` và một `EXPIRED`. Booking, cooldown, suppression, lease và idempotency tiếp tục áp dụng.
- Job và adapter Email dùng cùng policy. Lỗi cục bộ khi đọc lịch sử/tính forecast trả `CALCULATION_ERROR`, giữ luật cố định. Lỗi schema/cài đặt đồng ý vẫn được báo để phát hiện migration chưa chạy.

## API chủ xe

Các API dùng danh tính Firebase và guard owner hiện có. Không nhận user ID hoặc vehicle ID khác để thay quyền. JSON camelCase, envelope `data`.

`GET /api/v1/notification-settings` thêm:

| Field | Ý nghĩa |
|---|---|
| `personalizedRemindersEnabled` | Có đồng ý đang hiệu lực cho policy hiện tại |
| `personalizationAvailable` | Server không ở mode `off` |
| `personalizationMode` | `off`, `shadow`, `on` hiệu lực theo chủ xe, có xét canary |
| `personalizationPolicyVersion` | `driving-usage-2026-10-v1` |
| `personalizationConsentAt` | Thời gian đồng ý, nullable |

`PUT /api/v1/notification-settings` thêm field tùy chọn:

```json
{
  "personalizedRemindersEnabled": true,
  "personalizationPolicyVersion": "driving-usage-2026-10-v1"
}
```

Bật thiếu/sai phiên bản: HTTP 400 `PERSONALIZATION_CONSENT_REQUIRED`. Bật khi mode `off`: HTTP 400 `PERSONALIZATION_UNAVAILABLE`. Tắt chỉ cần boolean false. Bỏ field không thay quyền. Không tự bật nhắc tổng hoặc Email. Gửi boolean strict; field thừa bị từ chối.

`DELETE /api/v1/notification-settings/personalization-data` thu hồi quyền, huỷ delivery cá nhân hoá chưa gửi, xoá forecast snapshot/payload lưu ở EV Care, trả settings mới trong cùng transaction. Giữ ODO hãng, lịch sử dịch vụ, ID và metadata chống trùng. Tài khoản chưa đăng ký trả 404; chưa hoàn thành onboarding trả 403 theo guard MVP.

Response trạng thái bảo dưỡng thêm `maintenanceForecast` nullable:

| Field | Kiểu / ý nghĩa |
|---|---|
| `status` | `DISABLED`, `UNSUPPORTED_DATA_SOURCE`, `INSUFFICIENT_DATA`, `STALE_DATA`, `ANOMALOUS_DATA`, `LOW_CONFIDENCE`, `DATA_LIMIT`, `CALCULATION_ERROR`, `AVAILABLE` |
| `quality` | `SUFFICIENT` khi AVAILABLE, còn lại null |
| `avgKmPerDay` | Tốc độ quan sát, nullable; không phải ODO ước lượng |
| `observationDays`, `sampleDays` | Độ phủ thời gian / số ngày có điểm đo |
| `anchorRecordedAt` | Timestamp điểm ODO cuối, nullable |
| `kmForecastDate` | Ngày dự kiến chạm km, nullable |
| `officialTimeDueDate` | Hạn theo thời gian của hãng, nullable |
| `projectedDueDate`, `basis` | Ngày sớm hơn giữa hai mốc; `KM_FORECAST` hoặc `TIME_ONLY` |
| `possiblyReached` | Forecast có thể đã chạm mốc; cần ODO mới xác nhận |
| `reminderRecommended` | Policy đang bật nhắc dự báo và chưa có booking phù hợp |
| `reminderLeadDays` | Số ngày chủ xe chọn, nullable |
| `algorithmVersion`, `calculatedAt` | `usage-v1` / timestamp tính |

Các field bảo dưỡng cũ không đổi. Tool maintenance trả cùng model theo cách serialize hiện có; agent phải phân biệt forecast với hạn chính thức.

## Lưu trữ và kiểm soát

Migration `a9c4e2f6b8d1` sau `f8b2d6a4c1e9` thêm bốn cột settings và bảng `reminder_personalization_event`: chủ xe, action, phiên bản policy, nguồn, timestamp. Action gồm `GRANTED`, `REVOKED`, `DERIVED_DATA_DELETED`.

Migration `c7d9b1e3f5a2` sau `a9c4e2f6b8d1` thêm `reminder_policy_evaluation` và `reminder_booking_attribution`. Evaluation lưu tối đa một kết quả/xe/ngày Việt Nam/mode, gồm trạng thái chất lượng, level baseline/candidate/actual, phiên bản thuật toán và latency; chỉ ghi cho consent còn hiệu lực. Không lưu raw ODO trace. Evaluation giữ 90 ngày và được xoá cùng dữ liệu suy ra.

Luồng đặt lịch giữ `sourceReminderId` trong query và gửi `sourceReminderId` tùy chọn ở `POST /api/v1/bookings`. Backend kiểm tra đúng chủ xe, xe và mốc; ngữ cảnh không hợp lệ trả 400 `INVALID_REMINDER_CONTEXT`. Lời nhắc đã cũ nhưng đúng xe/mốc vẫn cho đặt lịch, chỉ không được attribution. Khoảng 7 ngày tính từ lời nhắc tới **lúc tạo booking**; chỉ ghi `confirmedAt` sau chuyển trạng thái `CONFIRMED`, kể cả xưởng xác nhận muộn. Mỗi booking tối đa một attribution. `DIRECT` là ID nguồn được client gửi và server kiểm tra; `RECENT_REMINDER` là tương quan theo xe/mốc/thời gian. Không kết luận quan hệ nhân quả, không coi click hoặc hold là conversion.

Không thêm profile ODO hay cache backend. Snapshot reminder thêm `snapshotVersion: 2`, `policyVersion`, `triggerReasons`. Chỉ nhắc có reason `PREDICTED_KM_WINDOW` lưu `personalization` và dùng template `maintenance-usage-v1`; snapshot cũ vẫn đọc được.

Snapshot forecast giữ tối đa 90 ngày, consent event 365 ngày; payload Email theo cấu hình hiện có (mặc định 30 ngày). Job purge Email hiện có thực hiện retention mới. Xoá chủ động có hiệu lực sớm hơn.

Tạo reminder và thay quyền dùng chung lock chủ xe; huỷ gửi dùng gate Email theo xe. Trước gửi kiểm tra lại quyền, kênh, trạng thái xe/chủ, mốc, booking và policy hiện tại. Payload đã gửi không viết lại khi retry. Email đã bắt đầu gọi provider không thể thu hồi; bản lưu ở EV Care vẫn được xoá.

FE huỷ cache maintenance/reminder và bỏ response đang bay từ trước thay quyền. Context HTTP/tool không trả phần forecast cũ khi consent mất hiệu lực. Re-enable không reset delivery đã gửi hoặc đã huỷ.

## Giao diện và agent

Trang cài đặt giải thích dữ liệu, công tắc cần bấm Lưu, hiển thị mode shadow và dialog xác nhận xoá. Thẻ xe hiển thị mức km/ngày, ngày dự kiến, nguồn ODO và trạng thái thiếu dữ liệu. Chi tiết nhắc dùng snapshot tại lúc tạo.

Agent đọc forecast qua tool, không suy ra GPS, giờ lái hoặc dữ liệu sạc từ timestamp ODO; hướng dẫn bật trong Cài đặt thông báo. Không tự bật cá nhân hoá từ câu hỏi tư vấn hoặc tự tạo booking.

## Nghiệm thu và giới hạn

Test thuần, API, service SQL với transport ghi nhận, migration SQLite/PostgreSQL và worker đồng thời nằm trong [báo cáo triển khai](../../../../DRIVING_HABIT_RESULTS_AND_USAGE.md#verification).

Đã nghiệm thu tự động UI 390/1280 px ở hai theme, keyboard/dialog, accessibility bằng axe, cache sau xoá, API/booking attribution và dashboard shadow fixture. Backtest offline có kiểm tra không dùng quan sát tương lai để tính forecast và không chấm điểm ca chưa quan sát chạm mốc. Script JSON/HTML tổng hợp chỉ đọc, không có endpoint analytics công khai cho chủ xe.

Chưa nghiệm thu độ chính xác trên dữ liệu OEM thực, giao email qua provider thật, screen reader thực hoặc shadow/canary trên cohort vận hành. Giờ nhận/quiet hours thuộc P2 của plan, đã triển khai theo [contract P2](driving-habit-send-schedule-phase2-spec.md). Canary cần dữ liệu đủ chất lượng và đánh giá latency/full scan trên môi trường triển khai.

Cập nhật P1.5: preflight chỉ đọc kiểm tra migration, audit ODO mới trong một giờ, consent phiên bản hiện tại, cohort và số ngày shadow. Không tự bật flag hoặc coi điều kiện kỹ thuật là phê duyệt phát hành. [Bằng chứng lượt thực hiện](../../../../DRIVING_HABIT_RESULTS_AND_USAGE.md#verification) gồm kiểm tra canary, scan 40 xe fixture và service PostgreSQL 6.000 snapshot. P95 với 6.000 snapshot chưa đạt mục tiêu thử 100 ms; cần xử lý trên môi trường/quy mô mục tiêu trước mở rộng.
