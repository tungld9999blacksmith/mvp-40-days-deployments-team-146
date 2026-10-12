# Frontend Technical Specification — Tra cứu lịch sử bảo dưỡng phía chủ xe

> Frontend cho Feature `FEAT-P2-HS01` (SCR-HS01-01..04).
>
> **Nguồn nghiệp vụ:** [Functional Spec](hs-01-phase2-spec.ff.md). **API:** [API Spec](hs-01-phase2-spec.api.md) (`API-HS01-01..06`, thẻ `SERVICE_HISTORY_ITEM`).
>
> **Nguyên tắc:** mở rộng màn "Lịch sử dịch vụ" có sẵn (`/history`, `ServiceHistory`, `HistorySummary`, `ServiceRecordDetail` — DESIGN.md), không dựng màn mới song song. Không có ô nhập / sửa lịch sử (FF §21).

---

## 1. Document Information

| Field | Value |
|---|---|
| Document ID | `FE-SPEC-P2-HS01` |
| Version | `v0.1` |
| Status | `Draft` |
| Screens | SCR-HS01-01 (sửa `/history`), SCR-HS01-02 (sửa `ServiceRecordDetail`, thêm route chi tiết), SCR-HS01-03 (dialog), SCR-HS01-04 (trang công khai mới) |
| Routes | `/history/:recordId` (mới, dùng dưới `xl`), `/h/:token` (mới, công khai, ngoài `AppLayout`) |
| Feature folder | `frontend/src/features/maintenance/` (trang lịch sử hiện có) + `frontend/src/features/public-history/` (mới) |
| Created Date | `2026-10-12` |

---

# 2. Components

## 2.1 Lịch sử xe (SCR-HS01-01)

| Phần | Thay đổi |
|---|---|
| `HistorySummary` | Giữ nguyên; thêm nút "Chia sẻ lịch sử" (secondary, icon `Share2`) |
| Bộ lọc | Hàng chip nhóm từ `facets.categories` ("Phanh (2)") + chọn năm từ `facets.years`; đổi lọc ⇒ gọi lại API với `category` / `year`; nút "Xoá lọc" |
| Dòng thời gian | Nhóm theo năm (tiêu đề năm), mục mới trước. Mỗi mục: ngày + ODO (`font-mono`), xưởng, `itemSummary`, chi phí (`formatVnd`, kèm "ước tính" khi `kind = ESTIMATE`, "—" khi `null`), nhãn nguồn ("Từ dữ liệu hãng", "EV Care", hoặc cả hai), biểu tượng ảnh khi `hasPhotos`, badge "1 việc chưa làm" khi `deferredCount > 0` |
| Phân trang | "Xem thêm" theo `nextCursor` |
| Đồng bộ | Dòng nhỏ "Dữ liệu hãng cập nhật lúc {lastSyncedAt}" (EF-HS01-01) |
| Trống | "Xe chưa có lần bảo dưỡng nào. Lịch sử đến từ hãng và các lần làm qua EV Care." + link "Xem mốc đầu tiên" (Xe của tôi) (EF-HS01-03) |

## 2.2 Chi tiết (SCR-HS01-02)

`xl`: rail phải `ServiceRecordDetail` (như hiện tại). Dưới `xl`: route `/history/:recordId`. Gọi `API-HS01-02`.

| Khối | Nội dung |
|---|---|
| Đầu | Ngày, ODO, xưởng, nhãn nguồn; `odoNote` khi có |
| Hạng mục | Danh sách `divide-y` (DESIGN.md Decision rows): tên, loại (Phụ tùng / Công / Kiểm tra), mã phụ tùng (`font-mono`), số lượng, tiền + nhãn "ước tính" / "Bảo hành" |
| Báo giá | "Báo giá đã duyệt {total} · {approvedAt}" + link `/quotes/{quoteId}` khi có |
| Ảnh | Lưới thumbnail 56 px `rounded-xl`, chạm mở lớn (tái dùng viewer của `DecisionCard`) |
| Chưa làm | "Khuyến nghị chưa làm": tên, ngày đề xuất, giá; hạng mục an toàn có badge `ShieldAlert` "Hạng mục an toàn". Nút "Đặt lịch làm tiếp" khi `canBookFollowUp` ⇒ `runScheduler({ trigger: 'OWNER_REQUEST', itemCodes })` (BK-01) |

## 2.3 Chia sẻ lịch sử (SCR-HS01-03)

`ShareHistoryDialog`:
- Danh sách link (`API-HS01-03`): "…{tokenHint}", trạng thái, hết hạn, số lượt xem, nút "Thu hồi" (xác nhận một bước) ⇒ `API-HS01-05`.
- "Tạo link mới" (disabled khi đã 3 link, dòng giải thích): chọn hạn 7 / 14 / 30 ngày ⇒ `API-HS01-04` ⇒ hiện `url` **một lần** trong ô chỉ đọc + nút "Sao chép" (Clipboard API, fallback chọn chữ) + "Chia sẻ" (`navigator.share` khi có). Câu: "Link chỉ hiện một lần. Người nhận thấy lịch sử đã che thông tin cá nhân."
- Xem trước: link "Xem như người nhận" mở `/h/{token}` tab mới (chỉ ngay sau khi tạo).

## 2.4 Trang công khai (SCR-HS01-04)

Route `/h/:token` → `PublicHistoryPage`, nằm ngoài `AppLayout` và ngoài guard đăng nhập; layout tối giản: logo (`<Logo />`), tiêu đề "Lịch sử bảo dưỡng xe", thông tin xe đã che (`PlateTile` với biển số che), dòng thời gian chỉ đọc (cùng component mục của §2.1 ở chế độ `public`: không chi phí, không ảnh, không link), chân trang "Link hết hạn {expiresAt} · Tạo bởi EV Care".
- `404 SHARE_LINK_INACTIVE` ⇒ "Link đã hết hiệu lực" (không gợi ý đăng nhập, không lộ thông tin nào).
- `index.html` route này thêm `<meta name="robots" content="noindex,nofollow">` (đặt động trong component bằng `document.head`, gỡ khi rời) (BR-HS01-07).
- Không gọi bất kỳ API cần token chủ xe; không lưu `localStorage`.

## 2.5 Thẻ chat `SERVICE_HISTORY_ITEM`

`MessageCard` nhánh mới → `ServiceHistoryItemCard`: ngày + ODO, xưởng, tóm tắt, chi phí; nút "Xem chi tiết" → `/history/{recordId}` (chi tiết của thẻ thuộc CH-02).

---

# 3. API Integration & Errors

`features/maintenance/api.ts` (hoặc `vehicles/api.ts` nơi đang gọi service-records): `listServiceRecords(params)`, `getServiceRecord`, `listShareLinks`, `createShareLink`, `revokeShareLink`; `features/public-history/api.ts`: `getPublicHistory(token)` (fetch không header Authorization).

| API | Lỗi | Xử lý |
|---|---|---|
| HS01-01 | Mạng / 5xx | Lỗi trang + "Thử lại" (giữ bộ lọc) |
| HS01-02 | `RECORD_NOT_FOUND` | Quay về danh sách + toast |
| HS01-04 | `SHARE_LINK_LIMIT` | Dòng "Bạn đã có 3 link, hãy thu hồi một link" |
| HS01-06 | `404` / `429` | Trang hết hiệu lực / "Thử lại sau" |

---

# 4. States

| State | UI |
|---|---|
| Đang tải | Skeleton 5 mục |
| Đổi lọc | Danh sách cũ mờ + spinner nhỏ, không nhảy layout |
| 390 px | Mục dạng thẻ dọc; chip lọc cuộn ngang |

---

# 5. Acceptance Criteria (FE)

1. Mục gộp hiện một dòng với hai nhãn nguồn (AC-HS01-01).
2. `url` link chỉ hiện ngay sau khi tạo; danh sách không chứa token.
3. Trang `/h/:token` không render chi phí, ảnh, mã lịch, VIN đầy đủ (snapshot `renderToStaticMarkup`).
4. Không có ô nhập / sửa trong toàn bộ màn lịch sử.
5. Hai theme, 390 px; `npm test`, `npx tsc --noEmit -p .` qua.

---

# 6. Tests (Vitest)

| File | What | Count |
|---|---|---|
| `maintenance/historyView.test.ts` | `groupByYear`, nhãn nguồn, nhãn chi phí (`ACTUAL` / `APPROVED_QUOTE` / `ESTIMATE` / `null`) | +5 |
| `maintenance/historyFilters.test.ts` | `toQuery(filters)` / `fromQuery` | +2 |
| `maintenance/shareLinks.test.ts` | `shareLinkRowView` trạng thái; tạo bị khoá khi 3 link | +3 |
| `public-history/PublicHistoryPage.test.tsx` | `renderToStaticMarkup`: không có chuỗi giá, không VIN đầy đủ | +1 |

---

# 7. Truy vết FF → FE

| FF | FE |
|---|---|
| UC-HS01-01, BR-HS01-01/02/03, EF-HS01-01/03 | §2.1 |
| UC-HS01-02, EDGE-HS01-01/03 | §2.2 |
| UC-HS01-04/05, BR-HS01-05/08 | §2.3 |
| SCR-HS01-04, BR-HS01-07, EF-HS01-02 | §2.4 |
| UC-HS01-03 | §2.5 |

---

# 8. Analytics

`history_viewed` (`count`), `history_filter_applied` (`category`, `year`), `history_record_opened` (`source`), `history_follow_up_booking_clicked`, `history_share_created` (`days`), `history_share_revoked`, `public_history_viewed` (không gửi token).

---

# 9. Change Log

| Version | Date | Change |
|---|---|---|
| `v0.1` | `2026-10-12` | Bản nháp đầu |
