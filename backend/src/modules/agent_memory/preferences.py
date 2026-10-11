"""Allowlisted preferences with explicit consent, provenance and owner-scoped recall."""

import re
import unicodedata
from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, ValidationError
from sqlalchemy import delete
from sqlmodel import Session, select

from src.common.core.conversation import ChatMessage, Conversation, MessageRole
from src.common.core.conversation.memory import AgentMemorySetting, AgentMemorySource, AgentUserMemory
from src.common.core.identity.vehicle_user import UserStatus, VehicleUser
from src.common.core.vehicle import UserVehicle, VehicleLinkStatus
from src.common.core.workshop.workshop import Workshop
from src.modules.conversation.errors import ConversationError, ConversationNotFound, InvalidRequest

MemoryKey = Literal["preferred_service_window", "preferred_workshop_id", "cost_display_preference"]


class Window(BaseModel):
    model_config = ConfigDict(extra="forbid")
    day: Literal["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    period: Literal["morning", "afternoon", "evening"]


class WorkshopPreference(BaseModel):
    model_config = ConfigDict(extra="forbid")
    workshop_id: UUID


class CostPreference(BaseModel):
    model_config = ConfigDict(extra="forbid")
    format: Literal["itemized", "total"]


def normalized(value: str) -> str:
    return " ".join(
        unicodedata.normalize("NFD", value.lower().replace("đ", "d")).encode("ascii", "ignore").decode().split()
    )


def explicit_consent(content: str) -> bool:
    value = normalized(content.replace("đ", "d").replace("Đ", "D"))
    return (
        bool(
            re.match(
                r"^(?:hay ghi nho|hay nho|ghi nho|nho giup|luu so thich|remember|please remember|save my preference)\b",
                value,
            )
        )
        and not re.search(r"\b(?:dung|khong|do not|don't)\b", value)
        and "?" not in content
    )


def validate_value(key: str, value: dict) -> dict:
    models = {
        "preferred_service_window": Window,
        "preferred_workshop_id": WorkshopPreference,
        "cost_display_preference": CostPreference,
    }
    try:
        return models[key].model_validate(value).model_dump(mode="json")
    except (KeyError, ValidationError, TypeError) as exc:
        raise InvalidRequest("Preference key or value is invalid.") from exc


class PreferenceService:
    def __init__(self, db: Session, settings):
        self.db, self.settings = db, settings

    def owner(self, user_id: int, *, lock=False):
        stmt = select(VehicleUser).where(VehicleUser.user_id == user_id)
        user = self.db.exec(stmt.with_for_update() if lock else stmt).first()
        if user is None or user.status != UserStatus.ACTIVE:
            raise ConversationNotFound()
        return user

    def enabled(self, user_id: int):
        setting = self.db.get(AgentMemorySetting, user_id)
        return setting is None or setting.enabled

    def _canary_allows(self, user_id: int):
        allowed = self.settings.agent_memory_canary_user_ids
        return not allowed or user_id in allowed

    def read_enabled_for(self, user_id: int):
        return self.settings.agent_memory_read_enabled and self._canary_allows(user_id)

    def write_enabled_for(self, user_id: int):
        return self.settings.agent_memory_write_enabled and self._canary_allows(user_id)

    def _write_guard(self, user_id: int):
        self.owner(user_id, lock=True)
        if not self.write_enabled_for(user_id) or not self.enabled(user_id):
            raise ConversationError("Memory writing is disabled.", code="MEMORY_DISABLED")

    def _vehicle(self, user_id: int, vehicle_id: UUID):
        vehicle = self.db.get(UserVehicle, vehicle_id)
        if vehicle is None or vehicle.user_id != user_id or vehicle.link_status != VehicleLinkStatus.ACTIVE:
            raise ConversationNotFound()
        return vehicle

    def _validate_workshop(self, key, value):
        if key == "preferred_workshop_id":
            workshop = self.db.get(Workshop, UUID(value["workshop_id"]))
            if workshop is None or str(workshop.status) != "active":
                raise InvalidRequest("The preferred workshop is unavailable.")
            return workshop
        return None

    def remember(
        self,
        user_id: int,
        vehicle_id: UUID,
        conversation_id: UUID,
        message_id: UUID,
        key: MemoryKey,
        value: dict,
        scope: Literal["account", "vehicle"] = "account",
    ):
        self._write_guard(user_id)
        if scope not in ("account", "vehicle"):
            raise InvalidRequest("Invalid preference scope.")
        self._vehicle(user_id, vehicle_id)
        conversation = self.db.exec(
            select(Conversation).where(Conversation.id == conversation_id).with_for_update()
        ).first()
        message = self.db.get(ChatMessage, message_id)
        if (
            conversation is None
            or conversation.user_id != user_id
            or conversation.user_vehicle_id != vehicle_id
            or message is None
            or message.conversation_id != conversation_id
            or message.role != MessageRole.USER
        ):
            raise ConversationNotFound()
        if not explicit_consent(message.content):
            raise InvalidRequest("Ask explicitly to remember this preference before saving it.")
        value = validate_value(key, value)
        workshop = self._validate_workshop(key, value)
        self._matches_consent(key, value, message.content, workshop)
        scope_id = str(user_id) if scope == "account" else str(vehicle_id)
        row = self.db.exec(
            select(AgentUserMemory).where(
                AgentUserMemory.user_id == user_id,
                AgentUserMemory.scope_type == scope,
                AgentUserMemory.scope_id == scope_id,
                AgentUserMemory.memory_key == key,
                AgentUserMemory.status == "active",
            )
        ).first()
        # Retrying the same turn is idempotent and does not extend retention.
        if row and row.consent_message_id == message_id and row.value_json == value:
            return row
        when = datetime.now(UTC)
        if row is None:
            row = AgentUserMemory(
                user_id=user_id,
                scope_type=scope,
                scope_id=scope_id,
                memory_key=key,
                value_json=value,
                consent_message_id=message_id,
                expires_at=when + timedelta(days=self.settings.agent_memory_preference_retention_days),
            )
        else:
            self.db.exec(delete(AgentMemorySource).where(AgentMemorySource.memory_id == row.id))
            row.version += 1
        row.value_json, row.consent_message_id, row.consented_at = value, message_id, when
        row.updated_at = when
        row.expires_at = when + timedelta(days=self.settings.agent_memory_preference_retention_days)
        self.db.add(row)
        self.db.flush()
        self.db.add(
            AgentMemorySource(memory_id=row.id, source_message_id=message_id, source_conversation_id=conversation_id)
        )
        self.db.commit()
        self.db.refresh(row)
        return row

    @staticmethod
    def _matches_consent(key, value, content, workshop):
        text = normalized(content.replace("đ", "d").replace("Đ", "D"))
        if key == "preferred_service_window":
            days = {
                "monday": "thu hai",
                "tuesday": "thu ba",
                "wednesday": "thu tu",
                "thursday": "thu nam",
                "friday": "thu sau",
                "saturday": "thu bay",
                "sunday": "chu nhat",
            }
            periods = {"morning": "sang", "afternoon": "chieu", "evening": "buoi toi"}
            valid = (days[value["day"]] in text or value["day"] in text) and (
                periods[value["period"]] in text or value["period"] in text
            )
        elif key == "cost_display_preference":
            phrases = (
                ("tung hang muc", "chi tiet", "itemized")
                if value["format"] == "itemized"
                else ("tong chi phi", "tong tien", "total")
            )
            valid = any(phrase in text for phrase in phrases)
        else:
            valid = value["workshop_id"] in text or (workshop is not None and normalized(workshop.name) in text)
        if not valid:
            raise InvalidRequest("Preference does not match the owner's explicit request.")

    def list(self, user_id: int, vehicle_id: UUID | None = None):
        self.owner(user_id)
        if vehicle_id:
            self._vehicle(user_id, vehicle_id)
        rows = self.db.exec(
            select(AgentUserMemory)
            .where(
                AgentUserMemory.user_id == user_id,
                AgentUserMemory.status == "active",
                AgentUserMemory.expires_at > datetime.now(UTC),
            )
            .order_by(AgentUserMemory.updated_at.desc())
        ).all()
        valid = []
        for row in rows:
            if row.scope_type == "vehicle":
                if vehicle_id and row.scope_id != str(vehicle_id):
                    continue
                try:
                    self._vehicle(user_id, UUID(row.scope_id))
                except ConversationNotFound:
                    continue
            elif row.scope_id != str(user_id):
                continue
            source = self.db.get(ChatMessage, row.consent_message_id)
            conversation = self.db.get(Conversation, source.conversation_id) if source else None
            if conversation is None or conversation.user_id != user_id:
                continue
            try:
                value = validate_value(row.memory_key, row.value_json)
                self._validate_workshop(row.memory_key, value)
            except InvalidRequest:
                continue
            valid.append(row)
        return valid

    def recall(self, user_id: int, vehicle_id: UUID):
        if not self.read_enabled_for(user_id) or not self.enabled(user_id):
            return []
        return [
            {
                "key": row.memory_key,
                "scope": row.scope_type,
                "value": row.value_json,
                "source": "explicit_user_preference",
            }
            for row in self.list(user_id, vehicle_id)
        ]

    def set_enabled(self, user_id: int, enabled: bool):
        self.owner(user_id, lock=True)
        setting = self.db.get(AgentMemorySetting, user_id) or AgentMemorySetting(user_id=user_id)
        setting.enabled = enabled
        self.db.add(setting)
        self.db.commit()

    def forget(self, user_id: int, memory_id: UUID | None = None):
        self.owner(user_id, lock=True)
        if memory_id:
            row = self.db.get(AgentUserMemory, memory_id)
            if row is None or row.user_id != user_id:
                raise ConversationNotFound()
            self.db.delete(row)
        else:
            self.db.exec(delete(AgentUserMemory).where(AgentUserMemory.user_id == user_id))
        self.db.commit()

    def forget_from_chat(self, user_id: int, vehicle_id: UUID, conversation_id: UUID, message_id: UUID, key: str):
        self.owner(user_id, lock=True)
        self._vehicle(user_id, vehicle_id)
        conversation = self.db.exec(
            select(Conversation).where(Conversation.id == conversation_id).with_for_update()
        ).first()
        message = self.db.get(ChatMessage, message_id)
        if (
            conversation is None
            or conversation.user_id != user_id
            or conversation.user_vehicle_id != vehicle_id
            or message is None
            or message.conversation_id != conversation_id
            or message.role != MessageRole.USER
        ):
            raise ConversationNotFound()
        text = normalized(message.content.replace("đ", "d").replace("Đ", "D"))
        keys = {
            "preferred_service_window": ("lich", "gio", "service", "window"),
            "preferred_workshop_id": ("xuong", "workshop"),
            "cost_display_preference": ("chi phi", "gia", "cost"),
        }
        if (
            not re.match(r"^(?:hay quen|quen|xoa so thich|dung nho|forget|please forget)\b", text)
            or key not in keys
            or not any(k in text for k in keys[key])
        ):
            raise InvalidRequest("Ask explicitly to forget this preference.")
        rows = self.db.exec(
            select(AgentUserMemory).where(AgentUserMemory.user_id == user_id, AgentUserMemory.memory_key == key)
        ).all()
        for row in rows:
            if row.scope_type == "account" or row.scope_id == str(vehicle_id):
                self.db.delete(row)
        self.db.commit()

    def edit(self, user_id: int, memory_id: UUID, value: dict, version: int):
        self._write_guard(user_id)
        row = self.db.get(AgentUserMemory, memory_id, populate_existing=True)
        if row is None or row.user_id != user_id:
            raise ConversationNotFound()
        if row.version != version:
            raise ConversationError("Memory was changed; reload before editing.", code="MEMORY_CONFLICT")
        # Editing through the authenticated UI is an explicit new consent.
        value = validate_value(row.memory_key, value)
        self._validate_workshop(row.memory_key, value)
        if row.scope_type == "vehicle":
            self._vehicle(user_id, UUID(row.scope_id))
        row.value_json, row.version = value, row.version + 1
        row.updated_at = row.consented_at = datetime.now(UTC)
        row.expires_at = row.updated_at + timedelta(days=self.settings.agent_memory_preference_retention_days)
        self.db.add(row)
        self.db.commit()
        return row
