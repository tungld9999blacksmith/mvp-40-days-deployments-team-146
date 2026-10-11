# workshop_crawl — Crawl vị trí xưởng ô tô thật tại Việt Nam (Amazon Location / Google Places)

Tool dòng lệnh (Python, chỉ dùng thư viện chuẩn) lấy khoảng **1000 xưởng ô tô có thật**, rải đều trên
**34 tỉnh/thành** (đơn vị hành chính từ 01/07/2025). Có 2 nguồn dữ liệu, chọn bằng `--source`:

| Nguồn | API | Ghi chú |
|---|---|---|
| `aws` (**mặc định**) | Amazon Location Service — Places v2 `SearchText` | Không cần nạp trước như Google; có credit cho tài khoản AWS mới |
| `google` | Google Places API (New) — Text Search | Dữ liệu gara VN tốt nhất; tài khoản billing ở VN bị yêu cầu nạp trước (prepayment) |

Kết quả được nạp vào bảng `service_centers` của [mock-ev-system](../../backend/mock-ev-system/README.md),
tức là nguồn dữ liệu "của hãng" (OEM).

```
tools/workshop_crawl/
  .env.example           mẫu cấu hình (copy thành .env)
  workshop_crawl.py      CLI: plan, crawl, stats, import
  places.py              phần chung: cache trên đĩa, retry, định dạng place đã chuẩn hoá
  aws_places.py          client Amazon Location (Places v2 SearchText)
  google_places.py       client Google Places API (New)
  provinces.py           34 tỉnh/thành + bảng tên tỉnh cũ → mới
  test_workshop_crawl.py test offline (không gọi API)
  data/                  file sinh ra + cache (git-ignored)
```

> Tool chỉ dùng **API chính thức**, không scrape trang bản đồ. Scrape vi phạm điều khoản, hay bị
> chặn/captcha và dễ hỏng khi giao diện thay đổi.

---

## 1. Dữ liệu đi đâu

```
Places API  ──crawl──▶ data/workshops.json ──import──▶ mock-ev-system: service_center
                                                          (address, latitude, longitude, place_id)
                                                                │  verify-manager (OEM)
                                                                ▼
                                       backend: workshop.latitude / longitude khi chủ xưởng onboarding
                                                                │
                                                                ▼
                                       gợi ý xưởng gần chủ xe (haversine, booking/location.py)
```

- `service_center` của mock có thêm 4 cột nullable: `address`, `latitude`, `longitude`, `place_id`.
  Mock cũ khởi động từ dump SQL hoặc file DB cũ sẽ **tự thêm cột** lúc start, không cần dump lại.
- `GET /service-centers`, `GET /service-centers/{id}` và `verify-manager` trả thêm `address`, `latitude`, `longitude`.
- Khi chủ xưởng onboarding **không nhập toạ độ**, backend lấy toạ độ từ OEM. Toạ độ chủ xưởng nhập vẫn được ưu tiên.

---

## 2. Chuẩn bị API key

```bash
cp tools/workshop_crawl/.env.example tools/workshop_crawl/.env
```

Không commit `.env`. Có thể truyền key qua biến môi trường hoặc `--key`.

### 2.1 Amazon Location Service (mặc định)

1. Đăng nhập [AWS Console](https://console.aws.amazon.com/), chọn region ở góc trên bên phải, ví dụ
   **Asia Pacific (Singapore) `ap-southeast-1`**. API key gắn với region, tool phải gọi đúng region đó.
2. Mở **Amazon Location Service → API keys → Create API key**.
3. Đặt tên (ví dụ `workshop-crawl`). Ở phần **Places**, cho phép action **`SearchText`** (chỉ cần action này).
4. **Expiration**: đặt ngày hết hạn gần (ví dụ 30 ngày) hoặc *No expiry* nếu chỉ dùng trên máy mình.
   **Referers**: để trống, vì tool gọi từ máy, không phải từ trình duyệt.
5. Tạo xong, copy giá trị key (bắt đầu bằng `v1.public.`) rồi điền vào `.env`:

```bash
WORKSHOP_CRAWL_SOURCE=aws
AWS_LOCATION_API_KEY=v1.public....
AWS_LOCATION_REGION=ap-southeast-1
```

Nên tạo thêm **Billing → Budgets** (ví dụ 10 USD) để nhận cảnh báo chi phí.

### 2.2 Google Places (tuỳ chọn, `--source google`)

1. Vào [Google Cloud Console](https://console.cloud.google.com/), chọn (hoặc tạo) project và **bật billing**.
   Google yêu cầu billing nhưng có hạn mức miễn phí hằng tháng (xem §6).
2. **APIs & Services → Library** → bật **Places API (New)**. Không phải "Places API" bản cũ.
3. **APIs & Services → Credentials → Create credentials → API key**.
4. Bấm vào key → **API restrictions → Restrict key → chọn Places API (New)**. Nên đặt thêm quota/ngày
   ở **Quotas** để tránh bị tính tiền ngoài ý muốn.
5. Điền `GOOGLE_MAPS_API_KEY=...` vào `.env`, rồi chạy với `--source google` (hoặc đặt `WORKSHOP_CRAWL_SOURCE=google`).

---

## 3. Bắt đầu nhanh

Yêu cầu: Python 3.11+ (dùng `uv` của backend là đủ). Không cần cài thêm gì.

```bash
# 0) Xem kế hoạch query và số request tối đa (không gọi API, không tốn tiền)
python tools/workshop_crawl/workshop_crawl.py plan

# 1) Thử nhỏ trước: 2 tỉnh, 40 xưởng
python tools/workshop_crawl/workshop_crawl.py crawl --provinces "Hà Nội,Huế" --target 40

# 2) Crawl đầy đủ: ~1000 xưởng, 34 tỉnh/thành
python tools/workshop_crawl/workshop_crawl.py crawl

# 3) Xem phân bố theo tỉnh
python tools/workshop_crawl/workshop_crawl.py stats

# 4) Bật mock-ev-system rồi nạp vào service_centers
cd backend && uv run --package mock-ev-system uvicorn mock_ev_system.main:app --reload --port 8100
python tools/workshop_crawl/workshop_crawl.py import
```

Trên Windows nếu console lỗi font tiếng Việt, chạy qua `uv run python ...` hoặc đặt `PYTHONUTF8=1`.

---

## 4. Các lệnh

### 4.1 `plan` — xem kế hoạch, không gọi API

In số tỉnh, hạn mức mỗi tỉnh, các câu query mẫu và **số request tối đa** (trường hợp xấu nhất).

### 4.2 `crawl` — tìm trên nguồn dữ liệu và ghi file

| Tuỳ chọn | Mặc định | Ý nghĩa |
|---|---|---|
| `--target N` | `1000` | Số xưởng giữ lại |
| `--provinces "A,B"` | cả 34 | Chỉ crawl một số tỉnh; nhận cả tên cũ, không dấu ("ha noi", "Bình Dương") |
| `--source aws\|google` | `WORKSHOP_CRAWL_SOURCE`, không có thì `aws` | Nguồn dữ liệu (có ở cả `plan`) |
| `--pages 1..3` | `3` | Lấy tối đa 20 × N kết quả mỗi query. Google: N request. AWS: 1 request (`MaxResults` = 20 × N) |
| `--stop-at X` | `2.0` | Ngừng query thêm cho một tỉnh khi đã có X × hạn mức ứng viên |
| `--by-area` | tắt | Thêm 2 query cho **mỗi quận/huyện** của tỉnh có trong `PROVINCE_AREAS` (hiện có Hà Nội: 30 quận/huyện → +60 query). Có ở cả `plan` |
| `--with-contact` | tắt | Lấy thêm số điện thoại (Google: thêm rating, SKU Enterprise). **Đắt hơn** |
| `--key` | `AWS_LOCATION_API_KEY` hoặc `GOOGLE_MAPS_API_KEY` theo `--source` | API key |
| `--aws-region` | `AWS_LOCATION_REGION` (`ap-southeast-1`) | Region của API key AWS |
| `--aws-intended-use` | `Storage` | `Storage` là bắt buộc nếu lưu kết quả vào DB (điều khoản AWS). `SingleUse` rẻ hơn nhưng không được lưu |
| `--out` | `tools/workshop_crawl/data/workshops.json` | File kết quả |

**Cách tìm.** Với mỗi tỉnh, tool chạy lần lượt 5 query:

| Query | Lọc |
|---|---|
| `xưởng dịch vụ VinFast {tỉnh}` | tên chứa "VinFast", **hoặc** được phân loại là sửa chữa / đại lý ô tô |
| `đại lý ô tô VinFast {tỉnh}` | như trên |
| `gara sửa chữa ô tô {tỉnh}` | chỉ giữ nơi được phân loại là sửa chữa / đại lý ô tô |
| `trung tâm bảo dưỡng ô tô {tỉnh}` | như trên |
| `sửa chữa ô tô điện {tỉnh}` | như trên |

Cách lọc "sửa chữa / đại lý ô tô" theo nguồn:
- **Google**: gửi `includedType=car_repair` (strict), Google chỉ trả đúng loại đó.
- **AWS**: `SearchText` không có bộ lọc loại, nên tool lọc sau. Giữ nơi có category chứa từ
  `car`, `auto`, `automotive`, `vehicle`, `garage`. Nếu không có category thì xét tên (`gara`, `ô tô`, `auto`, `vinfast`).
  Loại mọi nơi có tên chứa `xe máy`, `xe đạp`, `motorbike`. Muốn chỉnh thì sửa `AUTOMOTIVE_WORDS` / `NAME_HINTS`
  trong `aws_places.py`.

Query thương hiệu giữ cả nơi không có "VinFast" trong tên vì nguồn hay đặt tên showroom kiểu
"SR Long Biên-Hà Nội". Những nơi đó **không** được tính là xưởng VinFast (chỉ xét tên).

Với `--by-area`, sau 5 query trên, mỗi quận/huyện có thêm `gara ô tô {quận} {tỉnh}` và
`sửa chữa bảo dưỡng ô tô {quận} {tỉnh}` (lọc như query chung).

Muốn đổi câu query thì sửa `QUERY_PLAN` / `AREA_QUERY_PLAN` trong `workshop_crawl.py`.

Mọi request đều giới hạn trong khung chữ nhật bao lãnh thổ Việt Nam (AWS thêm `IncludeCountries=VNM`).
Tỉnh có trong `PROVINCE_BBOX` (`provinces.py`, hiện có Hà Nội) dùng khung của tỉnh đó. Tìm trên cả nước,
AWS chỉ trả vài kết quả cho mỗi query; thu về khung tỉnh thì trả nhiều hơn hẳn. Khung là hình chữ nhật nên
có thể lẫn vài nơi thuộc tỉnh bên cạnh (Hà Nội: một ít ở Phú Thọ), `region` vẫn ghi đúng tỉnh của chúng.
Kết quả bị **loại** khi: đã đóng cửa vĩnh viễn (chỉ Google có thông tin này), quốc gia khác VN, không có
toạ độ, hoặc trùng `place_id`.

**Rải đều khắp Việt Nam.** Hạn mức mỗi tỉnh = `target / số tỉnh`, khoảng 30 với 1000 xưởng / 34 tỉnh. Sau khi gom
ứng viên, tool chọn **xoay vòng**: mỗi vòng lấy 1 xưởng của mỗi tỉnh, cho tới khi đủ `target`. Trong
mỗi tỉnh, xưởng VinFast được lấy trước, phần còn lại xoay vòng theo quận/huyện (lấy từ địa chỉ) để xưởng
không dồn vào một quận. Tỉnh nào hết xưởng thì các vòng sau bỏ qua, phần thiếu
tự dồn sang tỉnh còn dư (thường là Hà Nội, TP.HCM). Nhờ vậy tỉnh nhỏ vẫn có mặt mà tổng vẫn đủ 1000.

**Xác định tỉnh (`region`).** Tool xét theo thứ tự:
1. Tỉnh do nguồn trả về (Google: `administrative_area_level_1`, AWS: `Address.Region`), quy về 34 tỉnh mới (ví dụ "Bình Dương" → "TP. Hồ Chí Minh", "Quảng Nam" → "Đà Nẵng").
2. Nếu không có: tìm tên tỉnh trong địa chỉ, ưu tiên tên xuất hiện cuối cùng.
3. Nếu vẫn không có: lấy tỉnh đang query.

**Cache.** Mỗi query (gồm mọi trang) được lưu ở `data/cache/<nguồn>/<hash>.json`. Chạy lại `crawl`, hoặc chạy
tiếp sau khi bị lỗi giữa chừng, **không tốn thêm request** cho query đã có. Xoá `data/cache/` để lấy dữ liệu mới.

### 4.3 `stats` — phân bố theo tỉnh

In tổng số, số xưởng VinFast, số `dealer` / `service_only` và số xưởng từng tỉnh.

### 4.4 `import` — nạp vào mock-ev-system

Gửi `POST /admin/import` với `mode=upsert` vào bảng `service_centers`, toàn bộ trong một transaction.
Chạy lại an toàn: cùng một xưởng luôn có cùng `center_id`.

| Tuỳ chọn | Mặc định |
|---|---|
| `--url` | `EV_MOCK_URL` (`http://localhost:8100`) |
| `--token` | `EV_MOCK_ADMIN_TOKEN` (bắt buộc nếu mock đặt `MOCK_ADMIN_TOKEN`, ví dụ trên Railway) |
| `--out` | file kết quả của `crawl` |

Mock mặc định chạy **in-memory**, nên restart là mất dữ liệu đã import. Muốn giữ lại cho cả team:
import xong thì dump ra seed dùng chung bằng [ev_mock_data](../ev_mock_data/README.md):

```bash
python tools/ev_mock_data/ev_mock_data.py dump --out backend/mock-ev-system/seed-data/ev-mock-dump.sql
```

Nên dump từ một mock **sạch** (nạp từ dump dùng chung, không đặt `MOCK_DEV_OWNER_EMAILS`). Nếu không,
chủ xe/xe sinh cho Gmail dev sẽ lẫn vào seed của cả team.

### 4.5 Đưa xưởng vào backend (không cần Firebase)

Theo luồng chuẩn, xưởng chỉ có trong DB backend khi chủ xưởng đăng nhập Google rồi onboarding. Muốn có
sẵn xưởng để chủ xe đặt lịch, dùng script seed của backend. Script đọc cùng file `workshops.json`:

```bash
cd backend
python scripts/seed_workshops.py --region "Hà Nội"           # dry run
python scripts/seed_workshops.py --region "Hà Nội" --apply   # ghi vào DB của root .env
python scripts/seed_service_prices.py --apply                # giá cho các xưởng mới
```

- Mỗi xưởng có một chủ xưởng giữ chỗ với `firebase_uid = seed:<center_id>`. Không có tài khoản Firebase
  nào có uid đó, nên không ai đăng nhập Workshop Portal của các xưởng này được.
- Xưởng ở trạng thái `active`, chế độ xác nhận `auto` (không cần chủ xưởng duyệt). Giờ mở cửa demo:
  T2–T7 08:00–17:30, CN 08:00–12:00.
- `hotline` để trống vì crawl không có số điện thoại. Không dùng số bịa, vì số này hiện cho chủ xe kèm nút gọi.
- Chạy lại an toàn: xưởng đã có `external_center_id` thì bỏ qua.
- Muốn tự đăng nhập một xưởng: **đừng** seed xưởng đó. Đổi `manager_email` / `manager_national_id` của nó
  thành Gmail + CCCD của bạn, `import` lại vào mock, rồi onboarding như bình thường.

---

## 5. Định dạng dữ liệu

`data/workshops.json`:

```json
{
  "generated_at": "2026-10-10T08:00:00+00:00",
  "source": "Amazon Location Service — Places v2 SearchText",
  "target": 1000,
  "candidates": 2140,
  "count": 1000,
  "workshops": [
    {
      "center_id": "AL-3F2A9C01B7",
      "name": "VinFast Thăng Long",
      "region": "Hà Nội",
      "type": "dealer",
      "address": "Số 1 Phạm Văn Bạch, Cầu Giấy, Hà Nội, Việt Nam",
      "latitude": 21.0301,
      "longitude": 105.7915,
      "place_id": "AQAAAD...",
      "manager_email": "manager.al-3f2a9c01b7@workshop.example.com",
      "manager_national_id": "482019374615",
      "source": "aws",
      "maps_uri": null,
      "categories": ["car_dealer", "car_repair"],
      "searched_province": "Hà Nội",
      "query": "đại lý ô tô VinFast Hà Nội"
    }
  ]
}
```

| Trường | Ghi chú |
|---|---|
| `center_id` | Tiền tố theo nguồn (`AL-` AWS, `GM-` Google) + 10 ký tự hash của `place_id`. Ổn định giữa các lần crawl |
| `type` | `dealer` nếu nguồn phân loại là đại lý ô tô, ngược lại `service_only` |
| `manager_email`, `manager_national_id` | **Giả lập**, sinh tất định. Mock bắt buộc mỗi xưởng có một quản lý duy nhất. Muốn đăng nhập Workshop Portal với một xưởng, sửa 2 trường này thành Gmail + CCCD của bạn rồi `import` lại |
| `source`, `maps_uri`, `categories`, `searched_province`, `query` | Metadata để kiểm tra, **không** import. `maps_uri` chỉ có với Google |
| `phone` (+ `rating`, `rating_count` với Google) | Chỉ có khi chạy với `--with-contact` |

---

## 6. Chi phí và hạn mức

Luôn chạy `plan` trước: lệnh này in **số request tối đa** cho nguồn đang chọn, và không gọi API.

**AWS.** Mỗi query chỉ tốn **1 request** (AWS trả tới 100 kết quả trong một trang). Crawl đầy đủ
34 tỉnh × 5 query tốn tối đa **170 request**, thực tế ít hơn nhờ dừng sớm và cache.
- Giá tính theo request và theo `IntendedUse`. `Storage` đắt hơn `SingleUse`, nhưng điều khoản AWS chỉ
  cho phép **lưu kết quả lâu dài** (vào DB) khi gọi với `Storage`. Vì vậy tool mặc định dùng `Storage`.
- Tài khoản AWS mới thường có credit / hạn mức dùng thử. Xem
  [Amazon Location pricing](https://aws.amazon.com/location/pricing/) trước khi chạy, vì giá có thể thay đổi.

**Google.** Field mặc định thuộc SKU **Text Search Pro**, thêm `--with-contact` sẽ chuyển sang **Enterprise**.
Crawl đầy đủ tốn tối đa **510 request** (3 trang × 170 query). Xem
[Places API pricing](https://developers.google.com/maps/billing-and-pricing/pricing).

Sau mỗi lần chạy, tool in số request thực tế và số query lấy từ cache.

**Điều khoản dữ liệu.** Dữ liệu này chỉ dùng cho **demo / mock** của dự án, không dùng làm cơ sở dữ liệu
thương mại. Google chỉ cho lưu không thời hạn `place_id`; toạ độ chỉ được cache tạm (tối đa 30 ngày).
AWS cho lưu khi gọi với `IntendedUse=Storage`. Với sản phẩm thật, toạ độ xưởng phải lấy từ hãng hoặc
chủ xưởng khai báo.

---

## 7. Xử lý lỗi thường gặp

| Lỗi | Nguyên nhân / cách xử lý |
|---|---|
| `Missing AWS_LOCATION_API_KEY` / `Missing GOOGLE_MAPS_API_KEY` | Chưa điền key của nguồn đang chọn trong `.env`, hoặc chưa truyền `--key` |
| AWS `HTTP 403` | Key sai, hết hạn, chưa cho phép action `SearchText`, hoặc khác region với `AWS_LOCATION_REGION` |
| AWS `HTTP 400 ... ValidationException` | Tham số không hợp lệ, ví dụ region không hỗ trợ Places v2. Thử region khác (`us-east-1`) và tạo key ở đó |
| Google `HTTP 403 ... API has not been used / is disabled` | Chưa bật **Places API (New)** cho project của key |
| Google `HTTP 403 ... billing` | Project chưa bật billing |
| Google `HTTP 400 ... API key not valid` | Key sai hoặc bị restrict sang API khác |
| `HTTP 429` | Hết quota. Tool tự retry; nếu vẫn lỗi thì đợi rồi chạy lại (cache giữ phần đã xong) |
| `Cannot reach mock-ev-system` | Chưa bật mock, hoặc sai `EV_MOCK_URL` |
| `Import failed: HTTP 401/403` | Thiếu hoặc sai `EV_MOCK_ADMIN_TOKEN` |
| AWS ra ít gara ở một tỉnh, hoặc lẫn nơi không phải gara | Xem `categories` trong file kết quả rồi chỉnh `AUTOMOTIVE_WORDS` / `NAME_HINTS` trong `aws_places.py`, xoá `data/workshops.json` và chạy lại (cache giữ nguyên, không tốn request) |
| Một tỉnh có ít xưởng | Bình thường với tỉnh miền núi. Phần thiếu đã dồn sang tỉnh khác. Muốn thêm thì tăng `--stop-at` hoặc thêm query vào `QUERY_PLAN` |

---

## 8. Test

```bash
cd backend && uv run --frozen pytest ../tools/workshop_crawl -q
```

Test chạy offline với client giả, gồm: quy đổi tên tỉnh cũ → mới, chuẩn hoá kết quả Google / AWS, nhận diện
gara trên AWS, body request gửi AWS, cache, lọc kết quả, sinh `center_id` tất định, chia đều theo tỉnh và
luồng `crawl` ghi file.
