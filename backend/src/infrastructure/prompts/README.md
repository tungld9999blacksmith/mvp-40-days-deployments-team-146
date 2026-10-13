# Prompt versioning

**Nguồn gốc (source of truth) của mỗi prompt là hằng số chuỗi ngay trong file `.py` dùng nó.**
`texts/<tên>.txt` (UTF-8) là bản **sinh tự động** từ code để git giữ lịch sử và để đẩy lên LangSmith Prompt Hub;
đừng sửa tay. `texts/versions.lock.json` ghi **số version** và **sha256** của từng prompt.

| Prompt | Hằng số trong code (nguồn gốc) |
|---|---|
| `ev_care_base` | `EV_CARE_BASE_PROMPT` ở `agents/prompts.py` (system prompt chính của agent chat) |
| `customer_chat` | `_SYSTEM_PROMPT` ở `modules/conversation/service.py` |
| `rag_generator` | `SYSTEM_PROMPT` ở `agents/tools/RAG/query/generator.py` |
| `rag_rewriter` | `SYSTEM_PROMPT` ở `agents/tools/RAG/query/rewriter.py` |
| `tool_review` | `REVIEW_PROMPT` ở `agents/tool_review.py` (kiểm tra lời gọi tool trước khi chạy) |
| `follow_up_classifier` | `SYSTEM_PROMPT` ở `modules/follow_up/classifier.py` |
| `injection_note` | `INJECTION_SYSTEM_NOTE` ở `agents/conversation_guards/input_guard.py` |

Bảng ánh xạ này nằm trong `PROMPT_SOURCES` (`registry.py`). Thêm prompt mới = thêm một dòng vào đó.

## 1. Sửa prompt

```
# 1. Sửa hằng số prompt trong file .py (bảng ở trên)
# 2. Sinh lại texts/<tên>.txt từ code và tăng version (+1 cho prompt đã đổi)
cd backend && uv run python scripts/prompt_sync.py lock
# 3. Chạy test, rồi commit .py, .txt và versions.lock.json
```

Test `tests/test_infrastructure/test_prompt_versions.py` sẽ **đỏ** nếu sửa prompt mà quên bước `lock`,
hoặc nếu `.txt` bị sửa tay / lệch với code.

## 2. Push / pull với LangSmith Prompt Hub

Cần `LANGCHAIN_API_KEY`, `LANGCHAIN_ENDPOINT`, `LANGCHAIN_WORKSPACE_ID` trong `.env` gốc.
Mỗi prompt là một repository trên Hub, tên `ev-care-<tên-có-gạch-ngang>` (đổi bằng `--prefix`).

```
cd backend
uv run python scripts/prompt_sync.py status                 # version, trạng thái lock và Hub
uv run python scripts/prompt_sync.py push                   # đẩy các prompt chưa đồng bộ, tag v<version>
uv run python scripts/prompt_sync.py push rag_generator     # đẩy một prompt
uv run python scripts/prompt_sync.py pull                   # so bản mới nhất của Hub với code
uv run python scripts/prompt_sync.py pull ev_care_base --commit <hash>   # so đúng một commit
uv run python scripts/prompt_sync.py pull --out hub_texts   # lưu thêm text của Hub vào thư mục
```

- `push` từ chối nếu prompt đã sửa mà chưa chạy `lock`.
- `pull` **chỉ in diff** (code so với Hub), không ghi vào code, `.txt` hay lock, vì nguồn gốc là file `.py`.
- Dùng khi sửa prompt trên Playground của LangSmith: `pull` để xem khác biệt, chép phần muốn giữ vào hằng số
  trong `.py`, rồi `lock`, test, commit.

## 3. Runtime và trace

- Agent dùng chuỗi prompt ngay trong code; **không gọi Hub và không đọc file `.txt` khi chạy**, nên Hub lỗi không ảnh hưởng chat.
  Đổi prompt trên production = đưa file mới qua git và deploy.
- Mỗi lượt chat, trace `agent.turn` có metadata `prompt_version`, ví dụ `ev_care_base@v3`.
  Lọc trên LangSmith theo metadata này để biết lượt nào dùng bản nào.
- Hub không tự quyết định prompt nào đang chạy; nguồn thật là git.
