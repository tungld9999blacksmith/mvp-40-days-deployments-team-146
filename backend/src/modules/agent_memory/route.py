"""Firebase-only API for viewing, toggling, editing and deleting one's memory."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field
from sqlmodel import Session, select

from src.common.core.workshop.workshop import Workshop
from src.config import get_settings
from src.infrastructure.supabase.db import get_session
from src.modules.conversation.dependency import get_current_user_id
from src.modules.conversation.errors import Unauthorized

from .preferences import PreferenceService

router = APIRouter(prefix="/agent-memory", tags=["agent-memory"])
_bearer = HTTPBearer(auto_error=False)


def memory_owner(
    cred: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    user_id: Annotated[int, Depends(get_current_user_id)],
) -> int:
    if cred is None:
        raise Unauthorized()
    return user_id


def memory_service(db: Annotated[Session, Depends(get_session)]) -> PreferenceService:
    return PreferenceService(db, get_settings())


Service = Annotated[PreferenceService, Depends(memory_service)]
Owner = Annotated[int, Depends(memory_owner)]


class Toggle(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool


class Edit(BaseModel):
    model_config = ConfigDict(extra="forbid")
    value: dict
    version: int = Field(ge=1)


def memory_dto(row, service):
    label = None
    if row.memory_key == "preferred_workshop_id":
        workshop = service.db.get(Workshop, UUID(row.value_json["workshop_id"]))
        label = workshop.name if workshop else None
    return {
        "id": str(row.id),
        "key": row.memory_key,
        "scope": row.scope_type,
        "value": row.value_json,
        "label": label,
        "version": row.version,
        "expires_at": row.expires_at.isoformat(),
    }


@router.get("")
def list_memory(service: Service, user_id: Owner, vehicle_id: UUID | None = None):
    rows = service.list(user_id, vehicle_id)
    return {
        "data": {
            "enabled": service.enabled(user_id),
            "read_enabled": service.read_enabled_for(user_id),
            "write_enabled": service.write_enabled_for(user_id),
            "items": [memory_dto(r, service) for r in rows],
        }
    }


@router.get("/workshops")
def memory_workshops(service: Service, user_id: Owner):
    service.owner(user_id)
    rows = service.db.exec(select(Workshop).where(Workshop.status == "active").order_by(Workshop.name).limit(100)).all()
    return {"data": [{"id": str(w.id), "name": w.name} for w in rows]}


@router.patch("/settings")
def toggle_memory(body: Toggle, service: Service, user_id: Owner):
    service.set_enabled(user_id, body.enabled)
    return {"data": {"enabled": body.enabled}}


@router.patch("/{memory_id}")
def edit_memory(memory_id: UUID, body: Edit, service: Service, user_id: Owner):
    row = service.edit(user_id, memory_id, body.value, body.version)
    return {"data": memory_dto(row, service)}


@router.delete("", status_code=204)
def forget_all(service: Service, user_id: Owner):
    service.forget(user_id)
    return Response(status_code=204)


@router.delete("/{memory_id}", status_code=204)
def forget_one(memory_id: UUID, service: Service, user_id: Owner):
    service.forget(user_id, memory_id)
    return Response(status_code=204)
