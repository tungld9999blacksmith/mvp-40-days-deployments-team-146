# Frontend Technical Specification — Quyền riêng tư và sự đồng ý

> Frontend cho Feature `FEAT-P2-PL01` (SCR-PL01-01..03).
>
> **Nguồn nghiệp vụ:** [Functional Spec](pl-01-phase2-spec.ff.md). **API:** [API Spec](pl-01-phase2-spec.api.md) (`API-PL01-01..04`).
>
> **Nguyên tắc:** frontend không tự quyết định mặc định hay hiệu lực của đồng ý; luôn hiển thị `status` / `effective` do backend trả. Kiểm tra đồng ý ở frontend chỉ để quyết định có hiện hộp hỏi hay không, backend vẫn là cổng chặn.

---

## 1. Document Information

| Field | Value |
|---|---|
| Document ID | `FE-SPEC-P2-PL01` |
| Version | `v0.1` |
| Status | `Draft` |
| Screens | SCR-PL01-01 (mới, trang), SCR-PL01-02 (mới, hộp thoại dùng chung), SCR-PL01-03 (mới, hộp thoại) |
| Routes | `/settings/privacy` (mới) |
| Feature folder | `frontend/src/features/privacy/` (mới) |
| Created Date | `2026-10-12` |

---

# 2. Components

## 2.1 Điều hướng

| | |
|---|---|
| Sidebar chủ xe (`layouts/AppLayout.tsx`) | Không thêm mục mới (DESIGN.md: không đổi điều hướng). Vào từ `/notifications/settings`: thêm hàng "Quyền riêng tư" (icon `ShieldCheck`) ở cuối trang, link `/settings/privacy` |
| Route | `/settings/privacy` → `PrivacyPage`, bọc `RequireOwner` như các trang chủ xe khác |
| Link sâu | Hộp hỏi trong luồng có link "Quản lý quyền riêng tư" tới route này |

## 2.2 `PrivacyPage` (SCR-PL01-01)

File `features/privacy/pages/PrivacyPage.tsx`. Một cột, thẻ `bg-card elevation-sm rounded-2xl`, các hàng `divide-y divide-border` (không lồng thẻ).

| Vùng | Nội dung |
|---|---|
| Đầu trang | Tiêu đề "Quyền riêng tư"; một câu: "Bạn quyết định EV Care được dùng dữ liệu nào. Tắt là dừng dùng ngay." |
| 5 hàng `ConsentRow` | Thứ tự như FF §3.1 |
| Chân trang | "Phiên bản giải thích: {policyVersion}" (`font-mono`, `text-muted`) |

## 2.3 `ConsentRow`

| Phần | Nội dung |
|---|---|
| Tên + giải thích | Từ `CONSENT_COPY[code]` (§2.6) |
| Công tắc | `Switch` có `aria-label` = tên; `checked = item.effective` |
| Nhãn phụ | `source = DEFAULT` ⇒ "Đang theo mặc định"; `deletion.status ∈ {PENDING, RUNNING}` ⇒ "Đang xoá dữ liệu, xong trước {dueAt}" |
| "Xem dữ liệu" | Khi `hasViewData`: bộ nhớ → `/settings/memory` (PS-01), lịch → `/settings/calendar` (BK-04) |
| "Xoá dữ liệu liên quan" | Nút ghost màu lỗi (button danger); mở SCR-PL01-03. Ẩn với `CONSENT_AUTO_BOOKING` (không có dữ liệu riêng) |

**Bật/tắt:**
1. Tắt: gọi ngay `PUT …/{code}` `{ granted: false, channel: 'PRIVACY_SCREEN', expectedVersion }`. Không hộp xác nhận (tắt không mất dữ liệu).
2. Bật `CONSENT_LOCATION`: gọi `navigator.geolocation.getCurrentPosition` trước; bị từ chối ⇒ không gọi API, hiện dòng "Trình duyệt đang chặn vị trí. Mở cài đặt trình duyệt để cho phép."
3. Bật `CONSENT_AUTO_BOOKING`: mở `DecisionSheet` (DESIGN.md) "Cho phép EV Care tự đặt lịch khi có khung phù hợp? Bạn huỷ miễn phí trong {AUTO_BOOK_FREE_CANCEL_HOURS} giờ." (giá trị lấy từ `GET /scheduling/config`, BK-01). Đồng ý ⇒ gọi API.
4. Trong lúc gọi: công tắc disabled + spinner nhỏ; cập nhật lạc quan, lỗi thì trả về giá trị cũ.
5. Tắt `CONSENT_CALENDAR_SYNC` hiện toast "Đã ngắt đồng bộ lịch. Sự kiện đã tạo vẫn còn trong lịch của bạn; xoá ở mục Xoá dữ liệu liên quan."

## 2.4 `ConsentPromptDialog` (SCR-PL01-02, dùng chung)

File `features/privacy/components/ConsentPromptDialog.tsx`, hook `useConsentGate(code, sourceFeature)`.

```ts
const gate = useConsentGate('CONSENT_CALENDAR_SYNC', 'BK-04');
const ok = await gate.ensure(); // true nếu đã/vừa đồng ý; false nếu từ chối
```

- `ensure()`: đọc `useConsents()` (cache React Query-like trong `features/privacy/api.ts`, staleTime 60 s). `effective = true` ⇒ trả `true` không hỏi. `status = REVOKED` ⇒ trả `false` **không hỏi lại** (chủ xe đã tắt; muốn bật thì vào màn Quyền riêng tư). `NOT_ASKED` ⇒ mở hộp.
- Hộp: `Dialog` (bottom sheet ở 390 px, `rounded-3xl`), tiêu đề + một câu giải thích (`CONSENT_COPY`), nút "Đồng ý" (primary) và "Không, cảm ơn" (secondary), link "Quản lý quyền riêng tư".
- "Đồng ý" ⇒ `PUT { granted: true, channel: 'IN_FLOW_PROMPT', sourceFeature }`; "Không" ⇒ `PUT { granted: false, … }` rồi `false`. Đóng hộp bằng Esc / chạm ngoài = "Không" nhưng **không** gọi API (vẫn `NOT_ASKED`, lần sau hỏi lại).
- Luồng gọi `ensure()` phải chạy tiếp ở mức thấp hơn khi nhận `false` (BR-PL01-05); ví dụ BK-05 hiện ô chọn khu vực.

## 2.5 `DeleteDataDialog` (SCR-PL01-03)

| Mã | Nội dung xác nhận | Tuỳ chọn |
|---|---|---|
| `CONSENT_LONG_TERM_MEMORY` | "Xoá mọi điều trợ lý đã nhớ về bạn và xe. Trợ lý sẽ bắt đầu lại từ đầu." | — |
| `CONSENT_CALENDAR_SYNC` | "Ngắt kết nối lịch và xoá dữ liệu bận/rảnh đã lưu." | Checkbox "Xoá cả các sự kiện EV Care đã tạo trong lịch của tôi" (mặc định bỏ chọn ⇒ `keepCreatedEvents = true`) |
| `CONSENT_LOCATION` | "Xoá vị trí đã lưu. Bạn vẫn chọn được khu vực khi đặt lịch." | — |
| `CONSENT_PERSONALIZATION_DATA` | "Xoá đánh giá và phản hồi gợi ý dùng để cá nhân hoá." | — |

- Dòng chung: "Việc xoá hoàn tất trong {DELETE_SLA_HOURS} giờ. Công tắc sẽ được tắt." (khi đang bật).
- Nút xác nhận `alertdialog` + button danger "Xoá dữ liệu"; gọi `API-PL01-03`; thành công ⇒ toast "Đã ghi nhận yêu cầu xoá" + hàng chuyển nhãn "Đang xoá…"; sau đó poll `API-PL01-04` mỗi 30 s khi trang mở, dừng khi `DONE`.

## 2.6 Copy

`features/privacy/copy.ts`:

| Mã | Tên | Giải thích (một câu) |
|---|---|---|
| `CONSENT_LONG_TERM_MEMORY` | Bộ nhớ dài hạn của trợ lý | Trợ lý nhớ thói quen và lựa chọn của bạn giữa các cuộc trò chuyện. |
| `CONSENT_CALENDAR_SYNC` | Đồng bộ lịch | Đọc giờ bận/rảnh để gợi ý lịch hẹn và thêm lịch hẹn vào lịch của bạn. |
| `CONSENT_LOCATION` | Vị trí thiết bị | Dùng vị trí hiện tại để tìm xưởng gần bạn. |
| `CONSENT_PERSONALIZATION_DATA` | Dữ liệu cho gợi ý | Dùng đánh giá dịch vụ và phản hồi của bạn để gợi ý xưởng, khung giờ phù hợp hơn. |
| `CONSENT_AUTO_BOOKING` | Tự đặt lịch | Cho phép EV Care tự đặt lịch khi có khung phù hợp với ràng buộc của bạn. |

Văn bản phải được người hiểu quy định bảo vệ dữ liệu cá nhân duyệt trước khi phát hành (FF §23); đổi văn bản thì backend tăng `PRIVACY_POLICY_VERSION`.

## 2.7 Thông báo lần đầu bộ nhớ dài hạn

Ở AI trợ lý (`features/assistant/pages/AIAssistant.tsx`): khi `CONSENT_LONG_TERM_MEMORY.status = NOT_ASKED`, hiện banner một lần trên khung chat: "Trợ lý sẽ nhớ thói quen của bạn để gợi ý tốt hơn. [Quản lý]". Hiện xong ⇒ `PUT { granted: true, channel: 'FIRST_RUN_NOTICE' }`. Bấm "Quản lý" ⇒ `/settings/privacy`.

---

# 3. API Integration & Errors

`features/privacy/api.ts`: `getConsents()`, `setConsent(code, body)`, `requestDeletion(code, options)`, `getLatestDeletion(code)`; kiểu ở `features/privacy/types.ts` đúng theo API §3–6.

| API | Lỗi | Xử lý |
|---|---|---|
| PL01-01 | Mạng / 5xx | Trạng thái lỗi trang + "Thử lại"; **mọi `useConsentGate.ensure()` trả `false`** (an toàn, BR-PL01-06) |
| PL01-02 | `CONSENT_VERSION_CONFLICT` | Tải lại danh sách, toast "Cài đặt vừa thay đổi ở nơi khác" |
| PL01-02 | Khác | Trả công tắc về giá trị cũ + toast lỗi chung |
| PL01-03 | `503` | Lỗi trong hộp xoá + "Thử lại" (idempotent) |
| Mọi API | `401` | Như các trang chủ xe (về đăng nhập) |

---

# 4. States

| State | UI |
|---|---|
| Đang tải | 5 hàng skeleton |
| Đang đổi một công tắc | Chỉ công tắc đó disabled |
| Đang xoá | Nhãn "Đang xoá dữ liệu…", nút xoá ẩn |
| Mobile 390 px | Công tắc bên phải tên; giải thích xuống dòng; nút xoá xuống dòng riêng, full width |

---

# 5. Acceptance Criteria (FE)

1. Trang có đúng 5 công tắc theo thứ tự FF §3.1; giá trị = `effective`.
2. Tắt công tắc gọi đúng một `PUT` với `channel = PRIVACY_SCREEN`.
3. `useConsentGate.ensure()` không mở hộp khi `REVOKED`, mở hộp khi `NOT_ASKED`, trả `false` khi tải đồng ý lỗi.
4. Đóng hộp hỏi bằng Esc không gọi API.
5. Hộp xoá lịch gửi `keepCreatedEvents = false` chỉ khi checkbox được chọn.
6. Kiểm tra cả hai theme và 390 px (DESIGN.md).
7. `npm test`, `npx tsc --noEmit -p .` qua; không thêm dependency.

---

# 6. Tests (Vitest, hàm thuần)

| File | What | Count |
|---|---|---|
| `privacy/consentView.test.ts` | `consentRowView(item)` → nhãn phụ, có nút xoá, link xem dữ liệu cho 5 mã | +5 |
| `privacy/consentGate.test.ts` | `decideGate(state)` → `ALLOW` / `DENY` / `ASK` cho `GRANTED` / `REVOKED` / `NOT_ASKED` / lỗi tải | +4 |
| `privacy/deletionRequest.test.ts` | `buildDeletionOptions(code, keepEvents)` | +2 |

---

# 7. Truy vết FF → FE

| FF | FE |
|---|---|
| UC-PL01-01, BR-PL01-01 | §2.2, §2.3 |
| UC-PL01-05, BR-PL01-05 | §2.4 |
| UC-PL01-04 | §2.5 |
| BR-PL01-06, AC-PL01-04 | §3 (lỗi ⇒ `false`) |
| AF-PL01-01 | §2.3 bước 5, §2.5 |

---

# 8. Analytics

`privacy_page_viewed`, `consent_toggled` (`code`, `granted`, `channel`, `sourceFeature`), `consent_prompt_shown` (`code`, `sourceFeature`), `consent_prompt_dismissed`, `data_deletion_requested` (`code`). Không gửi dữ liệu cá nhân.

---

# 9. Change Log

| Version | Date | Change |
|---|---|---|
| `v0.1` | `2026-10-12` | Bản nháp đầu |
