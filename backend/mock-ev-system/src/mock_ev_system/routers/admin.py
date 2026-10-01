"""API endpoints: data admin — bulk import, generic query, reset (dev tooling).

Used by ``tools/ev_mock_data``. When ``MOCK_ADMIN_TOKEN`` is set, every call must
send it in the ``X-Admin-Token`` header (set it on any shared deployment).
"""

import os
from typing import Any, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field
from sqlmodel import Session

from ..db import engine, get_session, init_db
from ..service import ENTITIES, DataAdminService, DataImportError


def require_admin_token(x_admin_token: str | None = Header(default=None)) -> None:
    expected = os.getenv("MOCK_ADMIN_TOKEN", "")
    if expected and x_admin_token != expected:
        raise HTTPException(401, "Invalid or missing X-Admin-Token")


router = APIRouter(
    prefix="/admin", tags=["Admin (data)"], dependencies=[Depends(require_admin_token)]
)


class ImportRequest(BaseModel):
    mode: Literal["insert", "upsert"] = "upsert"
    data: dict[str, list[dict[str, Any]]] = Field(
        ..., description="Entity name → records, e.g. {'owners': [...], 'vehicles': [...]}"
    )


def _entity(entity: str) -> str:
    if entity not in ENTITIES:
        raise HTTPException(404, f"Unknown entity '{entity}'. Known: {', '.join(ENTITIES)}")
    return entity


@router.get("/entities", summary="Entities with primary key, fields and row count")
def list_entities(session: Session = Depends(get_session)):
    return DataAdminService(session).describe()


@router.get("/data/{entity}", summary="Query records; other query params are exact-match filters")
def query_entity(
    entity: str,
    request: Request,
    limit: int = Query(100, ge=1, le=10_000),
    offset: int = Query(0, ge=0),
    session: Session = Depends(get_session),
):
    filters = {k: v for k, v in request.query_params.items() if k not in ("limit", "offset")}
    try:
        total, items = DataAdminService(session).query(_entity(entity), filters, limit, offset)
    except KeyError as exc:
        raise HTTPException(400, f"Unknown field {exc} for entity '{entity}'") from exc
    return {"entity": entity, "total": total, "limit": limit, "offset": offset, "items": items}


@router.post("/import", summary="Bulk insert/upsert records of several entities (one transaction)")
def import_data(body: ImportRequest, session: Session = Depends(get_session)):
    try:
        summary = DataAdminService(session).import_data(body.data, body.mode)
    except DataImportError as exc:
        raise HTTPException(
            422, {"entity": exc.entity, "index": exc.index, "message": exc.message}
        ) from exc
    return {"mode": body.mode, "imported": summary}


@router.post("/data/{entity}", summary="Create records in one table (fails if a primary key exists)")
def create_records(
    entity: str,
    records: list[dict[str, Any]],
    upsert: bool = Query(False, description="Replace records whose primary key exists"),
    session: Session = Depends(get_session),
):
    try:
        summary = DataAdminService(session).import_data(
            {_entity(entity): records}, "upsert" if upsert else "insert"
        )
    except DataImportError as exc:
        raise HTTPException(
            422, {"entity": exc.entity, "index": exc.index, "message": exc.message}
        ) from exc
    return summary.get(entity, {"created": 0, "updated": 0})


@router.get("/dump", summary="Dump the whole database: SQLite SQL script or JSON (import format)")
def dump(format: Literal["sql", "json"] = "sql", session: Session = Depends(get_session)):
    if format == "json":
        svc = DataAdminService(session)
        return {"data": {name: svc.query(name, {}, 10**9, 0)[1] for name in ENTITIES}}
    raw = engine.raw_connection()
    try:
        script = "\n".join(raw.driver_connection.iterdump())
    finally:
        raw.close()  # StaticPool: returns the shared connection, does not close it
    return PlainTextResponse(script + "\n", media_type="application/sql")


@router.delete("/data/{entity}/{key}", summary="Delete one record by primary key")
def delete_record(entity: str, key: str, session: Session = Depends(get_session)):
    if not DataAdminService(session).delete(_entity(entity), key):
        raise HTTPException(404, f"{entity} '{key}' not found")
    return {"deleted": key}


@router.post("/reset", summary="Drop all data and reload the startup data (MOCK_SEED_DUMP or built-in seed)")
def reset_data():
    init_db(reset=True)
    return {"status": "reset"}
