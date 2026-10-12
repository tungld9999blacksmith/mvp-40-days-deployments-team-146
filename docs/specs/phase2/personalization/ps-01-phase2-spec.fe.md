# Frontend Technical Specification — Bộ nhớ ngắn hạn và dài hạn của agent

> Frontend cho Feature `FEAT-P2-PS01` (SCR-PS01-01, SCR-PS01-02).
>
> **Nguồn nghiệp vụ:** [Functional Spec](ps-01-phase2-spec.ff.md). **API:** [API Spec](ps-01-phase2-spec.api.md) (`API-PS01-01..05`).
>
> **Nguyên tắc:** tái dùng `MemoryDrawer` của trợ lý (`features/assistant/components/MemoryDrawer.tsx`) — tách phần nội dung thành component dùng chung cho drawer và trang mới. Bật / tắt là đồng ý PL-01, không phải một công tắc riêng.

---

## 1. Document Information

| Field | Value |
|---|---|
| Document ID | `FE-SPEC-P2-PS01` |
| Version | `v0.1` |
| Status | `Draft` |
| Screens | SCR-PS01-01 (trang mới + drawer có sẵn), SCR-PS01-02 (banner lần đầu, đặc tả ở PL-01 FE §2.7) |
| Routes | `/settings/memory` (mới) |
| Feature folder | `frontend/src/features/memory/` (mới, chuyển logic từ `MemoryDrawer`) |
| Created Date | `2026-10-12` |

---

# 2. Components

## 2.1 `MemoryPanel` (nội dung dùng chung)

File `features/memory/components/MemoryPanel.tsx`; dùng trong `MemoryPage` (`/settings/memory`) và `MemoryDrawer` (giữ điểm mở từ AI trợ lý).

| Vùng | Nội dung |
|---|---|
| Đầu | Tiêu đề "Trợ lý đang nhớ gì về bạn"; một câu "Trợ lý dùng những điều này để không hỏi lại. Bạn sửa hoặc xoá được bất cứ lúc nào." |
| Công tắc | "Cho phép trợ lý nhớ" = `CONSENT_LONG_TERM_MEMORY` (đọc / ghi qua PL-01 `api.ts`). Tắt ⇒ dòng "Trợ lý không dùng và không ghi thêm. Dữ liệu cũ vẫn còn cho tới khi bạn xoá." |
| Nhóm | Mỗi `group`: tiêu đề (`title`), danh sách mục `divide-y` |
| Mục | Nội dung đọc được (`describeMemory(key, value, label)`), nhãn nguồn ("Bạn đã nói" / "Hệ thống suy ra" / "Từ đánh giá dịch vụ"), "Dùng lần cuối {ngày}" hoặc "Chưa dùng", "Còn đến {expiresAt}"; mục `usable = false` mờ + nhãn "Đang quan sát ({confirmCount}/{N} lần)" |
| Hành động mục | "Sửa" (khi `editable` và đang bật) mở `MemoryEditDialog`; "Xoá" (ghost) — không hộp xác nhận, có toast "Đã xoá · Hoàn tác" 5 s (hoàn tác = không gửi `DELETE` nếu chưa hết 5 s) |
| Cuối | "Xoá tất cả" (danger) ⇒ `alertdialog` "Xoá mọi điều trợ lý nhớ về bạn? Không thể hoàn tác." ⇒ `API-PS01-04` |
| Trống | "Trợ lý chưa nhớ điều gì về bạn." |

## 2.2 `MemoryEditDialog`

Form theo khoá:

| Khoá | Trường |
|---|---|
| `preferred_workshop` | Chọn xưởng (`/agent-memory/workshops` có sẵn) |
| `preferred_time` | Chọn thứ (nhiều) + buổi hoặc giờ bắt đầu–kết thúc |
| `location_anchor` | Tỉnh / quận (không có ô số nhà) |
| `addressing` | Ô chữ ≤ 30 ký tự |
| `vehicle_issue` | Nhóm (chọn) + mô tả ≤ 120 ký tự |
| `communication_style` | Theo PS-05 FE |
| `cost_display_preference` | Như MVP |

Lỗi `INVALID_MEMORY_VALUE` ⇒ "Nội dung chứa thông tin không được lưu (số giấy tờ, số điện thoại…)". Gửi kèm `version`; `MEMORY_VERSION_CONFLICT` ⇒ tải lại.

## 2.3 `MemoryPage` (route `/settings/memory`)

Vào từ: link "Xem dữ liệu" của PL-01 (`CONSENT_LONG_TERM_MEMORY`), hàng "Trợ lý ghi nhớ" ở `/notifications/settings`, banner lần đầu (PL-01 FE §2.7), nút trong `MemoryDrawer` "Mở trang quản lý". Một cột, thẻ `bg-card elevation-sm`.

## 2.4 Chat — câu dẫn bộ nhớ

Tin trợ lý có `refs.memoryRefs` ⇒ dưới câu trả lời một pill nhỏ "Dựa trên điều trợ lý nhớ" (icon `Brain`, cùng kiểu pill nguồn — DESIGN.md Chat); bấm ⇒ mở `MemoryDrawer` cuộn tới các mục đó. Giúp chủ xe thấy và xoá ngay (US-P2-PS01-03).

---

# 3. API Integration & Errors

`features/memory/api.ts`: `getMemory(vehicleId?)`, `editMemory(id, value, version)`, `deleteMemory(id)`, `deleteAllMemory()`; công tắc dùng `features/privacy/api.ts` `setConsent`.

| API | Lỗi | Xử lý |
|---|---|---|
| PS01-01 | Mạng / 5xx | Lỗi khối + "Thử lại" |
| PS01-02 | `MEMORY_DISABLED` | Ẩn "Sửa", toast |
| PS01-02 | `MEMORY_NOT_EDITABLE` | Ẩn "Sửa" |
| PS01-03 | `MEMORY_NOT_FOUND` | Bỏ mục khỏi danh sách |

---

# 4. States

| State | UI |
|---|---|
| Đang tải | Skeleton 3 nhóm |
| Đã tắt | Danh sách vẫn hiện, chỉ có "Xoá" |
| 390 px | Hành động mục xuống dòng dưới nội dung |

---

# 5. Acceptance Criteria (FE)

1. Công tắc đọc / ghi `CONSENT_LONG_TERM_MEMORY` (PL-01), không gọi `/agent-memory/settings` trực tiếp.
2. Khi tắt vẫn xoá được từng mục và tất cả.
3. Mục suy ra chưa đủ lần hiện "Đang quan sát", không có nút "Sửa".
4. Tin trợ lý có `memoryRefs` hiện pill "Dựa trên điều trợ lý nhớ".
5. `MemoryDrawer` cũ vẫn hoạt động (render bằng `MemoryPanel`).
6. Hai theme, 390 px; `npm test`, `npx tsc --noEmit -p .` qua.

---

# 6. Tests (Vitest)

| File | What | Count |
|---|---|---|
| `memory/describeMemory.test.ts` | Mô tả đọc được cho 9 khoá | +9 |
| `memory/memoryItemView.test.ts` | Nhãn nguồn, "Đang quan sát", `editable` × bật/tắt | +4 |
| `memory/undoDelete.test.ts` | Hoàn tác trong 5 s không gửi `DELETE` (hàm thuần `createUndoableAction` với đồng hồ giả) | +2 |
| `memory/MemoryPanel.test.tsx` | `renderToStaticMarkup` khi tắt: không có nút "Sửa" | +1 |

---

# 7. Truy vết FF → FE

| FF | FE |
|---|---|
| UC-PS01-04, BR-PS01-05 | §2.1–2.3 |
| UC-PS01-05, BR-PS01-06 | §2.1 công tắc |
| BR-PS01-04, UC-PS01-03 | §2.4 |
| SCR-PS01-02 | PL-01 FE §2.7 |

---

# 8. Analytics

`memory_page_viewed` (`itemCount`), `memory_item_edited` (`key`), `memory_item_deleted` (`key`, `source`), `memory_all_deleted`, `memory_pill_clicked`. Không gửi giá trị.

---

# 9. Change Log

| Version | Date | Change |
|---|---|---|
| `v0.1` | `2026-10-12` | Bản nháp đầu |
