# Tài liệu kỹ thuật theo công nghệ

> Cập nhật: 2026-10-12. Bức tranh tổng thể nằm ở [../architecture.md](../architecture.md); bảo mật, phi chức năng, vòng đời trạng thái nằm ở [../architecture-deep-dive.md](../architecture-deep-dive.md). Thư mục này giải thích **từng công nghệ**: dùng để làm gì, nằm ở đâu trong code, cấu hình và vận hành ra sao.

| Công nghệ | Dùng để | Tài liệu | Code chính |
| --- | --- | --- | --- |
| OpenTelemetry + Grafana Cloud + LangSmith | Trace, metric, log, trace LLM, chi phí | [observability.md](observability.md) · [setup](../observability/OBSERVABILITY_SETUP.md) · [usage](../observability/OBSERVABILITY_USAGE.md) · [Grafana](../observability/GRAFANA_GUIDE.md) · [alert](../observability/GRAFANA_ALERTING.md) | `infrastructure/observability/`, `infrastructure/observability/otel-collector/` |
| Xác thực M2M backend ↔ OEM | OAuth2 `client_credentials` + `private_key_jwt`, webhook JWT gắn body | [oem-m2m-auth.md](oem-m2m-auth.md) · [spec](../specs/mock-system/m2m_authentication_spec.md) | `infrastructure/oem/`, `shared/ev-contracts`, `mock-ev-system/auth.py` |
| Transactional outbox | Việc phụ không mất khi worker/Redis lỗi | [backend/guide/outbox.md](../../backend/guide/outbox.md) · [architecture.md §5.10](../architecture.md) | `infrastructure/outbox/` |
| Celery + beat | Tác vụ nền, lịch định kỳ | [celery-background-jobs.md](celery-background-jobs.md) | `celery_tasks.py`, `infrastructure/celery/tasks/` |
| LLM provider, định tuyến, fallback | Chọn model theo giai đoạn, chịu lỗi tạm thời | [llm-routing-and-fallback.md](llm-routing-and-fallback.md) | `infrastructure/llm/` |
| Prompt có phiên bản | Prompt như code, đồng bộ Prompt Hub | [prompt-management.md](prompt-management.md) · [README gốc](../../backend/src/infrastructure/prompts/README.md) | `infrastructure/prompts/`, `scripts/prompt_sync.py` |
| Che PII và bí mật | Log, trace LangSmith, output agent | [pii-redaction.md](pii-redaction.md) | `infrastructure/logging/pii.py`, `conversation_guards/` |
| AI agent (LangGraph), guardrail, RAG | Trợ lý chat | [backend/guide/agent.md](../../backend/guide/agent.md) · [ai-agent-dev-guide](../../backend/guide/ai-agent-dev-guide.md) · [agents/README](../../backend/src/agents/README.md) · [RAG](../../backend/src/agents/tools/RAG/README.md) | `agents/` |
| Agent memory | Summary, sở thích xuyên hội thoại | [backend/guide/agent-memory.md](../../backend/guide/agent-memory.md) | `modules/agent_memory/` |
| Eval AI agent | Đo chất lượng, CI, A/B | [eval/README.md](../../eval/README.md) · [chiến lược](../specs/ai-agent/ai-eval-testing-strategy.spec.md) | `eval/` |
| Redis | Cache, lock, rate limit, pub/sub, GEO | [backend/guide/redis.md](../../backend/guide/redis.md) | `infrastructure/redis/` |
| Qdrant / vector store | Kho tri thức RAG | [backend/guide/qdrant.md](../../backend/guide/qdrant.md) | `infrastructure/vectorstore/`, `qdrant/` |
| PostgreSQL + Alembic | Dữ liệu chuẩn, migration | [backend/guide/alembic.md](../../backend/guide/alembic.md) · [data-access](../../backend/guide/data-access.md) | `alembic/`, `common/core/` |
| Mock hãng xe | OEM giả lập cho dev | [backend/mock-ev-system/README.md](../../backend/mock-ev-system/README.md) | `backend/mock-ev-system/` |
| Triển khai | Railway, Vercel, local | [../deployments/](../deployments/) · [RUN_LOCAL_BACKEND.md](../RUN_LOCAL_BACKEND.md) | `docker-compose.*`, `infrastructure/` |

## Quy ước

- Thêm công nghệ mới: viết một trang trong thư mục này (mục đích, code, cấu hình, vận hành, sự cố), thêm dòng vào bảng trên và vào [DEV_GUIDE.md](../../DEV_GUIDE.md).
- Mô tả trạng thái thật: chỗ nào chưa nối hoặc chưa bật thì ghi rõ (ví dụ outbox chưa có handler nghiệp vụ, `OTEL_ENABLED` chưa bật trên Railway).
