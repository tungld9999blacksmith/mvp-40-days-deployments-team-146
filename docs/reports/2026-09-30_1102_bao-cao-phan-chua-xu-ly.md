# Báo cáo các phần chưa xử lý — Đặc tả so với PRD EV Care MVP

| Mục | Giá trị |
|---|---|
| Thời điểm lập | **30/09/2026 11:02 (GMT+7, Asia/Ho_Chi_Minh)** |
| Người lập | Claude Code (theo yêu cầu của Lê Đức Tùng) |
| Nhánh | `develop` (commit gốc `baf049a`) |
| Tài liệu đối chiếu | [PRD_EV_Care_MVP.md](../product/PRD_EV_Care_MVP.md) — bảng thông tin ghi v3.5, change log tới v3.6 |
| Phạm vi rà soát | `docs/specs/**` (FF, API, FE, Entity, Agent), `docs/product`, một phần `backend/`, `frontend/`, `eval/` |
| Báo cáo đi kèm | [Rà soát logic nghiệp vụ](2026-09-30_1102_bao-cao-ra-soat-logic-nghiep-vu.md) |

---

## 1. Tóm tắt

- PRD có **12 tính năng** (F1…F9, F5b, F6b, F8b). Trước lần rà soát này, **4 tính năng chưa có bộ đặc tả** (F5, F5b, F6b, F8b) và **F6 thiếu Frontend Spec**, dù các tài liệu khác đã trỏ tới chúng ("FF F5 `[Chưa có]`", "F6b — tài liệu riêng"…).
- Đã tạo **17 tài liệu đặc tả mới** (≈ 5.200 dòng) theo đúng template trong `docs/specs/templates` và cập nhật link ở **7 tài liệu cũ**. Chi tiết ở mục 3.
- Sau lần bổ sung này, mọi tính năng trong PRD §5 đều có FF + API + FE + Entity. Vẫn còn **các hạng mục chưa xử lý** (mục 4): Tech Spec chốt LLM, Prompt Spec, bộ eval, seed dữ liệu định mức/giá, Test Cases, và PRD cần nâng lên v3.7 để khớp các quyết định mới.
- Toàn bộ điểm mới có giá trị mặc định đánh dấu `[Đề xuất]` và cần PO/Tech Lead chốt — **26 câu hỏi mở** tổng hợp ở mục 5.

---

## 2. Ma trận độ phủ đặc tả theo PRD §5

Ký hiệu: ✅ có từ trước · 🆕 tạo mới trong lần này · — không áp dụng

| PRD | Tính năng | Ưu tiên | FF | API | FE | Entity | Agent |
|---|---|---|---|---|---|---|---|
| F1 | Đăng ký/đăng nhập chủ xe | Must | ✅ us-001, us-005 | ✅ | ✅ | ✅ | — |
| F2 | Đăng ký/đăng nhập chủ xưởng | Must | ✅ us-009, us-013 | ✅ | ✅ | ✅ | — |
| F3 | Hồ sơ xe & trạng thái đến hạn | Must | ✅ us-017 | ✅ | ✅ | ✅ | ✅ AI-001 tool |
| F4 | Chat RAG + lưu hội thoại | Must | ✅ us-025 | ✅ us-025 + platform | ✅ | ✅ + ENT-421…423 | ✅ AI-001, 002, 008 |
| **F5** | **Dự toán chi phí** | Must | 🆕 [us-045 FF](../specs/sprint-2/feature-functional/us-045-sprint-2-spec.ff.md) | 🆕 [API](../specs/sprint-2/api/us-045-sprint-2-spec.api.md) | 🆕 [FE](../specs/sprint-2/frontend/us-045-sprint-2-spec.fe.md) | 🆕 [Entity](../specs/sprint-2/entity/us-045-sprint-2-spec.entity.md) | ✅ AI-003 |
| F6 | Đặt lịch theo sức chứa | Must | ✅ us-029 | ✅ | 🆕 [us-029 FE](../specs/sprint-3/frontend/us-029-sprint-3-spec.fe.md) | ✅ | ✅ AI-004 |
| F8 | Workshop Board | Must | ✅ us-037 | ✅ | ✅ | ✅ | — |
| **F5b** | **Báo giá HITL** | Should | 🆕 [us-049 FF](../specs/sprint-3/feature-functional/us-049-sprint-3-spec.ff.md) | 🆕 [API](../specs/sprint-3/api/us-049-sprint-3-spec.api.md) | 🆕 [FE](../specs/sprint-3/frontend/us-049-sprint-3-spec.fe.md) | 🆕 [Entity](../specs/sprint-3/entity/us-049-sprint-3-spec.entity.md) | ✅ AI-005 |
| F7 | Nhắc mốc + nhắc lịch hẹn | Should | ✅ us-021, us-033 | ✅ | ✅ | ✅ | ✅ AI-006 |
| **F6b** | **Ticket + QR, huỷ/đổi lịch** | Should | 🆕 [us-053 FF](../specs/sprint-3/feature-functional/us-053-sprint-3-spec.ff.md) | 🆕 [API](../specs/sprint-3/api/us-053-sprint-3-spec.api.md) | 🆕 [FE](../specs/sprint-3/frontend/us-053-sprint-3-spec.fe.md) | 🆕 [Entity](../specs/sprint-3/entity/us-053-sprint-3-spec.entity.md) | ✅ AI-004 |
| F9 | Hỏi thăm sau dịch vụ + phiếu hỗ trợ | Could | ✅ us-041 | ✅ | ✅ | ✅ | ✅ AI-007 |
| **F8b** | **Tiến độ chi tiết 6 bước** | Could | 🆕 [us-057 FF](../specs/sprint-4/feature-functional/us-057-sprint-4-spec.ff.md) | 🆕 [API](../specs/sprint-4/api/us-057-sprint-4-spec.api.md) | 🆕 [FE](../specs/sprint-4/frontend/us-057-sprint-4-spec.fe.md) | 🆕 [Entity](../specs/sprint-4/entity/us-057-sprint-4-spec.entity.md) | — |

**Quy ước đánh số đã dùng:** tiếp tục bước nhảy 4 của US (…, 041 → **045, 049, 053, 057**); dải mã riêng cho mỗi feature để không trùng: F5 `10xx`, F5b `11xx`, F6b `12xx`, F8b `13xx` (BR/UC/AC/EDGE/SCR/Q). Entity mới: **ENT-428** `booking_reschedule`. F5 đặt ở `sprint-2` theo PRD (S2).

---

## 3. Những gì đã làm trong lần này

### 3.1 Tài liệu mới (17)

| Feature | Tài liệu | Nội dung chính |
|---|---|---|
| F5 `FEAT-COST-001` | FF, API, FE, Entity | Công thức dự toán tất định (BR-1001), thứ tự nguồn giá (BR-1004), không đưa số khi thiếu định mức (BR-1009), xe hết bảo hành (AF-1004), 3 API `API-EST-01…03` dùng chung `CostEstimationService` với tool AI-003; không tạo bảng mới |
| F5b `FEAT-QUOTE-001` | FF, API, FE, Entity | Nháp **luôn tính lại ở backend** (không nhận giá từ client/LLM — BR-1101), chặn trùng chờ duyệt, chủ xưởng sửa giá dòng + chọn hiệu lực 1–30 ngày, từ chối bắt buộc lý do, gắn/gỡ báo giá với booking; 9 API + job dọn nháp; mở rộng `quote`, `quote_item` |
| F6b `FEAT-BOOK-002` | FF, API, FE, Entity | Nội dung Ticket, định dạng `booking_code`, nội dung QR (chỉ URL + mã), "Lịch của tôi", **đổi lịch tại chỗ nguyên tử** (giữ khung mới trước, trả khung cũ khi commit), hạn đổi 60', tối đa 2 lần; bảng mới `booking_reschedule`; cột `booking.odo_milestone`, `reschedule_count` |
| F8b `FEAT-PROG-001` | FF, API, FE, Entity | 6 mốc, bảng chuyển tiếp hợp lệ, mốc tự động khi CHECK_IN/START, ghi chú bắt buộc khi chờ phụ tùng, thông báo ở 2 mốc; sửa cột người cập nhật của `service_progress` |
| F6 `FEAT-BOOK-001` | FE | Wizard 3 bước, `BookingSummaryCard` dùng chung chat + UI, ánh xạ toàn bộ mã lỗi `API-BK-01…04` |

### 3.2 Tài liệu cũ được cập nhật (chỉ sửa link, không đổi logic)

| File | Thay đổi |
|---|---|
| `ai-agent/ai-002`, `ai-008` | "FF F4 `[Chưa có]`" → link us-025 (FF F4 đã tồn tại nhưng agent spec chưa cập nhật) |
| `ai-agent/ai-003` | "FF F5 `[Chưa có]`", API → link us-045 |
| `ai-agent/ai-004` | "FF F6 / F6b `[Chưa có]`", API → link us-029 + us-053 |
| `ai-agent/ai-005` | "FF F5b `[Chưa có]`", API → link us-049 |
| `sprint-3/feature-functional/us-029` | "Related Frontend Spec `[Chưa có]`" → us-029 FE; "F6b/F8 (tài liệu riêng)" → link |
| `sprint-3/feature-functional/us-033` | "F6b (tài liệu riêng)" → link us-053 |

Đã kiểm tra tự động: **0 link tương đối bị hỏng** trong các file mới/sửa.

---

## 4. Các phần CHƯA xử lý

### 4.1 Tài liệu PRD có nhắc nhưng chưa tồn tại

| # | Hạng mục | PRD nhắc ở đâu | Hiện trạng | Đề xuất / Owner |
|---|---|---|---|---|
| U-01 | **Tech Spec** chốt LLM ("Gemini Flash-tier — chốt ở Tech Spec") | §9, Phụ lục A.2 #10 | Không có tài liệu; code mặc định `llm_provider = "openai"` (`backend/src/config.py`) | Tech Lead viết ADR/Tech Spec ngắn chốt model + provider trước M4 (05/10) |
| U-02 | **Bộ eval**: ≥ 60 câu RAG có đáp án, ≥ 15 câu bẫy, ≥ 50 câu NLU đặt lịch | §10 | `eval/datasets/README.md`: "Chưa có bộ dữ liệu đánh giá thực tế" | AI Team; cần xong trước Demo 1 để đo AC-F4 |
| U-03 | **Danh sách tài liệu chính hãng ingest** (PQ-06, hạn 04/10) | §12, §14 | Chưa có tài liệu chốt | PO; ảnh hưởng AI-008 và AC-F4 |
| U-04 | **Prompt / Knowledge Spec** cho agent | Template agent + AI-001…007 ghi `[Chưa có]` | Chưa có | AI Team (không bắt buộc bởi PRD nhưng các agent spec đều trỏ tới) |
| U-05 | **Test Cases / Test Specification** | Template FF §25; `[Chưa có]` ở us-025/033/037/041, AI-001…007 | Chưa có | QA/Backend; ưu tiên AC-F6-01 (tải đồng thời) |
| U-06 | **Runbook** triển khai staging | §11 M7 | Có `docs/RUN_LOCAL_BACKEND*.md` (local), chưa có runbook staging/pilot | DevOps trước 26/10 |
| U-07 | Khảo sát pain point | §2, §12 | [surveys.md](../../personal/tungld-03005/surveys.md) có, chưa có kết quả | PO trước Demo 2 |

### 4.2 Dữ liệu / hạ tầng cần có để spec chạy được

| # | Hạng mục | Hiện trạng (kiểm tra 30/09) | Ảnh hưởng |
|---|---|---|---|
| U-08 | Seed `maintenance_rule` theo model + mốc | `backend/seed.sql` **không có** `INSERT` | F3 luôn `UNKNOWN`, F5 luôn `NO_RULE` |
| U-09 | Seed `service_price` cho 3–5 xưởng mock | Không có | F5 toàn giá tham khảo; F5b không có ý nghĩa |
| U-10 | Migration cho các cột/bảng mới đề xuất | Chưa có (chờ duyệt spec) | `quote.submitted_at`, `result_seen_at`; `quote_item.is_covered_by_warranty`, `price_source`, `reviewer_note`; `booking.odo_milestone`, `reschedule_count`; `booking_reschedule`; `service_progress.actor_*` |

### 4.3 Triển khai code (tham khảo — không thuộc phạm vi đặc tả)

| Tính năng | Backend (`backend/src/modules`) | Frontend (`frontend/src/features`) |
|---|---|---|
| F6 đặt lịch | Có `booking/route.py` với `API-BK-01…04` | `/booking`, `/booking-success` còn dữ liệu mock |
| F5 dự toán | Chưa có module/endpoint | `/estimate` mock |
| F5b báo giá | Chỉ có model `quote`, `quote_item` | `/technician/quotes`, `/technician/quote-review` mock (cho thêm/xoá dòng — lệch spec, xem báo cáo logic L-17) |
| F7 nhắc 24h, F8 Board, F9, F6b, F8b | Chưa có endpoint | Chưa có hoặc mock |
| Conversation (F4) | Có, **chưa gắn auth** trên route (đã biết, cần thêm trước prod) | `/ai` |

### 4.4 Việc cần làm ở tài liệu gốc (chưa tự sửa vì cần owner duyệt — INSTRUCTION.MD §8)

| # | Tài liệu | Việc |
|---|---|---|
| D-01 | PRD | Nâng v3.7: cập nhật F6 (giữ chỗ/xác nhận xưởng), AC-F6-03, F8 (chấp nhận/từ chối), §15 Truy vết thêm us-045/049/053/057, bảng thông tin (đang ghi v3.5), Phụ lục B NOTI-01, §9 Frontend (Vite, không phải Next.js) — chi tiết ở báo cáo logic |
| D-02 | `booking.entity.md` | v1.3: thêm `odo_milestone`, `reschedule_count`; ghi rõ quy ước "mã sinh khi tạo, chỉ lộ khi `confirmed`"; sửa ví dụ mã |
| D-03 | `quote.entity.md`, `quote_item.entity.md` | v1.2 theo us-049 Entity |
| D-04 | `service_progress.entity.md` | Mở lại Q-403; thêm cột người ghi |
| D-05 | `us-029` FF/API | Sửa các câu mâu thuẫn nội bộ (BR-001, EF-005, §7 API), lưu `milestoneRef`, đổi tên mã lỗi `HOLD_EXPIRED` |
| D-06 | `ai-004` | Đóng AI-Q-401/402/403 theo quyết định us-029; TOOL-406 trả cùng booking |
| D-07 | `ai-005` | TOOL-501 không nhận `items[]` từ LLM (theo us-049 BR-1101) |
| D-08 | `sprint-1` us-001 | Bỏ dropdown chọn model (`API-004`) cho khớp PRD F1 |

---

## 5. Câu hỏi mở cần PO / Tech Lead chốt (phát sinh từ tài liệu mới)

| ID | Câu hỏi | Mặc định đề xuất |
|---|---|---|
| Q-1001 | Xe hết bảo hành xác định từ component nào (enum không có "bảo hành chung")? | Tạm dùng `chassis`; phase sau thêm `maintenance_rule.warranty_component` |
| Q-1002 | EDGE-003 "mẫu xe tương đương" vs no-source-no-claim | Không đưa số |
| Q-1003 | So sánh dự toán nhiều xưởng trong MVP? | Có, tối đa 3 |
| Q-1004 | Chuẩn hoá mốc chủ xe nêu tự do | Mốc ≥ gần nhất |
| Q-1005 | Màn quản lý bảng giá cho chủ xưởng? | Không trong MVP |
| Q-1006 | Dự toán theo giá ngày hẹn thay vì hôm nay? | Hôm nay |
| Q-1101 | Discord khi có kết quả báo giá? | Không, chỉ in-app + chat |
| Q-1102 | Chủ xưởng thêm/bỏ hạng mục khi duyệt? | Không; đặt 0 + ghi chú |
| Q-1103 | Đổi dòng bảo hành sang tính phí? | Không |
| Q-1104 | Nháp > 24h lập lại snapshot trước khi gửi? | Có |
| Q-1105 | Báo giá chờ lâu có tự huỷ? | Không; nhãn "Chờ > 24h" |
| Q-1201 | Đổi sang xưởng khác trong một thao tác? | Không; huỷ + đặt mới |
| Q-1202 | Hạn chót đổi lịch | 60' trước giờ hẹn |
| Q-1203 | Số lần đổi tối đa | 2 |
| Q-1204 | Định dạng `booking_code` (code: `EVC-` + 8 hex; tài liệu có 3 kiểu khác nhau) | Giữ như code, sửa ví dụ trong tài liệu |
| Q-1205 | Nút thêm vào lịch (.ics) | Phase sau |
| Q-1206 | Giấy tờ cần mang theo xưởng? | Cấu hình chung |
| Q-1207 | Xưởng `manual`: đổi lịch cần duyệt lại? | Không |
| Q-1208 | Chủ xe rút yêu cầu `pending` sau 10'? | **Cho phép** (hiện us-029 không cho — xem báo cáo logic L-03) |
| Q-1301 | Bắt buộc "Sẵn sàng giao xe" trước khi Hoàn tất? | Không, chỉ cảnh báo |
| Q-1302 | Hoàn tác mốc tiến độ? | Không |
| Q-1303 | Ghi chú tiến độ hiển thị cho chủ xe? | Có |
| Q-1304 / Q-ENT-1301 | `service_progress.updated_by integer` không chứa được `uuid` | Thêm `actor_workshop_owner_id` |
| Q-ENT-1002 | Exclusion constraint cho hiệu lực `service_price` | Có (`btree_gist`) |
| Q-ENT-1201 | Regex mã booking ở us-037 | Giữ `^[A-Z0-9-]{4,20}$` (vẫn khớp) |
| Q-ENT-1103 | Gom `result_seen_at` vào bảng thông báo in-app chung | Phase sau |

---

## 6. Đề xuất thứ tự xử lý

1. **Trước 04/10 (M3):** chốt Q-1001, Q-1002, Q-1204, Q-1208; viết Tech Spec LLM (U-01); seed định mức + bảng giá (U-08, U-09); nâng PRD v3.7 (D-01).
2. **Trước Demo 1 (11/10):** triển khai F5 theo us-045; bộ eval RAG (U-02).
3. **Trước 18/10 (M5):** migration mục U-10; F5b, F6b; sửa D-02…D-07.
4. **Chỉ khi Must đạt Demo 2:** F8b (Could).
