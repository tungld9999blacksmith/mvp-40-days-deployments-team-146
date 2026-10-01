# Deprecated code

Code moved here is no longer imported by the running app. It is kept for
reference instead of being deleted outright. Do not import from this
package in `src/`.

## Contents

| Path | Reason |
|---|---|
| `models/schemas.py` | `ChatRequest`/`ChatResponse` Pydantic schemas for the old `/api/v1/chat` endpoint. Superseded by module-scoped schemas (see `src/modules/*/model.py`). Pre-existing entry, undocumented until now. |
| `services/llm.py` | `ChatOpenAI` client factory, not wired into any active module. Pre-existing entry, undocumented until now. |
| `modules/routes.py` | Moved 2026-09-26. Imported `backend.src.agents.graph` and `backend.src.models.schemas`, neither of which exists (`backend/src/models/` was never created). Never mounted in `main.py`, so it was dead on arrival. |
| `tests/test_api/test_routes.py` | Moved 2026-09-26. Tested the `/api/v1/chat` and `/api/v1/status` endpoints defined in `modules/routes.py` above; moved alongside it. |
| `tests/test_agents/test_graph.py` | Moved 2026-09-26. Imported `from api.src.agents.graph import agent` — the `api` package does not exist in this repo, and `src/agents/graph.py` itself has the same broken-import bug (`from api.src.agents...`). The `agents/` LangGraph scaffold is unwired example code, out of scope for the current auth/vehicle work; revisit when that module is picked up. |

## 2026-09-26 cleanup

Also fixed while wiring `src/main.py` (not deprecated, just noted here for traceability):
- `tests/conftest.py`: `client` fixture imported `from api.src.main import app` (nonexistent package) — corrected to `from src.main import app`, matching how the app is actually run (`uvicorn src.main:app` from `backend/`).
- `src/main.py` and `src/modules/oauth/route.py` imported via `backend.src.*`, which only resolves if the process is launched from the repo root — inconsistent with the Makefile/Dockerfile convention (`src.main:app`, launched from `backend/`). Switched both to relative imports (`.config`, `.dependency`).
- `dockerfiles/Dockerfile` copied `backend/src/.` flat into `/app` while still running `uvicorn src.main:app`, which cannot resolve a `src` package. Changed the `COPY` to preserve the `src/` layout so the image matches local dev.
