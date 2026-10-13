# Quản lý prompt có phiên bản

> Cập nhật: 2026-10-12. Hướng dẫn thao tác đầy đủ: [backend/src/infrastructure/prompts/README.md](../../backend/src/infrastructure/prompts/README.md).

## Mô hình

- **Nguồn gốc** của mỗi prompt là hằng số chuỗi trong file `.py` dùng nó (bảng `PROMPT_SOURCES` trong `registry.py`). Thêm prompt = thêm một dòng ở đó.
- `texts/<tên>.txt` là bản **sinh tự động** (không sửa tay) để git giữ lịch sử và để đẩy lên LangSmith Prompt Hub.
- `texts/versions.lock.json` ghi **version** và **sha256** của từng prompt.
- Lúc chạy agent dùng chuỗi trong code; **không gọi Hub, không đọc `.txt`**, nên Hub lỗi không ảnh hưởng chat. Đổi prompt trên production = đưa thay đổi qua git và deploy.
- Mỗi lượt chat, trace `agent.turn` mang metadata `prompt_version` (ví dụ `ev_care_base@v3`) để lọc trên LangSmith.

| Prompt | Hằng số (file) |
| --- | --- |
| `ev_care_base` | `EV_CARE_BASE_PROMPT` — `agents/prompts.py` |
| `customer_chat` | `_SYSTEM_PROMPT` — `modules/conversation/service.py` |
| `rag_generator` / `rag_rewriter` | `SYSTEM_PROMPT` — `agents/tools/RAG/query/generator.py` / `rewriter.py` |
| `tool_review` | `REVIEW_PROMPT` — `agents/tool_review.py` |
| `follow_up_classifier` | `SYSTEM_PROMPT` — `modules/follow_up/classifier.py` |
| `injection_note` | `INJECTION_SYSTEM_NOTE` — `conversation_guards/input_guard.py` |

## Quy trình

```
# sửa hằng số trong .py, rồi:
cd backend && uv run python scripts/prompt_sync.py lock     # sinh .txt, tăng version
uv run python scripts/prompt_sync.py status                 # version, lock, Hub
uv run python scripts/prompt_sync.py push [tên]             # đẩy lên Hub, tag v<version>
uv run python scripts/prompt_sync.py pull [tên] [--commit h] # chỉ in diff Hub so với code
```

- Test `tests/test_infrastructure/test_prompt_versions.py` đỏ nếu sửa prompt mà quên `lock`, hoặc `.txt` bị sửa tay.
- `push` từ chối khi chưa `lock`. `pull` không ghi gì vào repo (nguồn thật là code).
- `.gitattributes` giữ LF cho file prompt để sha256 ổn định giữa Windows và Linux.
- Cần `LANGCHAIN_API_KEY`, `LANGCHAIN_ENDPOINT`, `LANGCHAIN_WORKSPACE_ID`; mỗi prompt là repository `ev-care-<tên-gạch-ngang>` trên Hub.

## Liên quan

Quy tắc trong prompt chính (độ dài câu trả lời, xử lý lỗi tool) và đánh giá thay đổi prompt bằng eval: [backend/guide/ai-agent-dev-guide.md](../../backend/guide/ai-agent-dev-guide.md), [eval/README.md](../../eval/README.md).
