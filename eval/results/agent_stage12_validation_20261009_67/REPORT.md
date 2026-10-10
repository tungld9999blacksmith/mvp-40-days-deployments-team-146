# Đợt1/2 — kiểm tra tích hợp và smoke revision66

Ngày09/10/2026. Người dùng duyệt chạy hai đợt; giữ Mistral Small2603, không dùng judge/GPT-4o, không xóa kết quả cũ/test_agents. Đây là development validation, không nghiệm thu production.

## Kết quả

| Lượt | Kết quả | Phạm vi |
| --- | --- | --- |
| [PostgreSQL/Redis persistence](stage1_postgres_persistence_01.xml) | **1/1 PASS** | Service thật trên schema/Redis namespace riêng; mở lại engine, proposal còn; confirm lặp một booking |
| [HTTP prepare](stage1_http_prepare_01.json) + [HTTP verify](stage1_http_verify_01.json) | **17/17 PASS** | `src.main:app`, PostgreSQL/Redis riêng, Firebase thật với custom token; không override auth. Chưa có booking trước confirm; người khác bị chặn; reminder update giữ trường; concurrent replay cùng booking; chỗ cuối trả409 |
| [Chrome UI](stage1_browser_03.json) | **4/4 PASS** | Frontend/backend thật, Firebase Auth Emulator với identity Google tổng hợp, LLM stub. Lưu reminder/reload; xác nhận booking/reload; chat HTTP. Không mock API trình duyệt hoặc bypass auth |
| [HTTP/email regression](stage1_http_email_regression_01.xml) | **121/121 PASS** | SQLite/FakeRedis/auth và email transport giả lập; kiểm retry, webhook, reminder, booking. Không chứng minh Resend gửi thật |
| [Budget guard](stage2_budget_tests_01.xml) | **8/8 PASS** | Pending reserve dùng chung, receipt lỗi/thiếu dừng, tính actual vượt reserve; không phải test chất lượng Agent |
| [Mistral smoke](stage2_summary.json) | **1 API_ERROR,11 NOT_RUN** | Request đầu NEW-R02 trả429 upstream shared pool; không có đáp án mới, không chạy Generation |

Không cộng các suite overlap vào256 hồi quy trước đây hoặc tính thành accuracy chung. HTTP có17 assertion nghiệp vụ, UI có4 luồng; đây không phải21 câu LLM hoặc chiến dịch load. Postconditions: một booking CONFIRMED, bốn checkpoint của graph main, migration `c6f2a8d4e9b1`, Redis ping thành công. [Snapshot](stage1_postconditions.json).

Ảnh dữ liệu tổng hợp: [reminder](browser_reminder_03.png), [booking sau reload](browser_booking_03.png).

## Các lần lỗi giữ nguyên

- Seed lần1: helper SQLite bỏ hotline/onboarded_at, PostgreSQL constraint từ chối. Seed lần2: retry tạo trùng chủ xưởng đã commit. Hoàn thiện bằng cách dùng lại owner và bổ sung các trường fixture; không sửa constraint/runtime. [Lần1](stage1_fixture_attempt_01_error.json), [lần2](stage1_fixture_attempt_02_error.json).
- Backend harness lần1 dùng ProactorEventLoop không tương thích psycopg async. Chuyển harness sang `src.agents.checkpoint:selector_loop_factory` đã có sẵn. [Log](stage1_backend_stdout_01.log).
- Browser Firebase thật lần1: custom token đăng nhập Firebase được, nhưng `/oauth/sign-in`403 do backend chỉ cho Google. Giữ policy nguyên vẹn, không dùng lượt này tuyên bố UI production PASS. [Kết quả](stage1_browser_01.json).
- Browser emulator lần2:401 do default project namespace của emulator không khớp verifier. Sửa namespace fixture rồi chạy lại lần3 đạt4/4. CLI emulator cũng không vào trạng thái ready; dùng trực tiếp AuthEmulator server của package đã cài. Không thay logic Firebase của backend. [Lần2](stage1_browser_02.json).
- Agent request đầu của smoke:429 `upstream_provider_shared_pool` từ provider Mistral. Dừng ngay, không retry SDK, không đổi model, không chấm bằng judge. [Trace nguyên bản](stage2_case_results.jsonl).

## Thiết kế smoke và chi phí

Khóa trước [12 case](stage2_selected_cases.json) và [rubric](stage2_rubric.json): NEW-R01..R06, NEW-B01/B04, NEW-N01/N02, NEW-G01/G04. Thứ tự pilot NEW-R02 trước. Tất cả đã từng dùng development, không holdout độc lập.

Agent/Generation dùng Mistral thật khi runtime cho phép; RAG lấy evidence đã được đóng gói sau neighbor expansion và QueryAnalysis/Rewrite từ61/repeat1_base. Cập nhật original_query theo tool input mới, không lấy đáp án LLM cũ làm đáp án mới. Không đo retrieval/Rewrite live. [Cache](stage2_cached_inputs.json), [SHA-256 lock](stage2_lock.json).

Ngưỡng dừng observed receipt0,04 USD; reserve0,004 USD/request trước mỗi gọi, dùng chung Agent/Generation. Đây là dự phòng từ receipt cũ, không bảo đảm hóa đơn tối đa. Bị lỗi/receipt thiếu thì dừng các request sau. **LLM mới đã biết0 USD; một receipt429 thiếu nên phí request lỗi chưa xác định.** Không ghi phí lỗi bằng0. [Ledger](stage2_receipts.jsonl). Không có Generation, embedding, Qdrant hoặc judge request; email thật0 lần.

Tổng receipt trước đây55–64 là0,45933872225 USD, không thay đổi hoặc cộng lại. Phí embedding69 calls, judge403 và request lúc dừng60 đã thiếu trước đây vẫn chưa xác định; lượt67 bổ sung một khoản thiếu429 riêng. Không có kết quả chất lượng LLM mới để thay46PASS/5FAIL/9UNVERIFIABLE cũ.

## Giới hạn và bước tiếp

Chưa kiểm chứng Google OAuth thật qua browser, dịch vụ staging giống production với LLM thật, Resend thật/webhook live, latency/load/TTFT, semantic accuracy sau sửa, nguồn chuẩn hoặc holdout độc lập. Firebase custom-token HTTP PASS không thay Google OAuth; emulator UI PASS không thay Firebase production. SQLite/FakeRedis/email fake và Mistral request bị429 không thay các kiểm tra còn thiếu.

Sau khi upstream gọi được, mở thư mục resume mới với cùng cases/rubric/cache và nguồn đã khóa. Giữ nguyên lần429, không overwrite artifact này và không mở thêm judge/model/220 câu/holdout. Không có batch trả phí chạy nền.

Đã dọn đúng hai tài khoản Firebase fixture, file token tạm, tiến trình/cổng riêng và container có label `p146.task=agent-eval67`; Redis/application data và `.env` giữ nguyên. [Firebase cleanup](stage1_firebase_cleanup.json), [resource cleanup](stage1_resource_cleanup.json). [Đối soát cuối](final_preservation.json) xác nhận349 source revision66 và3.022 file lịch sử/dataset/evaluator/test_agents bảo toàn; không sửa vấn đề seal lịch sử đã nêu ở báo cáo tổng hợp.

[Báo cáo đầy đủ cho mentor/team](../../../docs/AGENT_EVALUATION_SUMMARY_20261009.md) tự chứa phương pháp, các kết quả model trước đây, chi phí và giới hạn; không cần gửi plan.
