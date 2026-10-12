# Prompt versioning

Prompt của agent và các bước LLM nằm trong `texts/<tên>.txt` (UTF-8), không nằm trong code Python.
Git giữ lịch sử từng bản; `texts/versions.lock.json` ghi **số version** và **sha256** của từng prompt.

| Prompt | Dùng ở |
|---|---|
| `ev_care_base` | System prompt chính của agent chat (`agents/prompts.py`) |
| `customer_chat` | Trợ lý chat trong `modules/conversation/service.py` |
| `rag_generator` / `rag_rewriter` | Pipeline RAG (`agents/tools/RAG/query/`) |
| `tool_review` | Kiểm tra lời gọi tool trước khi chạy (`agents/tool_review.py`) |
| `follow_up_classifier` | Phân loại phản hồi sau bảo dưỡng (`modules/follow_up/classifier.py`) |
| `injection_note` | Ghi chú an toàn khi phát hiện prompt injection |

## 1. Sửa prompt

```
# 1. Sửa file texts/<tên>.txt
# 2. Tăng version (đọc sha256 mới, version +1 cho prompt đã đổi)
cd backend && uv run python scripts/prompt_sync.py lock
# 3. Chạy test, rồi commit cả .txt và versions.lock.json
```

Test `tests/test_infrastructure/test_prompt_versions.py` sẽ **đỏ** nếu sửa file mà quên bước `lock`.

## 2. Push / pull với LangSmith Prompt Hub

Cần `LANGCHAIN_API_KEY`, `LANGCHAIN_ENDPOINT`, `LANGCHAIN_WORKSPACE_ID` trong `.env` gốc.
Mỗi prompt là một repository trên Hub, tên `ev-care-<tên-có-gạch-ngang>` (đổi bằng `--prefix`).

```
cd backend
uv run python scripts/prompt_sync.py status                 # version, trạng thái lock và Hub
uv run python scripts/prompt_sync.py push                   # đẩy các prompt chưa đồng bộ, tag v<version>
uv run python scripts/prompt_sync.py push rag_generator     # đẩy một prompt
uv run python scripts/prompt_sync.py pull                   # lấy commit mới nhất của Hub vào file
uv run python scripts/prompt_sync.py pull ev_care_base --commit <hash>   # lấy đúng một commit
```

- `push` từ chối nếu có file đã sửa mà chưa chạy `lock`.
- `pull` từ chối ghi đè khi file có thay đổi chưa push; muốn ghi đè thì thêm `--force`.
- `pull` chỉ ghi file, không tự commit. Xem diff, rồi commit `texts/` và `versions.lock.json`.
- Dùng khi sửa prompt trên Playground của LangSmith: `pull` về, review, `lock`, commit.

## 3. Runtime và trace

- Agent đọc prompt từ file trong image; **không gọi Hub khi chạy**, nên Hub lỗi không ảnh hưởng chat.
  Đổi prompt trên production = đưa file mới qua git và deploy.
- Mỗi lượt chat, trace `agent.turn` có metadata `prompt_version`, ví dụ `ev_care_base@v3`.
  Lọc trên LangSmith theo metadata này để biết lượt nào dùng bản nào.
- Hub không tự quyết định prompt nào đang chạy; nguồn thật là git.
