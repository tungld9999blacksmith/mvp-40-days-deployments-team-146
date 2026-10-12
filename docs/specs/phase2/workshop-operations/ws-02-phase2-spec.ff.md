# Functional Specification — Sức chứa theo thời lượng và hạn phản hồi

> Đặc tả nghiệp vụ cho **WS-02** trong [PRD Phase 2](../../../product/PRD_EV_Care_Phase2.md).
>
> **Quan hệ tài liệu:** thay mô hình sức chứa "1 booking = 1 thợ × 1 khung" (PRD MVP F6, PQ-03, [us-029](../../sprint-3/feature-functional/us-029-sprint-3-spec.ff.md) BR-005) bằng mô hình theo **thời lượng**. Service sức chứa vẫn là nơi duy nhất kiểm tra và giữ chỗ. Hạn chót duyệt tay (us-029 BR-015, `BOOKING_WS_CONFIRM_DEADLINE_HOURS`) giữ nguyên thời hạn; spec này đổi cách xử lý khi hết hạn.
>
> **Rủi ro cao:** thay đổi service sức chứa có thể phá quy tắc chống đặt trùng của MVP. Bắt buộc giữ AC-F6-01 trong bộ hồi quy.
>
> Quy ước: [README Phase 2](../README.md).
>
> **Đặc tả kỹ thuật:** [API Spec](ws-02-phase2-spec.api.md) · [Entity Spec](ws-02-phase2-spec.entity.md) · [Frontend Spec](ws-02-phase2-spec.fe.md)

---

# 1. Document Information

| Field | Value |
|---|---|
| Feature ID | `FEAT-P2-WS02` |
| Feature Name | Sức chứa theo thời lượng và hạn phản hồi |
| PRD Feature | WS-02 (P2-A, Should, Cải tiến MVP) |
| Document Version / Status | `v0.2` / `Draft` |
| Created / Updated | `2026-10-09` / `2026-10-12` |
| Related Technical Spec | [API Spec](ws-02-phase2-spec.api.md) · [Entity Spec](ws-02-phase2-spec.entity.md) · [Frontend Spec](ws-02-phase2-spec.fe.md) |

---

# 2. Feature Overview

## 2.1 Feature Description

**Phần A — Thời lượng.** Mỗi hạng mục có **thời lượng chuẩn**. Lịch hẹn chiếm thời gian bằng tổng thời lượng các hạng mục, làm tròn lên theo `SLOT_UNIT_MIN`. Sức chứa kiểm tra theo **thợ × thời gian**: một thợ (hoặc khoang) không làm hai xe cùng lúc. Thời lượng thực tế từ tiến độ 6 bước được ghi lại để đề xuất chỉnh thời lượng chuẩn.

**Phần B — Hạn phản hồi.**
- Nhắc chủ xưởng khi lịch duyệt tay đã qua `WS_CONFIRM_REMIND_PCT` thời hạn.
- Khi hết hạn, **trước khi huỷ**, hệ thống gọi BK-01 để giữ phương án thay thế cho chủ xe.

**Phần C — Chỗ dự phòng.** Hệ thống đề xuất số chỗ dự phòng cho khách vãng lai theo tỉ lệ thực tế; chủ xưởng quyết định.

## 2.2 Business Objective

Sức chứa phản ánh đúng công việc (PP2-11). Chủ xe không bị bỏ rơi khi xưởng chậm duyệt (PP2-09).

## 2.3 User Objective

- Xưởng: không quá tải, không thợ ngồi chơi.
- Chủ xe: luôn có phương án.

## 2.4 Business Value

Giảm T₃, T₄ (M-09, M-10). Dữ liệu đầu vào cho BK-08, BK-10.

---

# 3. Scope

## 3.1 In Scope

- Danh mục thời lượng chuẩn (mặc định toàn hệ thống, xưởng chỉnh).
- Kiểm tra sức chứa theo khoảng thời gian.
- Chuyển đổi dữ liệu cũ.
- Ghi thời lượng thực tế; đề xuất điều chỉnh.
- Nhắc duyệt; phương án thay thế khi hết hạn.
- Đề xuất chỗ dự phòng.

## 3.2 Out of Scope

- Gán KTV cụ thể (WS-03).
- Tối ưu thứ tự (BK-10).
- Nhiều ca, giờ nghỉ trưa (ngoài phạm vi MVP; có thể mở sau).

---

# 4. Actors

| Actor | Type | Responsibility |
|---|---|---|
| Chủ xưởng | User | Chỉnh thời lượng, chỗ dự phòng; duyệt lịch |
| Service sức chứa | System | Kiểm tra theo thời lượng |
| Job hạn duyệt | System | Nhắc, xử lý hết hạn |
| Bộ lập lịch | System | Phương án thay thế |

---

# 5. User Story

- `US-P2-WS02-01`: As a chủ xưởng, I want bảo dưỡng lớn chiếm nhiều thời gian hơn kiểm tra nhanh, so that lịch không bị quá tải.
- `US-P2-WS02-02`: As a chủ xe, I want khi xưởng không kịp duyệt, tôi có ngay phương án khác, so that tôi không mất lịch.
- `US-P2-WS02-03`: As a chủ xưởng, I want được gợi ý thời lượng thực tế, so that tôi chỉnh cho đúng.

---

# 6. Use Case

| UC | Tên | Trigger | Postcondition |
|---|---|---|---|
| `UC-WS02-01` | Cấu hình thời lượng | Chủ xưởng mở Thời lượng hạng mục | Thời lượng theo xưởng |
| `UC-WS02-02` | Kiểm tra sức chứa | Giữ chỗ | Thành công nếu đủ thợ trong toàn khoảng |
| `UC-WS02-03` | Nhắc duyệt | Qua `WS_CONFIRM_REMIND_PCT` thời hạn | Chủ xưởng nhận nhắc |
| `UC-WS02-04` | Hết hạn duyệt | Quá hạn chót | Phương án thay thế giữ sẵn, lịch cũ `cancelled` |
| `UC-WS02-05` | Đề xuất điều chỉnh | Job tuần | Chủ xưởng thấy đề xuất thời lượng mới |

---

# 7. User Flow

```mermaid
flowchart TD
    A[Giữ chỗ lịch có hạng mục H1..Hn] --> B[Thời lượng = Σ thời lượng chuẩn, làm tròn SLOT_UNIT_MIN]
    B --> C{Trong khoảng [t, t+d) số thợ bận < số thợ khả dụng ở mọi đơn vị?}
    C -- Có --> D[Giữ chỗ]
    C -- Không --> E[Hết chỗ → BK-01 phương án khác]
    F[Lịch pending duyệt tay] --> G{Qua WS_CONFIRM_REMIND_PCT?}
    G -- Có --> H[Nhắc chủ xưởng]
    F --> I{Hết hạn chót?}
    I -- Có --> J[BK-01 giữ phương án thay thế] --> K[Huỷ lịch cũ, báo chủ xe kèm phương án]
```

---

# 8. Screen / UI Flow

| Screen ID | Name | Purpose |
|---|---|---|
| `SCR-WS02-01` | Thời lượng hạng mục (Workshop Portal) | Bảng hạng mục: mặc định, của xưởng, thực tế trung vị 30 ngày, nút "Dùng số thực tế" |
| `SCR-WS02-02` | Sức chứa (cập nhật màn us-037) | Ô khung hiển thị số chỗ còn theo đơn vị `SLOT_UNIT_MIN`; lịch dài hiển thị trải nhiều ô |
| `SCR-WS02-03` | Chỗ dự phòng | Số đề xuất theo tỉ lệ vãng lai 30 ngày, chủ xưởng chấp nhận / sửa |
| `SCR-WS02-04` | Thông báo hết hạn (chủ xe) | "Xưởng chưa kịp xác nhận. Mình đã giữ sẵn: …" |

---

# 9. Main Flow

1. Xưởng có 4 thợ, mở 08:00–17:00, `SLOT_UNIT_MIN` = 30.
2. Lịch A: bảo dưỡng lớn 150 phút lúc 08:00, chiếm 1 thợ trong 08:00–10:30.
3. Lịch B: kiểm tra nhanh 30 phút lúc 08:00, chiếm 1 thợ trong 08:00–08:30.
4. Lúc 08:00 còn 2 thợ trống. Lúc 08:30 còn 3 thợ trống.

---

# 10. Alternative Flow

- **AF-WS02-01 — Lịch cũ không rõ hạng mục:** thời lượng = `LEGACY_BOOKING_MIN` (60).
- **AF-WS02-02 — Lịch vượt giờ đóng cửa:** không cho bắt đầu nếu không kết thúc trước giờ đóng cửa.

# 11. Exception Flow

| ID | Condition | Behavior |
|---|---|---|
| `EF-WS02-01` | Hết hạn duyệt và BK-01 không có phương án | Huỷ lịch cũ, báo chủ xe kèm lý do và lựa chọn nới ràng buộc (BK-01 AF-BK01-04) |
| `EF-WS02-02` | Hạng mục chưa có thời lượng chuẩn | Dùng `LEGACY_BOOKING_MIN`, ghi log để bổ sung |
| `EF-WS02-03` | Chủ xưởng giảm số thợ làm lịch đã giữ vượt sức chứa | Không huỷ tự động; cảnh báo xưởng xử lý (BK-01 AF-BK01-08) |

---

# 12. Business Rules

- **BR-WS02-01 (PRD):** Thời lượng lịch = Σ thời lượng chuẩn, làm tròn lên `SLOT_UNIT_MIN`. **High.**
- **BR-WS02-02 (PRD):** Kiểm tra theo thợ × thời gian; mỗi đơn vị thời gian trong khoảng lịch phải còn thợ. **High.**
- **BR-WS02-03 (PRD):** Lịch không rõ hạng mục = `LEGACY_BOOKING_MIN`. **High.**
- **BR-WS02-04 (PRD):** Nhắc ở `WS_CONFIRM_REMIND_PCT`; hết hạn thì giữ phương án thay thế rồi mới huỷ lịch cũ. **High.**
- **BR-WS02-05 (PRD):** Chỗ dự phòng: hệ thống đề xuất, chủ xưởng quyết định. **Medium.**
- **BR-WS02-06 (PRD):** Ghi thời lượng thực tế từ tiến độ; đề xuất điều chỉnh khi trung vị lệch > 20% với ≥ 10 mẫu. **Medium.**
- **BR-WS02-07:** Công thức sức chứa MVP (`total_technicians − emergency_slots_reserved − blocked`) áp cho **từng đơn vị thời gian**. Khoá chỗ của chủ xưởng áp theo khoảng. **High.**
- **BR-WS02-08:** Bật mô hình thời lượng theo từng xưởng (cờ cấu hình). Chưa bật thì giữ mô hình MVP. **High.**

# 13. State / Status

Không thêm trạng thái. Lịch có `duration_min`, `starts_at`, `ends_at`.

# 14. Data Requirements

| Entity | Purpose | R/W |
|---|---|---|
| `service_item_duration` (mới) | Hạng mục, xưởng (null = mặc định), thời lượng chuẩn | R/W |
| `booking.duration_min`, `ends_at` (mới) | Khoảng chiếm | W |
| `service_progress` | Thời lượng thực tế | R |
| `workshop_slot_block` | Khoá chỗ theo khoảng | R |

# 15. Business Error & Edge Cases

| Case ID | Scenario | Expected Behavior |
|---|---|---|
| `EDGE-WS02-01` | 20 yêu cầu đồng thời vào khoảng còn 1 thợ | Đúng 1 thành công (AC-F6-01) |
| `EDGE-WS02-02` | Lịch gộp thêm hạng mục (HS-02) làm thời lượng tăng | Kiểm tra lại sức chứa trước khi cập nhật |
| `EDGE-WS02-03` | Đổi lịch cùng khung | Không tính chính lịch đang đổi (giữ us-053) |

# 16. Permissions & Access

Chủ xưởng chỉnh thời lượng và dự phòng của xưởng mình.

# 17. Acceptance Criteria

- **AC-WS02-01:** Không thợ nào bị gán hai lịch chồng thời gian (kiểm tra tự động).
- **AC-WS02-02:** AC-F6-01 vẫn đạt với mô hình thời lượng.
- **AC-WS02-03:** Lịch bị huỷ do xưởng chậm duyệt luôn đi kèm phương án thay thế, hoặc lý do không có.
- **AC-WS02-04:** Xưởng chưa bật mô hình thời lượng cho kết quả sức chứa giống MVP.

# 18. Non-functional Expectations

Kiểm tra sức chứa theo khoảng ≤ 100 ms (p90); nguyên tử (NFR-01).

# 19. Dependencies

us-029, us-037, us-057, BK-01.

# 20. Assumptions

Thời lượng chuẩn đủ ổn định (H2-10).

# 21. Business Constraints

Không vượt sức chứa.

# 22. Terminology

| Term | Vietnamese |
|---|---|
| Standard duration | Thời lượng chuẩn |
| Slot unit | Đơn vị khung |

# 23. Partner Notes

| Spec MVP | Thay đổi |
|---|---|
| PQ-03 "1 booking chiếm 1 thợ trong 1 khung 60 phút" | Theo thời lượng; dữ liệu cũ = 60 phút |
| us-029 BR-015 tự huỷ khi xưởng chậm duyệt | Giữ phương án thay thế trước khi huỷ |

# 24. Open Questions

| ID | Question | Proposal |
|---|---|---|
| `Q-WS02-01` | `SLOT_UNIT_MIN`? | 30 |
| `Q-WS02-02` | Nguồn thời lượng chuẩn mặc định? | Tài liệu hãng; thiếu thì 60 phút |

# 25. Traceability

PRD Phase 2 WS-02, PP2-07, PP2-11 · BR-WS02-01…08 · AC-WS02-01…04.

# 26. Related Documents

[PRD Phase 2](../../../product/PRD_EV_Care_Phase2.md) · [us-029 FF](../../sprint-3/feature-functional/us-029-sprint-3-spec.ff.md) · [BK-10](../booking/bk-10-phase2-spec.ff.md) · [API Spec](ws-02-phase2-spec.api.md) · [Entity Spec](ws-02-phase2-spec.entity.md) · [Frontend Spec](ws-02-phase2-spec.fe.md)

# 27. Change Log

| Version | Date | Change |
|---|---|---|
| `v0.1` | `2026-10-09` | Bản nháp đầu |
| `v0.2` | `2026-10-12` | Liên kết đặc tả API, Entity, Frontend |

# 28. Approval

| Role | Status |
|---|---|
| Product Owner | Pending |
| Technical Owner | Pending |
