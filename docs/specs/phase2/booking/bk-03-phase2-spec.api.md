# API Technical Specification — Bảo dưỡng sớm hoặc trễ so với mốc

> Backend cho Feature `FEAT-P2-BK03`.
>
> **Nguồn nghiệp vụ:** [Functional Spec](bk-03-phase2-spec.ff.md). **Entity:** [Entity Spec](bk-03-phase2-spec.entity.md).
>
> **Tái dùng, không viết lại:** `UserVehicleService.get_maintenance_status` (F3: `due_status`, `remaining_km`, `remaining_days`, `next_milestone`, `calculation_basis`), RAG có nguồn (F4, `agents/tools/RAG`, nguyên tắc no-source-no-claim), `SchedulerService.run` (BK-01), `CapacityService.duration_for` (WS-02). LLM **không** tính mốc hay ngưỡng (FF §21).

---

# 0. Document Information

| Field | Value |
|---|---|
| Document ID | `API-SPEC-P2-BK03` |
| Version | `v0.1` |
| Status | `Draft` |
| Base URL | `/api/v1` |
| Module | `backend/src/modules/user_vehicle/early_service.py` (mới), `agents/tools/maintenance_tools.py` (tool mới) |
| Created Date | `2026-10-12` |

---

# 1. API Group

| API ID | Method | Endpoint | Mục đích | FF |
|---|---|---|---|---|
| `API-BK03-01` | `GET` | `/user-vehicles/{userVehicleId}/early-service-check` | Phân loại sớm / trễ cho mốc kế tiếp + nguồn + có Kiểm tra nhanh không | UC-BK03-01, 02, 04 |
| `API-BK03-02` | `POST` | `/scheduling/runs` (sửa, BK-01) | Thêm `serviceKind`, `earlyAcknowledged` | AF-BK03-01, 02 |
| `API-BK03-03` | `GET` | `/user-vehicles/{userVehicleId}/maintenance-status` (sửa) | Thêm `basis` để hiện "tính từ lần bảo dưỡng ngày …" và `pendingOemSync` | UC-BK03-03, SCR-BK03-02 |
| `TOOL-BK03-01` | Agent tool | `check_early_service` | Agent đọc kết quả phân loại + nguồn; gắn thẻ `EARLY_SERVICE` | SCR-BK03-01, AC-BK03-02 |

---

# 2. Authorization & Guards

Chủ xe; xe thuộc chủ xe, `VERIFIED` + `ACTIVE` (dependency `get_owned_active_vehicle` có sẵn).

---

# 3. API-BK03-01 — `GET /user-vehicles/{userVehicleId}/early-service-check`

Query: `workshopId` (tuỳ chọn) để biết xưởng đó có Kiểm tra nhanh không; không có ⇒ trả danh sách xưởng gần có cung cấp không cần thiết, chỉ cờ `quickCheckOffered` theo xưởng yêu thích (BK-01) nếu có.

## 3.1 Processing

1. `status = get_maintenance_status(vehicle)`.
2. `UNKNOWN` ⇒ `classification = UNKNOWN`, không phân loại (EF-BK03-01); frontend mở chọn hạng mục (us-061 EF-1502).
3. `OVERDUE` ⇒ `classification = OVERDUE`; `warrantyNote` từ §3.2.
4. Còn lại: ngưỡng từ `early_service_window` (entity §2) ⇒ phân loại theo BR-ENT-BK03-01.
5. `quickCheckOffered`: xưởng có `service_price` cho `QUICK_CHECK` (entity §4).
6. Không gọi LLM.

## 3.2 `warrantyNote` (BR-BK03-04, BR-BK03-05)

- Xe hết bảo hành (`vehicle_warranty` không còn `is_active`) ⇒ `null` (EDGE-BK03-03).
- Truy hồi RAG `query = "bảo dưỡng trễ mốc ảnh hưởng bảo hành {model}"`, chỉ nhận chunk `official_document` có điểm ≥ ngưỡng RAG hiện có và chứa từ khoá bảo hành. Có ⇒ `{ "hasSource": true, "citations": [...] }` (trích đoạn nguyên văn, không diễn giải con số). Không ⇒ `{ "hasSource": false, "text": "Tài liệu hãng chưa nêu ảnh hưởng tới bảo hành, bạn nên hỏi xưởng." }` (AF-BK03-03).
- Đệm Redis theo (model, phiên bản tài liệu) 24 giờ.

## 3.3 Response `200`

```json
{
  "data": {
    "classification": "TOO_EARLY",
    "milestone": { "odoMilestoneKm": 24000, "label": "24.000 km / 24 tháng", "dueDate": "2027-02-12" },
    "remainingKm": 4200, "remainingDays": 122,
    "threshold": { "earlyDays": 30, "earlyKm": 1000, "sourceType": "CONFIG", "citation": null },
    "summary": "Xe còn 4.200 km hoặc 4 tháng mới tới mốc 24.000 km.",
    "quickCheckOffered": true,
    "warrantyNote": null,
    "nextMilestoneNote": "Nếu bảo dưỡng đầy đủ bây giờ, mốc sau sẽ tính từ ngày và số km của lần này."
  }
}
```

`summary` dựng bằng mẫu từ số liệu F3 (không LLM). `threshold.citation` có khi `sourceType = OEM_DOC`.

---

# 4. API-BK03-02 — `POST /scheduling/runs` (sửa BK-01)

Thêm vào request:

| Field | Validation |
|---|---|
| `serviceKind` | `MAINTENANCE` (mặc định) / `QUICK_CHECK` |
| `earlyAcknowledged` | `bool`, mặc định `false` |

Xử lý thêm (trước bước 6 của BK-01 API §4.2):

1. `classification` như §3.1.
2. `MAINTENANCE` + `TOO_EARLY` + `earlyAcknowledged = false` ⇒ `outcome = EARLY_CONFIRMATION_REQUIRED` với `early = <API-BK03-01 data>`; không quét khung (BR-BK03-02).
3. `QUICK_CHECK`: hạng mục = `[QUICK_CHECK]`, thời lượng theo WS-02; chỉ xưởng có `service_price` `QUICK_CHECK`; không hạn chót mốc; `odo_milestone = NULL` trên booking.
4. `OVERDUE`: bỏ hạn chót, chấm điểm thêm yếu tố `EARLIEST` trọng số 30 và sắp `start` tăng dần trước điểm (AC-BK03-04); lý do `EARLIEST` "Khung sớm nhất vì xe đã quá hạn".
5. Lịch tạo từ phương án ghi `service_kind`, `early_classification`, và `early_confirmed_at = now` khi `earlyAcknowledged`.

Luồng đặt lịch MVP (`POST /bookings` với token) áp cùng kiểm tra: `MAINTENANCE` + `TOO_EARLY` mà request không có `earlyAcknowledged = true` ⇒ `409 EARLY_CONFIRMATION_REQUIRED` (`details.early`).

---

# 5. API-BK03-03 — `maintenance-status` (sửa)

Thêm:

```json
{ "basis": { "type": "LAST_SERVICE", "serviceDate": "2026-10-12", "serviceOdoKm": 23000, "source": "OEM" },
  "pendingOemSync": { "bookingId": "…", "completedAt": "2026-10-12T09:00:00Z" } }
```

- `basis` lấy từ `calculation_basis` hiện có + bản ghi `vehicle_service_record` gần nhất dùng để tính.
- `pendingOemSync`: có lịch EV Care `MAINTENANCE` `completed` mà hãng chưa gửi `vehicle_service_record` tương ứng (EF-BK03-02) ⇒ frontend hiện "Đang chờ hãng cập nhật lịch sử", mốc vẫn là mốc cũ. Lịch `QUICK_CHECK` không bao giờ tạo `pendingOemSync`.

---

# 6. TOOL-BK03-01 — `check_early_service`

| | |
|---|---|
| File | `backend/src/agents/tools/maintenance_tools.py` |
| Args (LLM thấy) | không có (dùng xe của hội thoại) |
| Trả về LLM | `classification`, `summary`, `threshold`, `warrantyNote` (chỉ `citations` hoặc câu cố định), `quickCheckOffered` |
| Gắn thẻ | `card = { type: "EARLY_SERVICE", userVehicleId, classification }` khi `TOO_EARLY` hoặc `OVERDUE`; thẻ đọc lại API-BK03-01 khi render |
| Prompt | "Chỉ khẳng định về bảo hành khi `warrantyNote.hasSource = true` và kèm trích dẫn. Không tự nêu ân hạn, ngưỡng mất bảo hành, hay tự tính mốc." Guardrail đầu ra hiện có (`conversation_guards/output_guard.py`) thêm pattern chặn câu khẳng định bảo hành không có citation |

---

# 7. Error Cases

| HTTP | Code | Khi | API |
|---|---|---|---|
| 404 | `VEHICLE_NOT_FOUND` | Xe không thuộc chủ xe | BK03-01, 03 |
| 409 | `VEHICLE_NOT_ACTIVE` | | BK03-01 |
| 409 | `EARLY_CONFIRMATION_REQUIRED` | Đặt quá sớm chưa xác nhận lần hai | `POST /bookings` |
| 422 | `QUICK_CHECK_NOT_OFFERED` | `serviceKind = QUICK_CHECK` với `overrides.workshopId` không cung cấp | BK03-02 |

---

# 8. Test Checklist

| Layer | What | Count |
|---|---|---|
| Unit | Phân loại: trong ngưỡng theo km nhưng xa theo ngày ⇒ `WITHIN` (EDGE-BK03-01); `DUE_SOON` ⇒ `WITHIN`; cả hai xa ⇒ `TOO_EARLY` | +4 |
| Unit | Tra ngưỡng: (model, mốc) → model → mặc định | +3 |
| Service | `TOO_EARLY` chưa xác nhận ⇒ `EARLY_CONFIRMATION_REQUIRED`, không giữ chỗ | +1 |
| Service | `QUICK_CHECK` hoàn tất ⇒ mốc vẫn mở, nhắc vẫn chạy (AC-BK03-03) | +1 |
| Service | `OVERDUE` ⇒ phương án đầu là khung sớm nhất (AC-BK03-04) | +1 |
| Service | Lịch sử hãng đồng bộ lần làm sớm ⇒ mốc kế tiếp khớp công thức F3 (AC-BK03-01) | +1 |
| Service | `pendingOemSync` khi chưa có bản ghi hãng (EF-BK03-02) | +1 |
| Eval | Bộ câu hỏi trễ mốc (`eval/datasets`): 100 % câu khẳng định bảo hành có citation; không nguồn ⇒ không khẳng định (AC-BK03-02) | +1 bộ |
| Agent | Xe hết bảo hành ⇒ không có câu cảnh báo bảo hành (EDGE-BK03-03) | +1 |

---

# 9. Change Log

| Version | Date | Change |
|---|---|---|
| `v0.1` | `2026-10-12` | Bản nháp đầu |
