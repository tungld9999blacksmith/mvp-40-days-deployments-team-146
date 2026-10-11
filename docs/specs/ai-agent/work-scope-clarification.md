# AI-Agent — Làm rõ phạm vi công việc & Kế hoạch triển khai

> Tài liệu **làm rõ (clarification)**, viết trước khi code. Mục tiêu: bóc tách yêu cầu bạn giao thành các hạng mục rời rạc, đối chiếu với **hiện trạng repo**, nêu phạm vi đề xuất, và liệt kê **câu hỏi cần bạn chốt** trước khi tôi bắt tay làm.
>
> **Nguyên tắc:** tôi chưa viết code/eval/guardrail nào. Sau khi bạn duyệt tài liệu này (hoặc trả lời các câu hỏi §9), tôi mới triển khai theo thứ tự ở §10.

| Field | Value |
| --- | --- |
| Loại | Clarification / Work-scope |
| Version | v0.2 — đã chốt scope (xem §9) |
| Ngày | 2026-10-05 |
| Trạng thái | ✅ Đã duyệt: làm toàn bộ D1–D9 theo thứ tự §10 |
| Tác giả | AI Team (drafted via Claude Code) |
| Liên quan | [00-ai-agents-proposal.md](00-ai-agents-proposal.md), [ai-001…ai-008 specs](.), [backend/src/agents/README.md](../../../backend/src/agents/README.md), [metrics.py](../../../backend/tests/test_agents/test_rag/evaluation/metrics.py) |

---

## 0. Bóc tách yêu cầu của bạn

Tôi hiểu bạn giao **9 hạng mục (D1–D9)**. Nếu tôi hiểu sai bất kỳ mục nào, hãy sửa trước khi tôi làm.

| ID | Hạng mục bạn yêu cầu | Loại đầu ra |
| --- | --- | --- |
| **D1** | Hoàn thiện các AI-agent theo tài liệu đặc tả AI-Agent, **cắm vào API chat** | Code |
| **D2** | Viết **unit-test / integration test** cho agent | Code (test) |
| **D3** | Thêm **guardrail** | Code |
| **D4** | Viết **AI-evaluation-benchmarking** (bộ chạy eval + benchmark) | Code |
| **D5** | Tạo **bộ golden dataset** | Data |
| **D6** | **Tài liệu hướng dẫn dev** về AI-agent: cấu trúc code + cách tương tác với client qua platform chat | Doc |
| **D7** | **Đặc tả chi phí vận hành** AI-agent (operational cost spec) | Doc |
| **D8** | **Đặc tả chiến lược kiểm thử** AI-agent: toàn bộ taxonomy metric + chiến lược test case + A/B + trajectory + bias/fairness + red-team + error analysis (chi tiết ở §4) | Doc |
| **D9** | **Đề xuất bổ sung** metric/framework phù hợp hệ thống | Doc (trong D8) |

**Quan hệ:** D8 là *tài liệu thiết kế* (design), D4 là *bản hiện thực* (implementation) của D8, D5 là *dữ liệu* mà D4 chạy trên đó. Nên làm **D8 → D5 → D4** theo thứ tự đó.

---

## 1. Hiện trạng repo (đã có gì rồi)

Trước khi làm mới, đây là những gì **đã tồn tại** — tránh làm trùng.

| Thành phần | Trạng thái | Vị trí |
| --- | --- | --- |
| Agent core (Orchestrator + LangGraph ReAct loop) | ✅ Đã có | `backend/src/agents/{orchestrator,graph,state,prompts}.py` |
| 6 business tools (due, cost, RAG, find_workshops, slots, propose_booking) | ✅ Đã có | `backend/src/agents/tools/*.py` |
| RAG pipeline (hybrid dense+BM25, reranker, rewriter, citation) | ✅ Đã có | `backend/src/agents/tools/RAG/` |
| **Agent đã cắm vào chat API** (ChatService → AgentOrchestrator → SSE) | ✅ Đã có (README mục 6) | `backend/src/modules/conversation/` |
| Tool guardrail (timeout + che exception, không lộ DB/Redis) | ✅ Có 1 phần | `backend/src/agents/tools/guard.py` |
| Agent-level tests (graph, orchestrator, tools, integration, stream) | ✅ Có cơ bản | `backend/tests/test_agents/*.py` |
| **RAG eval** (hit@k, MRR, ctx precision/recall, answer relevancy, citation) | ✅ Có (RAG-only) | `backend/tests/test_agents/test_rag/evaluation/` |
| Golden set RAG (100 dòng JSONL) | ✅ Có | `…/evaluation/golden_set.jsonl` |
| Error analysis RAG | ✅ Có (sơ khởi) | `…/evaluation/error_analysis.md` |
| 8 spec `.agent.md` (AI-001…AI-008) | ✅ Có | `docs/specs/ai-agent/` |

**Khoảng trống (gap) chính — cần làm mới:**

- ❌ Eval **cấp agent** (không chỉ RAG): tool-calling accuracy, trajectory, task completion end-to-end.
- ❌ Faithfulness bằng **LLM-as-Judge**; BLEU/ROUGE/BERTScore/F1/Exact-Match "đúng chuẩn" (hiện chỉ có token-F1 thủ công).
- ❌ Guardrail **input/output cấp hội thoại** (PII, jailbreak, off-scope, no-source-no-claim như một guard thực thi).
- ❌ **Confidence interval**, **A/B testing**, **bias & fairness**, **red-team** — chưa có.
- ❌ 3 tài liệu: **dev guide** (D6), **cost spec** (D7), **testing-strategy spec** (D8).

---

## 2. Làm rõ từng hạng mục code (D1–D4)

### D1 — Hoàn thiện agent & cắm vào chat API
**Hiểu của tôi:** phần "cắm vào chat API" **về cơ bản đã xong** (ChatService gọi `run_agent_turn`, stream SSE, lưu `chat_message`). Vậy "hoàn thiện" ở đây tôi hiểu là: (a) rà soát các agent so với 8 spec `.agent.md`, liệt kê phần còn thiếu/lệch so với spec, (b) vá các lệch đó. 
→ **Cần bạn chốt (Q1):** có agent/tính năng cụ thể nào bạn thấy còn thiếu, hay để tôi tự rà theo spec rồi báo cáo "spec ↔ code gap" trước khi sửa?

### D2 — Unit/integration test
Mở rộng từ bộ test hiện có. Bổ sung: test tool-calling (đúng tool, đúng tham số), test guardrail (D3), test luồng chat end-to-end có mock LLM. Dùng `pytest` theo convention `backend/tests/`.

### D3 — Guardrail
Tôi đề xuất **3 lớp** (chi tiết §5): input guard, output guard, tool/action guard. Lớp tool đã có một phần.

### D4 — AI-evaluation-benchmarking
Bản hiện thực của D8: một CLI/harness chạy trên golden dataset (D5), xuất báo cáo JSON + Markdown, có ngưỡng pass/fail để gắn CI. Kế thừa `run_eval.py` hiện có, mở rộng sang cấp agent.

---

## 3. (D5) Golden dataset — kế hoạch

Hiện có 1 golden set RAG (100 dòng). Tôi đề xuất bổ sung **nhiều bộ con**, mỗi bộ cho một loại eval:

| Bộ | Mục đích | Trường dữ liệu chính | Số lượng đề xuất |
| --- | --- | --- | --- |
| `rag_golden.jsonl` (đã có) | Retrieval + answer | query, expected_answer, relevant_doc_ids, keywords | giữ 100, mở rộng 120+ |
| `tool_calling_golden.jsonl` | Đúng tool + tham số | query, expected_tool, expected_args, context xe | 40–60 |
| `trajectory_golden.jsonl` | Chuỗi hành động ReAct | query, expected_tool_sequence, max_steps | 25–40 |
| `task_completion_golden.jsonl` | Hoàn thành tác vụ E2E | multi-turn script, success_criteria | 20–30 |
| `refusal_trap_golden.jsonl` | No-source-no-claim, off-scope | query bẫy, expected=refuse | 20–30 |
| `safety_redteam.jsonl` | Jailbreak/PII/prompt-injection | adversarial prompt, must_not_contain | 30–50 |
| `bias_fairness.jsonl` | Công bằng theo nhóm | cặp prompt biến thể (giới tính/vùng/dòng xe) | 20–40 |

→ **Cần bạn chốt (Q2):** nguồn tạo golden — tôi tự sinh từ tài liệu VinFast đã ingest + tri thức nghiệp vụ trong spec, rồi bạn/team review; hay bạn có sẵn dữ liệu thật muốn dùng?

---

## 4. (D8) Đặc tả chiến lược kiểm thử — taxonomy metric

Đây là phần nặng nhất bạn yêu cầu. Dưới đây là **bản đồ metric** tôi sẽ đưa vào tài liệu D8; mỗi metric ghi rõ *đo gì / cách tính / đã có chưa*. Bạn xem có cần thêm/bớt.

### 4.1 RAG — theo 4 trụ (retriever / context / generator / answer)
| Trụ | Metric | Cách tính | Hiện trạng |
| --- | --- | --- | --- |
| Retriever | **Context Recall** | % relevant docs lọt vào top-k | ✅ có |
| Context | **Context Precision** | % docs retrieve thực sự liên quan (có cân nhắc thứ hạng) | ✅ có (bản không trọng số thứ hạng) |
| Generator | **Faithfulness** | câu trả lời có bám context không (claim-level, **LLM-as-Judge**) | ❌ cần làm |
| Answer | **Answer Relevancy** | câu trả lời có đúng trọng tâm câu hỏi | ✅ có (bản token-overlap; nâng lên embedding/LLM) |
| | Hit@k, MRR, nDCG | xếp hạng truy hồi | ✅ hit@k,MRR; ❌ nDCG |

### 4.2 Answer quality (chất lượng câu chữ)
| Metric | Dùng khi | Hiện trạng |
| --- | --- | --- |
| **Exact Match (EM)** | câu trả lời có đáp án duy nhất (số, mã) | ❌ |
| **F1 token-overlap** | overlap token answer vs gold | ⚠️ có bản thủ công, sẽ chuẩn hóa |
| **BLEU** | n-gram precision (tham khảo, yếu với tiếng Việt) | ❌ |
| **ROUGE-L** | longest common subsequence | ❌ |
| **BERTScore** | tương đồng ngữ nghĩa bằng embedding (phù hợp tiếng Việt hơn BLEU) | ❌ |
| **Semantic accuracy** | cosine similarity embedding answer vs gold | ❌ |
| **LLM-as-Judge** | chấm toàn diện (đúng/đủ/an toàn/giọng điệu) | ❌ |

**LLM-as-Judge — tôi đề xuất (chi tiết sẽ nằm trong D8):**
- **Model judge:** Claude (Opus/Sonnet 5.x) làm judge *độc lập* với model chạy agent (hiện agent dùng Gemini theo code), để tránh self-preference bias. → **Cần bạn chốt (Q3)**.
- **Chiến lược chọn:** judge khác họ model với generator; chạy **pairwise** khi so A/B, **reference-guided scoring** (1–5) khi có gold; dùng **rubric cố định** + **few-shot** + yêu cầu **chain-of-thought rồi mới chấm điểm**; lấy trung bình nhiều lần (self-consistency) cho câu nhạy cảm.
- **Cấu trúc prompt judge:** `system` (vai trò + rubric + thang điểm) → `question` → `retrieved_context` → `reference_answer` → `candidate_answer` → yêu cầu xuất JSON `{reasoning, score, verdict}`. Có guard chống prompt-injection trong câu trả lời bị chấm.

### 4.3 Agent-specific
| Metric | Đo gì | Hiện trạng |
| --- | --- | --- |
| **Tool-calling accuracy** | chọn đúng tool + đúng tham số (exact/partial/arg-F1) | ❌ |
| **Trajectory eval** | chuỗi hành động hợp lý, không thừa bước, hiệu quả ReAct/CoT | ❌ |
| **Task completion rate** | hoàn thành mục tiêu người dùng (E2E, multi-turn) | ❌ |
| **Tool error recovery** | xử lý khi tool lỗi/timeout | ⚠️ một phần (guard.py) |

**Trajectory:** đo (a) *exact-match* chuỗi tool so với gold, (b) *in-order recall* (các bước bắt buộc có xuất hiện đúng thứ tự), (c) *số bước thừa* (efficiency), (d) *hiệu quả ReAct* = tỉ lệ bước có "reasoning dẫn tới action đúng". Có thể dùng LLM-as-Judge chấm tính hợp lý của trajectory.

### 4.4 Thống kê & độ tin cậy
| Hạng mục | Nội dung |
| --- | --- |
| **Accuracy / Pass rate** | đã có; bổ sung theo category |
| **Confidence interval** | CI 95% cho mọi tỉ lệ: **Wilson score interval** cho proportion; **bootstrap** cho metric trung bình (BERTScore, latency). Báo cáo điểm ± CI, không chỉ điểm. |
| **A/B testing** | so 2 cấu hình (ví dụ: reranker A vs B, prompt v1 vs v2, top-k=3 vs 5). **Giả thuyết H0:** không khác biệt; metric chính (primary): task-completion / faithfulness; kiểm định **two-proportion z-test** (hoặc bootstrap) + **hiệu chỉnh đa kiểm định** nếu nhiều metric; báo cáo effect size + CI, không chỉ p-value. → **Cần bạn chốt (Q4):** tham số/giả thuyết nào ưu tiên A/B đầu tiên? |

### 4.5 Thuật toán liên quan (giải thích trong D8)
- **Dual-encoder (bi-encoder):** encode query & doc riêng → cosine. Nhanh, dùng cho *retrieval* (chính là dense hiện tại, `bge-m3`/Gemini embedding).
- **Cross-encoder:** encode cặp (query, doc) chung → điểm liên quan. Chậm nhưng chính xác, dùng cho *reranking* (đã có `RerankerService`). D8 sẽ giải thích vì sao dual cho recall, cross cho precision.

### 4.6 An toàn & công bằng
| Hạng mục | Nội dung |
| --- | --- |
| **Bias & fairness** | so chất lượng/giọng điệu giữa các nhóm (dòng xe phổ thông vs cao cấp, cách xưng hô, vùng miền); đo chênh lệch pass-rate giữa nhóm (demographic parity-style). |
| **Red-team** | jailbreak, prompt-injection qua nội dung tài liệu, rò rỉ PII (VIN/CCCD/SĐT), dụ agent tạo booking/khẳng định sai; metric = attack success rate (càng thấp càng tốt). |
| **Error analysis** | phân loại lỗi (retrieval miss / wrong tool / hallucination / refusal sai / format), bảng tần suất + ví dụ, liên kết về nguyên nhân & hành động sửa. Mở rộng `error_analysis.md` hiện có. |

### 4.7 Business metrics
Containment rate (tự giải quyết không cần người), booking conversion từ chat, tỉ lệ từ chối đúng (safe-refusal), CSAT proxy, cost/conversation (nối sang D7), p95 latency, tỉ lệ câu có citation hợp lệ.

---

## 5. (D3) Kế hoạch guardrail

| Lớp | Kiểm soát | Ghi chú |
| --- | --- | --- |
| **Input guard** | lọc prompt-injection, off-scope, chuẩn hóa, (tuỳ chọn) phát hiện PII người dùng dán nhầm | mới |
| **Output guard** | no-source-no-claim (chặn khẳng định kỹ thuật không có citation), che PII (VIN/CCCD/SĐT/biển số), chặn số liệu chi phí bịa, giọng điệu | mới — cốt lõi MVP |
| **Tool/action guard** | timeout, che exception, confirm-before-side-effect (booking), danh tính từ session không từ LLM | ✅ một phần (guard.py + propose_booking) |

→ **Cần bạn chốt (Q5):** guardrail tự viết (rule + regex + LLM-check nhẹ) hay tích hợp thư viện (ví dụ NeMo Guardrails / Guardrails-AI)? Tôi nghiêng về **tự viết gọn cho MVP** + hook sẵn để sau thay thư viện.

---

## 6. (D6) Dev guide & (D7) Cost spec — nội dung dự kiến

**D6 Dev guide** (`backend/guide/` hoặc `docs/guide/`): kiến trúc agent, cấu trúc thư mục, cách thêm 1 tool mới, vòng đời 1 lượt chat (client → SSE → orchestrator → tool → respond), cách test local, cách đọc trace. Phần lớn chắt lọc từ `README.md` hiện có + bổ sung "how-to".

**D7 Cost spec** (`docs/specs/ai-agent/` hoặc `docs/guide/cost-*`): bóc tách chi phí/lượt hội thoại = token in/out × giá model (LLM generator + rewriter + reranker + embedding + LLM-judge khi eval) + hạ tầng (Qdrant, Redis, DB). Ước tính theo kịch bản tải, đòn bẩy giảm chi phí (caching, chọn tier model, giảm số vòng ReAct), ngân sách eval. → **Cần bạn chốt (Q6):** model & đơn giá thực tế đang dùng (Gemini tier nào? có dùng Claude cho judge?) để tôi tính đúng.

---

## 7. (D9) Đề xuất framework bổ sung

Tôi đề xuất cân nhắc (không bắt buộc tất cả):
- **RAGAS** — chuẩn hóa faithfulness/context-precision/recall/answer-relevancy (khớp đúng 4 trụ bạn nêu).
- **DeepEval** — assert metric trong pytest, hợp để gắn CI (D2+D4).
- **promptfoo** — chạy ma trận prompt/model + red-team + so A/B bằng YAML.
- **Langfuse / trace** — quan sát & lưu trajectory thật để làm golden từ traffic.
- **BERTScore / sacreBLEU / rouge-score** — thư viện tính answer-quality chuẩn.

→ **Cần bạn chốt (Q7):** ưu tiên **tự viết metric gọn** (ít phụ thuộc, dễ kiểm soát) hay **dùng RAGAS/DeepEval** (nhanh, chuẩn, thêm dependency)? Tôi đề xuất lai: tự viết lõi + RAGAS/DeepEval cho các metric phức tạp.

---

## 8. Giả định của tôi (nếu không nghe gì ngược lại, tôi sẽ theo)

1. Tài liệu viết **tiếng Việt**; code/comment/identifier **tiếng Anh** (theo memory dự án).
2. Eval chạy **offline/CI**, không gọi API tốn phí trong unit-test mặc định (LLM-call tách sau cờ `--full`).
3. Golden dataset tôi tự dựng từ tài liệu đã ingest + spec, rồi team review.
4. Không đổi kiến trúc agent (giữ single-orchestrator); chỉ bổ sung eval/guardrail/doc.
5. Judge model mặc định Claude; generator giữ nguyên hiện tại.

---

## 9. Câu hỏi cần bạn chốt (blocking) — ĐÃ CHỐT

| # | Câu hỏi | ✅ Quyết định |
| --- | --- | --- |
| Q1 | "Hoàn thiện agent" = rà gap theo spec rồi vá? | **Tự rà spec↔code và vá luôn** (báo cáo sau) |
| Q2 | Nguồn golden dataset? | Tự sinh từ tài liệu + spec, team review |
| Q3 | Model LLM-as-Judge? | Claude Sonnet/Opus 5.x (khác họ generator) |
| Q4 | Giả thuyết/tham số A/B ưu tiên? | reranker on/off hoặc top-k=3 vs 5, primary = faithfulness |
| Q5 | Guardrail tự viết hay thư viện? | Tự viết gọn cho MVP, hook để thay sau |
| Q6 | Model & đơn giá thực tế để tính cost? | **Dùng giả định có đánh dấu**, bạn chỉnh số sau |
| Q7 | Tự viết metric hay RAGAS/DeepEval? | **Lai: lõi tự viết + RAGAS/DeepEval cho phần khó** |
| Q8 | Phạm vi lần này? | **Làm toàn bộ D1–D9 liền mạch** theo thứ tự §10 |

## 10. Thứ tự thực thi đề xuất (sau khi bạn duyệt)

1. **D8** (testing-strategy spec) — xương sống, chốt metric & ngưỡng.
2. **D7** (cost spec) + **D6** (dev guide) — tài liệu, không chặn code.
3. **D5** (golden datasets) — theo taxonomy ở D8.
4. **D4** (eval harness) + **D3** (guardrail) — hiện thực.
5. **D2** (tests) bao phủ D3/D4.
6. **D1** (vá gap agent theo báo cáo spec↔code).

---

> **Bạn hãy trả lời §9 (ít nhất Q1, Q2, Q8) để tôi bắt đầu.** Nếu bạn chỉ nói "ok làm đi", tôi sẽ theo toàn bộ "Đề xuất của tôi" ở §8–§9 và thứ tự §10.

---

## 11. Tình trạng triển khai (cập nhật 2026-10-05)

Đã triển khai theo thứ tự §10:

| D | Hạng mục | Kết quả |
| --- | --- | --- |
| D8 | Testing-strategy spec | ✅ [ai-eval-testing-strategy.spec.md](ai-eval-testing-strategy.spec.md) |
| D7 | Cost spec | ✅ [ai-operational-cost.spec.md](ai-operational-cost.spec.md) (số liệu giả định 🔸) |
| D6 | Dev guide | ✅ [backend/guide/ai-agent-dev-guide.md](../../../backend/guide/ai-agent-dev-guide.md) (đã link DEV_GUIDE) |
| D5 | Golden datasets | ✅ `eval/datasets/` (6 bộ seed) |
| D4 | Eval harness | ✅ `eval/metrics/` + `eval/run.py` (CI Wilson/bootstrap, A/B z-test, tool-calling, trajectory) |
| D3 | Guardrails | ✅ `backend/src/agents/conversation_guards/` — cắm vào `orchestrator.py` (completed event) |
| D2 | Tests | ✅ 32 ca pass (`test_eval/test_metrics.py`, `test_agents/test_guardrails.py`) |
| D1 | Gap audit & vá | ✅ [ai-agent-gap-audit.md](ai-agent-gap-audit.md) |

**Còn lại (cần khoá API / quyết định của bạn):** script sinh predictions từ agent thật, LLM-as-Judge (Claude) cho faithfulness, số liệu cost thật (Q6), cập nhật header AI-005/006/007.
