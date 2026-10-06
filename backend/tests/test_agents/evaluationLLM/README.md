# EV Care Agent — OpenRouter LLM Benchmark

Benchmark này so sánh 10 model trong vai trò **AI Agent**, dùng system prompt và
schema của 6 tool production hiện tại. Nó không chỉ gửi câu hỏi chat đơn lẻ.

## Kiến trúc được benchmark

Agent production dùng LangGraph theo vòng `agent → tools → agent`. Orchestrator
nạp vehicle context từ backend, bind các tool và chặn `create_booking_draft` bằng
Human-in-the-loop. Sáu tool thực tế được benchmark:

1. `get_due_maintenance`
2. `estimate_service_cost`
3. `find_workshops`
4. `get_available_slots`
5. `create_booking_draft`
6. `search_ev_knowledge`

Runner import trực tiếp `format_system_prompt` và `CUSTOMER_AGENT_TOOLS`; thay đổi
schema/prompt production vì vậy sẽ được phản ánh trong lần chạy tiếp theo. Tool
output được fixture cố định theo từng case để mọi model nhận cùng dữ liệu và để
benchmark không tạo booking, không phụ thuộc DB/Qdrant, và không chịu sai lệch do
dịch vụ ngoài. Đây là benchmark khả năng orchestration của LLM, không thay cho
integration test của tool backend hay retrieval benchmark của Qdrant.

Runner cũng mô phỏng đúng bước pre-fill trong `graph.py`: trusted vehicle context
chỉ bổ sung `model`, ODO và số tháng còn thiếu/null cho `get_due_maintenance`.
Raw `arguments` và `effective_arguments` sau pre-fill đều được lưu để audit; ID,
item code, giá và argument sai kiểu không được tự sửa.

## Dataset

`agent_cases.json` có đúng 30 case:

| Nhóm | Số case |
|---|---:|
| Maintenance | 6 |
| Cost estimation | 5 |
| RAG | 5 |
| Workshop/booking | 4 |
| Multi-step | 4 |
| Guardrail/adversarial | 3 |
| Error/edge | 3 |

Các phép chấm deterministic kiểm tra tên tool, thứ tự, arguments, provenance của
`item_codes`/`workshop_id`/slot, forbidden tool, confirmation trước write action,
xử lý tool error, fact có trong RAG fixture và dấu hiệu trích nguồn. Answer Quality
dùng heuristic công khai (độ dài, tiếng Việt, ý bắt buộc, fact bắt buộc và lặp
câu). Benchmark không dùng một LLM khác để tự quyết định model thắng.

## Model và cấu hình

Toàn bộ model nằm ở `models.yaml` và cấu hình hiện tại chỉ dùng endpoint trả phí.
Không dùng `openrouter/free` hay model có hậu tố `:free`. Mọi model dùng cùng
temperature và max token mặc định, trừ khi có override được ghi rõ trong chính
file cấu hình. API key chỉ đọc từ `OPENROUTER_API_KEY` trong environment hoặc
`.env` ở root.

## Cách chạy

Benchmark nằm tại `backend/tests/test_agents/evaluationLLM/`. Chạy từ repository root
bằng virtual environment của dự án:

```bash
.venv/bin/python backend/tests/test_agents/evaluationLLM/benchmark_models.py --all
```

Tiếp tục các partial result mà không chạy lại case đã hoàn thành:

```bash
.venv/bin/python backend/tests/test_agents/evaluationLLM/benchmark_models.py --all --resume
```

Chấm lại raw result sau khi điều chỉnh deterministic heuristic, không gọi API:

```bash
.venv/bin/python backend/tests/test_agents/evaluationLLM/benchmark_models.py --rescore
```

Chạy một model hoặc smoke test một số case:

```bash
.venv/bin/python backend/tests/test_agents/evaluationLLM/benchmark_models.py \
  --model anthropic/claude-haiku-4.5

.venv/bin/python backend/tests/test_agents/evaluationLLM/benchmark_models.py \
  --model qwen/qwen3.8-27b:free \
  --limit 5

.venv/bin/python backend/tests/test_agents/evaluationLLM/benchmark_models.py \
  --model openai/gpt-4o \
  --case RAG-01 --case GUARD-03
```

Kiểm tra config/dataset mà không gọi API:

```bash
.venv/bin/python backend/tests/test_agents/evaluationLLM/benchmark_models.py --all --list
```

Rate limit được retry có giới hạn với backoff. Runner ghi JSON sau từng case nên
giữ được partial result khi gặp `RATE_LIMITED`, `CREDIT_EXHAUSTED`, lỗi mạng hoặc
provider. Model từ chối tool calling được ghi `UNSUPPORTED_FOR_AGENT`.
Model có provider quota thấp có thể đặt `inter_case_delay_seconds` trong
`models.yaml`; thời gian pacing này nằm ngoài latency của case.

## Output và cách tính điểm

`results/<model>.json` chứa raw tool calls, arguments, tool fixture response,
answer, latency từng request, token usage, cost do OpenRouter trả và metrics từng
case. `results/comparison.csv` và `comparison.json` được cập nhật sau mỗi model.

Final score:

| Thành phần | Trọng số |
|---|---:|
| Tool Calling (`70% tool selection + 30% arguments`) | 25% |
| Multi-step | 20% |
| RAG Faithfulness | 20% |
| Guardrail | 15% |
| Answer Quality | 10% |
| Latency | 5% |
| Cost | 5% |

Latency score giảm tuyến tính từ 100 ở tối đa 3 giây/case xuống 0 ở 30 giây/case.
Cost score là 100 ở tối đa `$0.001/case`, giảm tuyến tính xuống 0 ở
`$0.02/case`. Cost chỉ được tính khi OpenRouter trả metadata; model `:free` chỉ
được ghi `$0` khi endpoint thực tế là free và provider trả cost bằng 0.

Một model có `eligible_for_agent=true` theo ngưỡng nghiệm thu MVP khi chạy đủ tập
case đã chọn, Tool Calling Accuracy đạt ít nhất 77%, Argument Accuracy đạt ít nhất
80%, RAG Faithfulness đạt ít nhất 80%, Guardrail đạt ít nhất 90% và không có
critical violation. Final score cao không tự động đủ điều kiện. Đây là ngưỡng MVP;
ngưỡng production khuyến nghị vẫn nên yêu cầu Tool Calling Accuracy ít nhất 85%.

## Giới hạn

- Fixture tool làm kết quả tái lập được nhưng không đo độ ổn định DB, Qdrant hay
  API booking thật.
- RAG Faithfulness dùng fact/citation checks theo từng fixture; nó không đo recall
  của retriever và chưa có semantic judge tùy chọn.
- Answer Quality là heuristic, không thay thế review tiếng Việt của con người.
- Latency chịu ảnh hưởng mạng, provider routing và tải OpenRouter tại thời điểm
  chạy. Nên chạy lặp nhiều lần trước quyết định production.
- Kết quả partial, rate-limited hoặc credit-exhausted không được dùng để tuyên bố
  model tốt nhất.
