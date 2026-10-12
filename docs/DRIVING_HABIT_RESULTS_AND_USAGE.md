# Kết quả và cách sử dụng cho thành viên — Cá nhân hoá nhắc theo thói quen chạy xe

Cập nhật: **11/10/2026**, EV Care. **P1–P3 hoàn tất về chức năng và kiểm thử; có thể dùng thử/nghiệm thu. Rollout thật chưa hoàn tất.** Chủ dự án xác nhận chưa có API hãng thật và đã chọn diễn tập bằng dữ liệu thử. Đây là tài liệu bàn giao cho thành viên, gồm kết quả chính, cách sử dụng và hướng dẫn triển khai. Plan và bằng chứng chạy chi tiết được giữ cục bộ tại `docs/plans/DRIVING_HABIT_RUN_RESULTS.md`, không đưa vào bản push này.

## 1. Kết quả đã thực hiện

| Phần | Chức năng đã có | Lợi ích khi áp dụng |
|---|---|---|
| P1 — Nhắc theo mức sử dụng | Tính km/ngày từ lịch sử ODO, ước lượng ngày chạm mốc, kết hợp hạn theo thời gian, giải thích lý do, quyền bật/tắt/xoá dữ liệu suy ra | Xe chạy nhiều có thể được nhắc sớm; xe thiếu dữ liệu vẫn dùng luật cố định |
| P2 — Giờ nhận phù hợp | Chọn giờ nhận, giờ yên lặng, timezone; lưu lịch gửi/claim trong DB; kiểm tra lại trước gửi, retry theo lịch | Người dùng kiểm soát giờ nhận; worker phục hồi sau gián đoạn và hạn chế gửi trùng |
| P3 — Chuẩn bị trước chuyến đi | Khai báo ngày đi/về, tổng km dự kiến, bật nhắc chuyến; gợi ý bảo dưỡng trước chuyến, đọc sở thích đặt lịch khi được phép | Chủ xe chuẩn bị trước chuyến dài và chọn lịch bảo dưỡng phù hợp |
| Tích hợp | Chi tiết xe, cài đặt thông báo, feed/chi tiết lời nhắc, email, agent, luồng booking và metrics | Từ lý do nhắc sang bước đặt lịch có xác nhận của chủ xe |
| Quyền và vòng đời | API theo owner/xe, consent độc lập, cohort, huỷ lượt chờ khi mất điều kiện, giữ ID/receipt chống trùng | Giữ đúng phạm vi tài khoản và không gửi lại nội dung chuyến/dự báo đã bị thu hồi |

Km dự kiến của chuyến và forecast không được ghi thành ODO hãng. Không thu GPS hoặc suy ra tuyến đường. Agent không tự tạo booking. P3 lưu tối đa một kế hoạch hiện tại mỗi xe; kế hoạch được giữ tới khi chủ xe xoá hoặc thay thế, chưa tự xoá chuyến đã qua.

<a id="verification"></a>

### Triển khai và nghiệm thu

- Nghiệm thu P3 trước đồng bộ `develop`: **418 test backend / 27 suite** liên quan tính năng đạt; **190 test frontend / 36 file**, typecheck/build đạt. Không phải toàn bộ test repository. Kết quả kiểm tra sau đồng bộ ở mục 5.
- Browser P3 đạt 4 trường hợp mobile/desktop × light/dark; **0 vi phạm axe**, không tràn ngang. Auth/clock/email trong bài browser là fixture/mock.
- PostgreSQL schema thử kiểm tra bốn migration upgrade/downgrade/upgrade và concurrency: hai worker email/SMS chỉ một transport call ghi nhận cho mỗi loại, không giữ transaction qua transport.
- **Bốn migration đã áp dụng vào database thật trong `.env` gốc**, được xác nhận là đích Phase 2. Tracking tính năng ở `alembic_version_driving_habit`, head `f2a4c6e8b0d3`; giữ base revision cũ `d5b2e8f4a1c7`. Source base revision đã có lại từ `develop`. Source canonical sau đồng bộ có một head `9b7d3e1f5a6c`; database dùng tracking riêng vẫn cần đối chiếu schema/lịch sử trước khi chuyển sang luồng canonical.
- Worker Celery thật/Redis đã kiểm tra round-trip trên queue riêng, sau đó dừng worker thử. **Chưa xác nhận worker/Beat vận hành liên tục.**
- Một email test Resend thật được chấp nhận HTTP 200; người dùng xác nhận đã nhận thư. Đây là kiểm tra transport, không phải gửi reminder nghiệp vụ thật.
- Diễn tập **shadow → canary → rollback → bật lại** đạt **12 kiểm tra**, 8 tài khoản/8 xe, 14 ngày mô phỏng, 3 email mock, 0 kết nối mạng/LLM/provider thật trong lượt diễn tập.

Hồ sơ đối chiếu cục bộ gồm các báo cáo P1/P1.5/P2/P3, verification triển khai và diễn tập, được hợp nhất trong `docs/plans/DRIVING_HABIT_RUN_RESULTS.md`. Thành viên có thể chạy lại bài diễn tập ở mục 3 để kiểm tra logic trên dữ liệu thử.

## 2. Cách dùng trong ứng dụng

Các thao tác sau dùng backend thật `src.main:app` và frontend thật. Khi dự án được khởi động đúng cấu hình, truy cập `http://localhost:5173`; đăng nhập và hoàn tất onboarding, chọn xe đã xác minh. Quy ước khởi động có trong [AGENTS.md](../AGENTS.md). Không tự bật demo hoặc tạo dữ liệu hãng giả trên database nghiệp vụ để làm cho forecast hoạt động.

### P1 — Nhắc theo mức sử dụng xe

1. Vào **Thông báo → Cài đặt** (`/notifications/settings`). Bật nhắc bảo dưỡng tổng và chọn số ngày nhắc trước.
2. Bật **“Nhắc theo mức sử dụng xe”** rồi bấm **Lưu** để ghi nhận quyền sử dụng lịch sử ODO cho cá nhân hoá. Email/kênh nhận nhắc là lựa chọn riêng; bật cá nhân hoá không tự bật kênh email.
3. Vào **Chi tiết xe** (`/vehicle`) để xem mức sử dụng, ngày dự kiến chạm mốc và lý do/fallback. Chi tiết lời nhắc lưu snapshot tại thời điểm tạo, không dùng số liệu hôm nay để giả thành dữ liệu cũ.
4. Khi có gợi ý, chọn đặt lịch hoặc hỏi trợ lý; người dùng vẫn xác nhận booking.
5. Có thể tắt công tắc hoặc chọn **“Xoá dữ liệu suy ra đã lưu”**. Lịch sử ODO hãng và lịch sử bảo dưỡng vẫn được giữ; lượt forecast chưa gửi sẽ dừng theo guard.

Ví dụ minh hoạ: xe còn 1.200 km tới mốc, chạy khoảng 200 km/ngày, nhắc trước 7 ngày → dự kiến khoảng 6 ngày tới mốc, có thể nhắc sớm dù chưa vào ngưỡng km cố định. Nếu chỉ chạy 20 km/ngày, ước lượng khoảng 60 ngày, chưa nhắc theo forecast; hạn thời gian hoặc ngưỡng cố định vẫn có thể tạo nhắc.

Forecast cần ít nhất 3 ngày có quan sát trải trên 14 ngày, anchor còn mới và chuỗi không có gap/anomaly vượt quy tắc. **Hiện ODO static bị chặn và server ở `shadow`, nên dùng thử có thể hiển thị thiếu/không hỗ trợ dữ liệu; bật công tắc không tự mở gửi forecast thật.** Trong shadow, nhắc vẫn theo luật cố định.

### P2 — Chọn giờ nhận

1. Tại **Thông báo → Cài đặt**, bật **“Chọn giờ nhận nhắc”**, chọn giờ như **19:00**.
2. Nếu muốn, bật **“Bật giờ yên lặng”**, đặt **22:00–07:00**, chọn **Việt Nam (UTC+7)**.
3. Chọn kênh khả dụng, chẳng hạn Email, rồi bấm **Lưu**. Email thật cần địa chỉ đã xác minh và không bị suppression.
4. Feed xuất hiện khi đủ điều kiện tạo nhắc; kênh ngoài chờ tới giờ phù hợp. Nếu giờ nhận nằm trong giờ yên lặng, lịch chuyển tới khi khoảng yên lặng kết thúc.

Gửi tự động cần worker/Beat đang chạy cùng cấu hình với backend. Dispatcher tick mỗi 15 phút nên giờ chọn là thời điểm sớm nhất có thể gửi, không cam kết đúng từng phút. Chưa khởi động Beat nghiệp vụ trên nguồn static chỉ để thử chức năng; dùng bài diễn tập offline bên dưới để kiểm tra lịch gửi.

### P3 — Chuẩn bị trước chuyến đi

1. Vào **Chi tiết xe**, tìm thẻ **“Chuẩn bị trước chuyến đi”**.
2. Nhập ngày khởi hành, ngày về nếu có và tổng km cả đi/về. Ngày đi trong 365 ngày tới, km là số nguyên 1–20.000.
3. Nếu muốn nhận nhắc, chọn **“Nhắc bảo dưỡng trước chuyến đi này qua các kênh tôi đã bật”**, rồi bấm **“Lưu chuyến đi”**. Quyền này độc lập với quyền forecast P1.
4. Xem gợi ý mốc km/hạn thời gian. Nếu có sở thích đặt lịch được phép đọc, ứng dụng gợi ý xưởng active/ngày phù hợp; khả năng còn slot được kiểm tra trong luồng booking.
5. Chọn **“Chọn lịch bảo dưỡng trước chuyến đi”** và xác nhận lịch. Nếu đã có booking, mở lịch hẹn hiện có. Sửa/xoá kế hoạch sẽ dừng lượt chưa gửi liên quan đến nội dung chuyến cũ.

Ví dụ: ODO mới 10.800 km, mốc 12.000 km, dự kiến chuyến 1.500 km → cuối chuyến theo kế hoạch khoảng 12.300 km, ứng dụng gợi ý chuẩn bị bảo dưỡng trước ngày đi. Đây là ước lượng kế hoạch; ODO vẫn 10.800 km.

Preview có thể cộng mức sử dụng trước khởi hành nếu forecast đủ điều kiện và được phép. Nhắc tự động theo chuyến chỉ dùng ODO đã quan sát + km khai báo, cần nhắc tổng bật, kế hoạch bật nhận nhắc, mode hiệu lực `on`, đúng cohort và cửa sổ nhắc trước đã lưu. **Hiện mode `shadow` nên khai báo/gợi ý P3 dùng thử được, gửi tự động theo chuyến chưa mở.**

## 3. Cách kiểm tra ngay khi chưa có API hãng

Diễn tập offline không cần Redis, frontend, worker hoặc API hãng. Từ `backend/`:

```powershell
$env:APP_ENV = 'test'
$env:EMAIL_MODE = 'mock'
$artifactDir = '..\data\verification\driving-habit\latest'
New-Item -ItemType Directory -Path $artifactDir -Force | Out-Null
.\.venv\Scripts\python.exe scripts/rehearse_driving_habit_release.py --json "$artifactDir/release-rehearsal.json" --html "$artifactDir/release-rehearsal.html"
```

Mở `data/verification/driving-habit/latest/release-rehearsal.html` để xem kết quả. Mỗi lần tạo SQLite trong RAM mới; không ghi database `.env` và không gửi email thật. **14 ngày mô phỏng không thay thế shadow thật 2–4 tuần.**

Kết quả mới nằm trong `data/verification/` được Git ignore. Dùng terminal riêng cho diễn tập; khi chạy backend thật, dùng terminal mới để tránh giữ biến test/mock. Thành viên chỉ đọc nghiệm thu có thể xem bảng và bằng chứng ở bản tổng hợp kết quả chạy mà không cần chạy lại.

Khi có API hãng: kiểm tra nguồn/đồng bộ ODO thật → người dùng tự opt-in → chọn cohort → shadow thật → backtest, hiệu năng và acceptance review → canary → mở rộng. Audit gần nhất còn 0 xe ứng viên lịch sử, 0 owner opt-in, 0 xe có 14 ngày shadow; pipeline thật chưa đủ điều kiện. Forecast thử SQL 6.000 điểm P95 320,72 ms còn vượt mục tiêu 100 ms; chưa xác nhận SLA fleet. Xem [hướng dẫn phát hành](#rollout) trước khi bật gửi thật.

## 4. Bàn giao cho thành viên kỹ thuật

| Thành viên | Việc có thể làm ngay | Việc cần đủ điều kiện |
|---|---|---|
| Chủ xe/người nghiệm thu | Cài đặt quyền, giờ nhận, khai báo chuyến, xem preview và xác nhận booking | Forecast cần ODO đủ chất lượng; gửi tự động theo forecast/chuyến cần mode/cohort phù hợp |
| QA | Chạy diễn tập offline, xem các kết quả backend/frontend/browser trong hồ sơ chạy | Dùng dữ liệu và tài khoản được phép khi nghiệm thu dịch vụ thật |
| Backend/DevOps | Kiểm tra migration, audit/preflight, kết nối Redis/worker; giữ registry receipt | Kết nối OEM thật, shadow/cohort đủ điều kiện, review và triển khai scheduler liên tục |
| Frontend | Dùng các màn hình cài đặt/chi tiết xe/booking đã tích hợp; tái hiện browser smoke khi cần | Build và cấu hình proxy `/api` đúng backend trên môi trường triển khai |

Contract chi tiết: [P1](specs/phase2/personalization/driving-habit/driving-habit-reminders-phase2-spec.md), [P2](specs/phase2/personalization/driving-habit/driving-habit-send-schedule-phase2-spec.md), [P3](specs/phase2/personalization/driving-habit/driving-habit-trip-reminders-phase2-spec.md). Bản hướng dẫn này cùng các spec được chia sẻ trong repository; plan và báo cáo chạy trong `docs/plans/` được giữ cục bộ.

### Migration cho đích hiện tại

Source của base revision `d5b2e8f4a1c7` đã có lại sau đồng bộ `develop`. Database hiện tại đã áp dụng tính năng bằng `alembic_version_driving_habit`, nên việc tìm lại source không tự hợp nhất hai bảng tracking. **Không tự stamp hoặc chạy lại migration tạo các bảng tính năng đã có**. Với đích này, dùng runner feature đã nghiệm thu; kiểm tra trước, chỉ áp dụng khi đúng database Phase 2 được xác nhận. Từ `backend/`, terminal cấu hình thật:

```powershell
$artifactDir = '..\data\verification\driving-habit\latest'
New-Item -ItemType Directory -Path $artifactDir -Force | Out-Null
.\.venv\Scripts\python.exe scripts/deploy_driving_habit_migrations.py --output "$artifactDir/migration-check.json"

# Trên đúng đích Phase 2; bốn migration hiện đã áp dụng, head là no-op.
.\.venv\Scripts\python.exe scripts/deploy_driving_habit_migrations.py --apply --phase2-target-confirmed --output "$artifactDir/migration-apply.json"
```

Database có lịch sử canonical đầy đủ và không dùng tracking tính năng riêng vẫn dùng Alembic bình thường. Cần đối chiếu schema và hai luồng tracking của đích hiện tại trước khi hợp nhất lịch sử. Migration `9b7d3e1f5a6c` chỉ gộp hai head source, không thay đổi schema hoặc áp dụng migration vào database trong lượt sửa conflict này. Rollback vận hành dùng mode `off`, giữ schema và receipt chống trùng. Không xoá `data/verification/driving-habit/provider-receipts/` để thử lại email: một email thật trước đó đã được người nhận xác nhận, không cần gửi lại trong việc bàn giao này.

<a id="rollout"></a>

### Phát hành thật

1. Cấu hình API OEM hợp lệ, đồng bộ và thu lịch sử đủ điều kiện; chạy audit/backtest trên dữ liệu thật.
2. Người dùng tự opt-in; xác định user ID số cho cohort. Email đã nhận thư thử không tự cấp quyền cá nhân hoá.
3. Vận hành shadow 2–4 tuần; kiểm tra đủ ít nhất 14 ngày quan sát, chất lượng dự báo, hiệu năng fleet và acceptance. Shadow vẫn giữ baseline gửi thật nếu cấu hình Resend, nên cần quản lý worker/Beat như dịch vụ nghiệp vụ.
4. Mở `on` trong cohort, theo dõi canary rồi mở rộng. Khi bất thường, chuyển `off`; các lượt chờ được kiểm tra lại điều kiện, receipt giữ nguyên.

Kế hoạch chuyến lưu tối đa một kế hoạch mỗi xe và chưa có tác vụ tự xoá chuyến đã qua. Xoá/sửa chuyến dừng nội dung cũ chưa gửi; thư đã gửi không thể thu hồi. Gợi ý ngày/xưởng không bảo đảm còn slot, dự báo không thay thế kiểm tra tình trạng xe.

## 5. Kiểm tra sau đồng bộ develop

Đã gộp `develop` tại `5697dfe` vào nhánh tính năng, giữ cả lựa chọn gói bảo dưỡng, liên kết booking–reminder và giải phóng transaction trước khi chờ Redis. Tài khoản demo dùng chung vẫn không được sửa cài đặt nhắc/cá nhân hoá/giờ nhận hoặc xoá dữ liệu suy ra.

- **286 test nghiệp vụ / 14 suite đạt**, gồm booking, gói bảo dưỡng, notification, demo, agent và chuyến đi; **8 test migration / 2 suite đạt**. Tổng 294 test trong phạm vi kiểm tra merge, không phải toàn repository.
- **253 test frontend / 42 file**, typecheck và build đạt; còn cảnh báo bundle trên 500 kB.
- Ruff check/format đạt cho các file xử lý conflict và test bổ sung. Migration gộp `9b7d3e1f5a6c` giữ hai nhánh lịch sử và đưa source về một head duy nhất.
- Thêm kiểm tra kết hợp chọn gói với nguồn reminder và transaction qua Redis, chặn tài khoản demo sửa các trường mới, kiểm tra migration graph giữ đủ hai nhánh.

Kiểm thử dùng SQLite/fake Redis/mock transport, không gọi LLM/provider thật và không áp migration lên database `.env`. Rollout thật vẫn ở trạng thái chờ điều kiện trong mục 4.
