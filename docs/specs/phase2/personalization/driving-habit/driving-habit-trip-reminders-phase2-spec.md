# P3 — Nhắc bảo dưỡng trước chuyến đi

Ngày thực hiện: 11/10/2026. Áp dụng cho backend thật `src.main:app`, frontend thật và các tác vụ nhắc hiện có. Database trong `.env` gốc đã được chủ dự án xác nhận là đích Phase 2.

## Dữ liệu và API

Mỗi xe có tối đa một kế hoạch chuyến đi hiện tại trong `vehicle_trip_plan`. Chủ xe nhập ngày khởi hành, ngày về tùy chọn, tổng quãng đường cả đi/về và lựa chọn nhận nhắc. Không thu GPS, điểm đến, tuyến đường; không sửa ODO, lịch sử hãng hoặc trạng thái đến hạn đã quan sát.

`GET`, `PUT`, `DELETE /api/v1/user-vehicles/{userVehicleId}/trip-plan` yêu cầu Firebase identity, onboarding và quyền sở hữu xe đã xác minh, đang active. Response dạng `{ "data": plan | null }`, field camelCase. API không cho xem kế hoạch của chủ cũ sau chuyển quyền xe.

Ví dụ PUT:

```json
{
  "departureDate": "2026-10-14",
  "returnDate": "2026-10-18",
  "distanceKm": 1500,
  "reminderEnabled": true
}
```

Ngày khởi hành từ hôm nay đến 365 ngày tới theo UTC+7. Ngày về không trước ngày đi, thời lượng tối đa 365 ngày. Quãng đường là số nguyên từ 1 đến 20.000 km; boolean phải đúng kiểu, field lạ bị từ chối. Backend thật trả HTTP 400 cho input không hợp lệ theo handler hiện có; fixture FastAPI không dùng handler đó có thể trả 422. Không có kế hoạch trả `data: null`; DELETE lặp lại vẫn trả `data: null`. PUT cùng nội dung giữ nguyên kế hoạch và không huỷ delivery.

Migration `f2a4c6e8b0d3` bổ sung bảng và constraints, sau `e4b6c8d0f2a3`.

## Gợi ý và quyền dữ liệu

Gợi ý xét mốc bảo dưỡng tiếp theo từ luật hãng. Nếu ODO còn mới, số km cuối chuyến theo kế hoạch = ODO đã quan sát + tổng km chuyến đi. Preview có thể cộng km/ngày × số ngày trước khởi hành, chỉ khi forecast hợp lệ, chủ xe đã đồng ý cá nhân hoá và khởi hành trong 90 ngày. Phần cộng này là ước lượng tư vấn, không ghi thành ODO.

Các lý do: `TRIP_KM_MILESTONE` khi số km dự kiến >= mốc; `TRIP_TIME_DEADLINE` khi hạn thời gian rơi trước/trong chuyến; `OBSERVED_OVERDUE` khi dữ liệu thật đã quá hạn. Gợi ý chuẩn bị trước ngày đi một ngày, không lùi trước hôm nay. Không đủ luật/ODO mới thì trả trạng thái giải thích; kết quả chưa vượt mốc không phải chứng nhận an toàn xe. Ngày khởi hành đã qua trả `DEPARTED` và không kích hoạt nhắc chuyến.

Nhắc tự động theo chuyến **chỉ dùng ODO đã quan sát + quãng đường khai báo**, không dùng phần forecast bổ sung của preview. Phải có `reminderEnabled=true` trên kế hoạch, nhắc tổng bật, mode hiệu lực `on`, tài khoản thuộc cohort khi cấu hình canary, và ngày đi trong cửa sổ lead days đã lưu. Nhắc chuyến là quyền sử dụng kế hoạch chủ xe chủ động khai báo; không thay thế hoặc tự cấp consent dùng lịch sử ODO để forecast. Mode `shadow`/`off` không thêm trigger chuyến đi; gợi ý vẫn đọc được.

Sở thích đặt lịch chỉ đọc qua guard của preference memory: đồng ý sử dụng, read flag, cohort, chưa hết hạn, đúng owner/vehicle. Sở thích cấp xe ưu tiên cấp tài khoản. Xưởng chỉ được gợi ý nếu còn active. Ngày gợi ý theo thứ đã lưu phải không muộn hơn ngày chuẩn bị; không khẳng định slot trống. Link booking truyền xe, mốc, xưởng/ngày phù hợp; người dùng vẫn chọn slot và xác nhận. Nếu đã có booking cho mốc thì dẫn tới lịch hẹn hiện có.

## Vòng đời và giao nhận

Trigger chuyến đi dùng policy, feed, template, lịch gửi P2 và kiểm tra lại trước transport của luồng nhắc hiện có. Mức `EXPIRED` theo dữ liệu thật ưu tiên hơn nhắc sớm. Giữ unique `(vehicle, milestone, level)` và delivery ID; không tạo email mới chỉ vì sửa kế hoạch hoặc thêm chuyến khác ở cùng mốc đã nhắc. Email đã gửi không được phát lại dưới ID mới.

Sửa kế hoạch huỷ lượt chưa gửi có snapshot chuyến cũ, không thay payload retry đã đóng băng, không reset số lần thử. Snapshot có thể gồm cả lý do P1 và chuyến đi; huỷ cả delivery kết hợp để không gửi nội dung chuyến cũ. Lịch sử giữ nguyên ID; các mức/mốc tiếp theo tiếp tục theo policy hiện có. Nhắc đã tạo không được gửi nếu đến lúc dispatch chuyến đã qua, không còn điều kiện, bị tắt hoặc đã có booking.

DELETE xoá kế hoạch hiện tại, xoá phần chuyến trong snapshot và body/recipient của email outbox liên quan, dừng lượt chưa gửi. Giữ receipt/status/ID đã gửi để chống trùng; không thu hồi thư đã tới provider. Chi tiết feed hiển thị dữ liệu chuyến đã xoá. Kế hoạch được giữ tới khi chủ xe xoá/thay thế; chưa có tác vụ tự xoá kế hoạch đã khởi hành.

Agent có tool đọc `get_planned_trip`, dùng xe/owner trong session, không tự khai báo chuyến đi và không tự tạo booking. Không gọi LLM trong vòng quét nhắc.

## Nghiệm thu và phát hành

Kiểm thử SQLite kiểm tra projection, input, guard, consent, expiry, sửa/xoá, idempotency, lịch gửi, preference và tool. API thật kiểm tra auth/owner/input. PostgreSQL thử trong schema tạm kiểm tra bốn migration và concurrency của luồng delivery. UI kiểm tra mobile/desktop, hai theme, keyboard, reload, axe và mock dispatch một lần.

Migration thật và worker/provider kiểm tra riêng theo [báo cáo triển khai](../../../../DRIVING_HABIT_RESULTS_AND_USAGE.md#verification). Chưa đưa canary vào vận hành khi nguồn OEM vẫn static, không có consent/cohort hoặc chưa có 14 ngày shadow. Không dùng dữ liệu fixture để hoàn thành điều kiện rollout thật.
