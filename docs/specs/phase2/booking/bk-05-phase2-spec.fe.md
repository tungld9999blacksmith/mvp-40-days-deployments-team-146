# Frontend Technical Specification — Bản đồ xưởng (Google Maps)

> Frontend cho Feature `FEAT-P2-BK05` (SCR-BK05-01..03).
>
> **Nguồn nghiệp vụ:** [Functional Spec](bk-05-phase2-spec.ff.md). **API:** [API Spec](bk-05-phase2-spec.api.md) (`API-BK05-01..04`; "Đặt ở đây" = `API-BK01-05`).
>
> **Nguyên tắc:** bản đồ là lớp hiển thị; số chỗ, khoảng cách, thời gian đều từ backend. Bản đồ lỗi thì danh sách luôn đặt lịch được (AC-BK05-01). Không thêm dependency npm: Google Maps JavaScript API tải bằng thẻ `<script>` động.

---

## 1. Document Information

| Field | Value |
|---|---|
| Document ID | `FE-SPEC-P2-BK05` |
| Version | `v0.1` |
| Status | `Draft` |
| Screens | SCR-BK05-01 (trang), SCR-BK05-02 (thẻ / sheet), SCR-BK05-03 (danh sách dự phòng) |
| Routes | `/booking/map` (mới, trong `BookingLayout`) |
| Feature folder | `frontend/src/features/workshop-map/` (mới) |
| Created Date | `2026-10-12` |

---

# 2. Components

## 2.1 Điểm vào

| Nơi | Hành vi |
|---|---|
| Wizard Đặt lịch | Tab "Danh sách / Bản đồ" ở bước chọn xưởng (`BookingWorkshops`) và ở `/booking/options` (BK-01); tab Bản đồ → `/booking/map` |
| Chat chip "Chọn trên bản đồ" (CH-01) | Mở `/booking/map?from=chat&conversationId=…`; "Đặt ở đây" chạy BK-01 rồi quay lại hội thoại với thẻ `SCHEDULE_OPTIONS` (`trigger = MAP`, `conversationId` để backend gắn thẻ) |
| Thói quen đặt lịch (BK-01) | "Chọn trên bản đồ" cho xưởng yêu thích: chế độ `mode=pick`, nút thẻ là "Chọn làm xưởng yêu thích" |

## 2.2 `WorkshopMapPage` (SCR-BK05-01)

| Vùng | Nội dung |
|---|---|
| Thanh trên | `DayStrip` (tái dùng `SlotPicker.tsx`, mặc định hôm nay, 14 ngày) + chip lọc: "Còn chỗ", "Đang mở cửa", "Đánh giá ≥ 4", "Có phụ tùng" (chỉ khi BK-09 bật) + nút "Danh sách" |
| Bản đồ | Chấm "Bạn" ở tâm khi `anchor = DEVICE`; ghim xưởng: nhãn số `remainingCapacity` (`font-mono`), nền `bg-brand` khi > 0, xám + "0" khi hết (vẫn bấm được, BR-BK05-01); xưởng yêu thích viền đậm |
| Cụm | Ghim gần nhau gom cụm bằng hàm thuần `clusterPins(pins, zoom)` (lưới theo pixel, không thư viện); bấm cụm ⇒ zoom vào (EDGE-BK05-01) |
| Ngoài vùng | `nearestOutside` ⇒ thẻ nổi "Xưởng gần nhất cách {km} km" + nút "Xem" (EDGE-BK05-02) |
| `truncated` | Dòng "Phóng to để xem đủ xưởng" |

**Điểm neo (BR-BK05-05):** khi mở, `useConsentGate('CONSENT_LOCATION', 'BK-05')`; đồng ý ⇒ `getCurrentPosition` (timeout 5 s) ⇒ `anchor = DEVICE`; từ chối / lỗi ⇒ `PROFILE` (backend dùng địa chỉ đã lưu) ⇒ không có thì `CITY`. Toạ độ thiết bị chỉ gửi trong request, không lưu.

**Tải dữ liệu:** `API-BK05-01` khi mở, đổi ngày, đổi lọc, và khi bản đồ dừng pan/zoom 400 ms (`bbox`). Đổi ngày cập nhật số trên mọi ghim (AF-BK05-02).

## 2.3 `WorkshopMapCard` (SCR-BK05-02)

Bấm ghim ⇒ sheet đáy (390 px) / thẻ nổi cạnh ghim (≥ `md`):

| Dòng | Nguồn |
|---|---|
| Tên, "Xưởng yêu thích" | `name`, `isPreferred` |
| Địa chỉ, "Hôm nay mở 08:00–17:30" / "Đóng cửa hôm nay" | `address`, `openToday` |
| Đánh giá "4,6 ★ (18)" | `rating` (ẩn khi `null`) |
| "3,4 km · 12 phút · còn 5 chỗ" | `distanceKm`, `API-BK05-02` (`durationMin`; `null` ⇒ bỏ "· 12 phút"), `remainingCapacity` |
| Nút | "Đặt ở đây" (primary) ⇒ `runScheduler({ trigger: 'MAP', overrides: { workshopId }, applyAutomation: true })` ⇒ `ScheduleOptionsList`; "Chỉ đường" (secondary) ⇒ mở `https://www.google.com/maps/dir/?api=1&destination={lat},{lng}` tab mới (BR-BK05-04) |

Thời gian di chuyển: gọi `API-BK05-02` một lần cho tối đa 10 xưởng gần nhất đang hiển thị (không gọi theo từng ghim) và khi mở thẻ của xưởng chưa có.

## 2.4 `WorkshopListFallback` (SCR-BK05-03)

Danh sách thẻ (tái dùng `features/bookings/components/WorkshopCard.tsx`) sắp theo khoảng cách, cùng dữ liệu `API-BK05-01`, cùng nút "Đặt ở đây" / "Chỉ đường". Dùng khi:
- `mapsEnabled = false` (`/maps/config`), hoặc
- tải script Google lỗi / timeout 8 s, hoặc `gm_authFailure` (EF-BK05-01) ⇒ banner "Bản đồ tạm thời không tải được" + danh sách,
- chủ xe bấm "Danh sách".
Khoảng cách chim bay vẫn hiện; thời gian di chuyển chỉ khi API trả (EF-BK05-02).

## 2.5 Tải Google Maps

`features/workshop-map/loadGoogleMaps.ts`: chèn `<script src="https://maps.googleapis.com/maps/api/js?key={browserKey}&v=weekly&loading=async&libraries=marker&language=vi&region=VN&callback=…">` một lần (singleton promise), timeout 8 s. Gọi `POST /maps/usage` một lần sau khi bản đồ khởi tạo xong. `mapId` theo theme (sáng / tối) từ `/maps/config`. Script là tài nguyên ngoài nên giữ trong lazy chunk của route `/booking/map`.

---

# 3. API Integration & Errors

`features/workshop-map/api.ts`: `getMapConfig`, `getMapWorkshops`, `getTravelTimes`, `reportMapLoad`.

| API | Lỗi | Xử lý |
|---|---|---|
| BK05-01 | `RATE_LIMITED` | Giữ ghim hiện tại, thử lại sau `retryAfter` |
| BK05-01 | Mạng / 5xx | Lỗi trong bản đồ + "Thử lại"; nút "Danh sách" vẫn dùng được với lần tải trước |
| BK05-02 | `degraded` / `limited` | Ẩn thời gian di chuyển, không báo lỗi |
| BK05-03 | Lỗi | Coi như `mapsEnabled = false` ⇒ danh sách |
| BK01-05 | Theo BK-01 FE §3 | |

---

# 4. States

| State | UI |
|---|---|
| Đang tải script / ghim | Khung bản đồ skeleton + danh sách skeleton phía dưới trên mobile |
| 390 px | Bản đồ 60 % chiều cao, thanh lọc cuộn ngang, thẻ xưởng là bottom sheet |
| Desktop xl | Bản đồ 2/3, danh sách xưởng trong vùng ở rail 1/3 (DESIGN.md context rail) |
| Dark theme | `mapId` tối; ghim dùng token màu của theme |

---

# 5. Acceptance Criteria (FE)

1. Script bản đồ lỗi ⇒ trong ≤ 8 s chuyển danh sách và đặt lịch được (AC-BK05-01).
2. Ghim hết chỗ vẫn mở thẻ và "Đặt ở đây" bấm được.
3. Không gửi toạ độ thiết bị khi chủ xe chưa đồng ý PL-01.
4. `POST /maps/usage` đúng một lần mỗi lần khởi tạo bản đồ.
5. Không thêm dependency npm; `npm test`, `npx tsc --noEmit -p .` qua; hai theme, 390 px.

---

# 6. Tests (Vitest)

| File | What | Count |
|---|---|---|
| `workshop-map/cluster.test.ts` | `clusterPins` gom đúng theo zoom; một ghim không tạo cụm | +3 |
| `workshop-map/pinView.test.ts` | `pinView(workshop)` → nhãn số, xám khi 0, yêu thích | +3 |
| `workshop-map/cardLine.test.ts` | Dòng "km · phút · chỗ" khi thiếu phút / khoảng cách | +3 |
| `workshop-map/anchor.test.ts` | `resolveAnchor(consent, position, profile)` | +3 |
| `workshop-map/directionsUrl.test.ts` | URL chỉ đường đúng định dạng | +1 |
| `workshop-map/loadGoogleMaps.test.ts` | Singleton: gọi hai lần chỉ chèn một script (DOM giả tối thiểu bằng đối tượng `document` stub) | +1 |

---

# 7. Truy vết FF → FE

| FF | FE |
|---|---|
| UC-BK05-01, BR-BK05-05 | §2.1, §2.2 |
| UC-BK05-02, BR-BK05-02, AF-BK05-01/02 | §2.2 |
| UC-BK05-03, BR-BK05-06, AF-BK05-03 | §2.3 |
| UC-BK05-04, BR-BK05-04 | §2.3 |
| EF-BK05-01/02/03, AC-BK05-01 | §2.4 |
| EDGE-BK05-01/02 | §2.2 |

---

# 8. Analytics

`map_opened` (`entry`, `anchor`), `map_filter_toggled` (`filter`), `map_pin_opened` (`remainingCapacity`, `hasTravelTime`), `map_book_here` , `map_directions_clicked`, `map_fallback_shown` (`reason`). Không gửi toạ độ.

---

# 9. Change Log

| Version | Date | Change |
|---|---|---|
| `v0.1` | `2026-10-12` | Bản nháp đầu |
