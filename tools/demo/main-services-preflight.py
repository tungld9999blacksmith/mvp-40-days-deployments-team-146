"""Read-only service checks. Prints status only, never keys/hosts/recipients.

Run from repository root with .venv/Scripts/python.exe -X utf8.
Does not migrate, ingest, send mail or start workers.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

import httpx
from sqlalchemy import create_engine, text
from src.config import get_settings


def run():
    cfg = get_settings()
    report = {}
    from dotenv import dotenv_values

    env = dotenv_values(ROOT / ".env")
    filename = env.get("FIREBASE_CREDENTIAL") or ""
    report["firebase"] = {
        "credential_file_found": bool(
            filename and (ROOT / "backend/src/assets/secrets" / filename).is_file()
        ),
        "inline_credential_set": bool(env.get("FIREBASE_CREDENTIAL_JSON")),
    }
    try:
        from firebase_admin import credentials

        path = ROOT / "backend/src/assets/secrets" / filename
        contents = (
            json.loads(path.read_text(encoding="utf-8"))
            if filename and path.is_file()
            else json.loads(env.get("FIREBASE_CREDENTIAL_JSON") or "")
        )
        credentials.Certificate(contents)
        report["firebase"].update(
            {
                "credential_valid": True,
                "frontend_project_matches": contents.get("project_id")
                == env.get("VITE_FIREBASE_PROJECT_ID"),
            }
        )
    except Exception as exc:  # noqa: BLE001 -- status only, never secret error text
        report["firebase"].update(
            {"credential_valid": False, "error_type": type(exc).__name__}
        )
    engine = create_engine(
        cfg.sqlalchemy_database_url,
        connect_args={"connect_timeout": 8}
        if cfg.sqlalchemy_database_url.startswith("postgres")
        else {},
    )
    try:
        with engine.connect() as db:
            db.execute(text("SELECT 1"))
            revision = db.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar()
            report["database"] = {"connected": True, "revision": revision}
    except Exception as exc:  # noqa: BLE001 -- status only, never secret error text
        report["database"] = {"connected": False, "error_type": type(exc).__name__}
    finally:
        engine.dispose()
    try:
        import redis

        client = redis.Redis.from_url(
            cfg.redis_connection_url, socket_connect_timeout=5, socket_timeout=5
        )
        report["redis"] = {"connected": bool(client.ping())}
        client.close()
    except Exception as exc:  # noqa: BLE001 -- status only, never secret error text
        report["redis"] = {"connected": False, "error_type": type(exc).__name__}
    with httpx.Client(timeout=15) as client:
        try:
            from urllib.parse import quote

            response = client.get(
                cfg.qdrant_url.rstrip("/")
                + "/collections/"
                + quote(cfg.qdrant_collection_name, safe=""),
                headers={"api-key": cfg.qdrant_api_key},
            )
            info = response.json().get("result", {}) if response.is_success else {}
            vectors = info.get("config", {}).get("params", {}).get("vectors", {})
            dimensions = vectors.get("size")
            report["qdrant"] = {
                "status": response.status_code,
                "vector_dimensions": dimensions,
                "points_count": info.get("points_count"),
                "matches_embedding_dimensions": dimensions == cfg.embedding_dimensions,
            }
        except Exception as exc:  # noqa: BLE001 -- status only, never secret error text
            report["qdrant"] = {"error_type": type(exc).__name__}
        try:
            response = client.get(
                cfg.openrouter_base_url.rstrip("/") + "/models",
                headers={"Authorization": "Bearer " + cfg.openrouter_api_key},
            )
            model = (
                next(
                    (
                        m
                        for m in response.json().get("data", [])
                        if m.get("id") == cfg.openrouter_model
                    ),
                    None,
                )
                if response.is_success
                else None
            )
            report["openrouter"] = {
                "status": response.status_code,
                "model": cfg.openrouter_model,
                "model_found": model is not None,
                "tools_supported": "tools"
                in (model or {}).get("supported_parameters", []),
            }
            auth = client.get(
                cfg.openrouter_base_url.rstrip("/") + "/auth/key",
                headers={"Authorization": "Bearer " + cfg.openrouter_api_key},
            )
            report["openrouter"]["key_auth_status"] = auth.status_code
        except Exception as exc:  # noqa: BLE001 -- status only, never secret error text
            report["openrouter"] = {"error_type": type(exc).__name__}
    report["embedding"] = {
        "provider": cfg.embedding_provider,
        "model": getattr(cfg, f"embedding_{cfg.embedding_provider}_model"),
        "dimensions": cfg.embedding_dimensions,
        "key_configured": bool(
            cfg.gemini_api_key
            if cfg.embedding_provider == "gemini"
            else cfg.openai_api_key
            if cfg.embedding_provider == "openai"
            else cfg.huggingface_api_key
            if cfg.embedding_provider == "huggingface"
            else True
        ),
    }
    print(json.dumps(report, ensure_ascii=True, indent=2))
    return report


if __name__ == "__main__":
    run()
