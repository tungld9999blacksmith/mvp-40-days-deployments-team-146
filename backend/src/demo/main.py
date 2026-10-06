"""Run: uvicorn src.demo.main:app (one worker, no reload during demo)."""
# ruff: noqa: N803, N815 -- names mirror existing camelCase HTTP contracts.

import html
from pathlib import Path
from uuid import UUID, uuid4

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse, StreamingResponse
from pydantic import BaseModel, Field

from .chat_service import DemoChatService, default_llm
from .dependency import current_user, make_services, verify_token
from .knowledge import DOCUMENTS, ROOT
from .registration import router as registration_router
from .registration import snapshot as registration_snapshot
from .store import DemoError
from .workshop import owner as workshop_owner
from .workshop import router as workshop_router

load_dotenv(Path(__file__).resolve().parents[3] / ".env")


class ConversationInput(BaseModel):
    userVehicleId: UUID


class MessageInput(BaseModel):
    content: str = Field(min_length=1, max_length=8000)
    clientMessageId: str = Field(min_length=1, max_length=200)


class BookingInput(BaseModel):
    userVehicleId: UUID
    confirmationToken: str = Field(min_length=1, max_length=200)
    proposalId: UUID | None = None
    milestoneRef: str | None = Field(default=None, pattern=r"^\d+$")
    quoteId: UUID | None = None
    note: str | None = Field(default=None, max_length=1000)


def create_app(demo_services=None, token_verifier=verify_token, llm_factory=default_llm):
    app = FastAPI(title="EV Care — stateful MVP demo")
    app.include_router(workshop_router)
    app.include_router(registration_router)
    s = demo_services or make_services()
    app.state.services = s
    app.state.token_verifier = token_verifier
    app.state.chat = DemoChatService(s, llm_factory)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Trace-Id"],
    )

    @app.middleware("http")
    async def trace(request, call_next):
        request.state.trace_id = str(uuid4())
        response = await call_next(request)
        response.headers["X-Trace-Id"] = request.state.trace_id
        return response

    @app.exception_handler(DemoError)
    async def demo_error(request, exc):
        return JSONResponse(
            status_code=exc.status,
            content={
                "error": {
                    "code": exc.code,
                    "message": str(exc),
                    "details": exc.details,
                    "traceId": request.state.trace_id,
                }
            },
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "INVALID_REQUEST",
                    "message": "Yêu cầu không hợp lệ.",
                    "details": {"fields": [".".join(map(str, e["loc"])) for e in exc.errors()]},
                    "traceId": request.state.trace_id,
                }
            },
        )

    def data(value):
        return {"data": value}

    def onboarding():
        return {
            "status": "ACTIVE",
            "nextStep": "HOME",
            "profileCompleted": True,
            "profileCompletedAt": s.store.timestamp(),
            "completedAt": s.store.timestamp(),
        }

    def paged(items, limit, cursor=None):
        try:
            start = int(cursor or 0)
            if start < 0:
                raise ValueError()
        except ValueError:
            raise DemoError("INVALID_CURSOR", "Cursor không hợp lệ.") from None
        end = start + limit
        return {
            "data": items[start:end],
            "page": {"hasMore": end < len(items), "nextCursor": str(end) if end < len(items) else None},
        }

    @app.get("/health")
    def health():
        return {"status": "ok", "mode": "demo", "storage": "memory"}

    @app.post("/api/v1/oauth/sign-in")
    def sign_in(u=Depends(current_user)):
        state = registration_snapshot(s.store, u)[1]["onboarding"]
        return data({"isNewUser": not state["profileCompleted"], "user": u, "onboarding": state})

    @app.get("/api/v1/oauth/profile")
    def profile(u=Depends(current_user)):
        return data({"uid": u["uid"], "email": u["email"]})

    @app.post("/api/v1/oauth/logout", status_code=204)
    def logout(u=Depends(current_user)):
        return Response(status_code=204)

    @app.get("/api/v1/onboarding")
    def onboard(u=Depends(current_user)):
        return data(registration_snapshot(s.store, u)[1])

    @app.get("/api/v1/notification-settings")
    def notifications(u=Depends(current_user)):
        return data({"remindersEnabled": False, "reminderLeadDays": 7, "defaultReminderLeadDays": 7, "channels": []})

    @app.get("/api/v1/user-vehicles")
    def vehicles(u=Depends(current_user)):
        return data(s.vehicles.list(u["userId"]))

    @app.get("/api/v1/user-vehicles/{vid}")
    def vehicle(vid: UUID, u=Depends(current_user)):
        return data(s.vehicles.profile(u["userId"], str(vid)))

    @app.get("/api/v1/user-vehicles/{vid}/maintenance-status")
    def maintenance(vid: UUID, u=Depends(current_user)):
        return data(s.maintenance.calculate(u["userId"], str(vid)))

    @app.get("/api/v1/user-vehicles/{vid}/service-records")
    def service_records(vid: UUID, u=Depends(current_user)):
        profile = s.vehicles.profile(u["userId"], str(vid))
        last = profile.get("lastService")
        items = []
        if last:
            items.append(
                {
                    "recordId": f"oem-{vid}",
                    "source": "OEM",
                    "serviceDate": last["serviceDate"],
                    "odoKm": last["odoKm"],
                    "isPeriodic": True,
                    "itemsDone": "Bảo dưỡng định kỳ",
                    "workshop": {"workshopId": None, "name": last.get("centerName") or "Hãng"},
                    "bookingId": None,
                    "bookingCode": None,
                    "actualCost": None,
                }
            )
        for booking in s.store.bookings.values():
            if (
                booking["userId"] != u["userId"]
                or booking["userVehicleId"] != str(vid)
                or booking["status"].upper() != "COMPLETED"
            ):
                continue
            items.append(
                {
                    "recordId": booking["bookingId"],
                    "source": "EV_CARE",
                    "serviceDate": booking["bookingDate"],
                    "odoKm": profile.get("odometer", {}).get("odoKm") if profile.get("odometer") else None,
                    "isPeriodic": True,
                    "itemsDone": ", ".join(item["itemName"] for item in booking["items"]),
                    "workshop": {
                        "workshopId": booking["workshopId"],
                        "name": s.store.workshops[booking["workshopId"]]["name"],
                    },
                    "bookingId": booking["bookingId"],
                    "bookingCode": booking["bookingCode"],
                    "actualCost": booking.get("actualCost"),
                }
            )
        return data({"items": sorted(items, key=lambda item: item["serviceDate"], reverse=True)})

    @app.get("/api/v1/user-vehicles/{vid}/cost-estimate")
    def estimate(vid: UUID, workshopId: UUID | None = None, u=Depends(current_user)):
        return data(s.cost.estimate(u["userId"], str(vid), str(workshopId) if workshopId else None))

    @app.get("/api/v1/workshops/nearby")
    def nearby(
        userVehicleId: UUID | None = None,
        query: str | None = None,
        date: str | None = None,
        timeSlot: str | None = None,
        u=Depends(current_user),
    ):
        return data(s.booking.nearby(u["userId"], str(userVehicleId) if userVehicleId else None, query, date, timeSlot))

    @app.get("/api/v1/workshops/{wid}/availability")
    def availability(
        wid: UUID, date: str, timeSlot: str | None = None, withAlternatives: bool = True, u=Depends(current_user)
    ):
        return data(s.booking.availability(u["userId"], str(wid), date, timeSlot, withAlternatives))

    @app.get("/api/v1/booking-proposals/{pid}")
    def proposal(pid: UUID, u=Depends(current_user)):
        return data(s.booking.prepare_proposal(u["userId"], str(pid)))

    @app.post("/api/v1/bookings")
    async def booking(
        body: BookingInput, idempotency_key: str = Header(alias="Idempotency-Key"), u=Depends(current_user)
    ):
        return data(
            await s.booking.create(u["userId"], body.model_dump(mode="json", exclude_none=True), idempotency_key)
        )

    @app.get("/api/v1/bookings")
    def my_bookings(
        scope: str = "UPCOMING",
        limit: int = Query(20, ge=1, le=100),
        cursor: str | None = None,
        u=Depends(current_user),
    ):
        if scope not in {"UPCOMING", "PAST"}:
            raise DemoError("INVALID_REQUEST", "Phạm vi lịch hẹn không hợp lệ.")
        items = [
            s.booking.ticket(u["userId"], booking["bookingId"])
            for booking in s.store.bookings.values()
            if booking["userId"] == u["userId"]
            and ((booking["status"].upper() in {"COMPLETED", "CANCELLED"}) == (scope == "PAST"))
        ]
        for item in items:
            item["status"] = item["status"].upper()
        items.sort(key=lambda item: item["appointmentAt"], reverse=scope == "PAST")
        try:
            start = int(cursor or 0)
            if start < 0:
                raise ValueError()
        except ValueError:
            raise DemoError("INVALID_CURSOR", "Cursor không hợp lệ.") from None
        return data(
            {
                "items": items[start : start + limit],
                "nextCursor": str(start + limit) if len(items) > start + limit else None,
            }
        )

    @app.get("/api/v1/notifications")
    def notification_feed(u=Depends(current_user)):
        items = []
        for booking in s.store.bookings.values():
            if booking["userId"] != u["userId"]:
                continue
            for index, event in enumerate(booking.get("history", [])):
                if event["toStatus"] not in {"CONFIRMED", "COMPLETED", "CANCELLED"}:
                    continue
                items.append(
                    {
                        "id": f"{booking['bookingId']}-{index}",
                        "kind": "BOOKING_UPDATE",
                        "occurredAt": event["at"],
                        "unread": False,
                        "reminder": None,
                        "followUp": None,
                        "booking": {
                            "bookingId": booking["bookingId"],
                            "bookingCode": booking["bookingCode"],
                            "status": event["toStatus"],
                            "reasonCode": event.get("reasonCode"),
                            "bookingDate": booking["bookingDate"],
                            "timeSlot": booking["timeSlot"],
                            "workshopName": s.store.workshops[booking["workshopId"]]["name"],
                        },
                    }
                )
        return data({"items": sorted(items, key=lambda item: item["occurredAt"], reverse=True), "unreadCount": 0})

    @app.get("/api/v1/bookings/by-code/{code}")
    def resolve_code(code: str, u=Depends(current_user)):
        for booking in s.store.bookings.values():
            if booking["userId"] == u["userId"] and booking["bookingCode"] == code.upper():
                return data({"bookingId": booking["bookingId"]})
        raise DemoError("BOOKING_NOT_FOUND", "Không tìm thấy lịch hẹn.", 404)

    @app.get("/api/v1/bookings/{bid}")
    def ticket(bid: UUID, u=Depends(current_user)):
        return data(s.booking.ticket(u["userId"], str(bid)))

    def progress_payload(booking):
        stages = {"CHECKED_IN": "CHECKED_IN", "IN_PROGRESS": "SERVICING", "COMPLETED": "READY_FOR_PICKUP"}
        entries = [
            {
                "stage": stages[event["toStatus"]],
                "note": event.get("note"),
                "actorType": "WORKSHOP_OWNER",
                "createdAt": event["at"],
            }
            for event in booking.get("history", [])
            if event["toStatus"] in stages
        ]
        return {
            "bookingId": booking["bookingId"],
            "bookingStatus": booking["status"].upper(),
            "currentStage": entries[-1]["stage"] if entries else None,
            "isFrozen": booking["status"].upper() in {"COMPLETED", "CANCELLED"},
            "nextStages": [],
            "entries": entries,
        }

    @app.get("/api/v1/bookings/{bid}/progress")
    def owner_progress(bid: UUID, u=Depends(current_user)):
        return data(progress_payload(s.booking.owned(u["userId"], str(bid))))

    def workshop_booking(bid, owner):
        booking = s.store.bookings.get(str(bid))
        if not booking or booking["workshopId"] != owner["workshopId"]:
            raise DemoError("BOOKING_NOT_FOUND", "Không tìm thấy lịch hẹn.", 404)
        return booking

    @app.get("/api/v1/workshop-owner/bookings/{bid}/progress")
    def shop_progress(bid: UUID, o=Depends(workshop_owner)):
        return data(progress_payload(workshop_booking(bid, o)))

    @app.get("/api/v1/workshop/bookings/{bid}/conversation-excerpt")
    def excerpt(bid: UUID, o=Depends(workshop_owner)):
        booking = workshop_booking(bid, o)
        cid = booking.get("conversationId")
        return data(
            {
                "source": {"type": "booking", "id": str(bid), "confirmedMessageId": booking.get("sourceMessageId")},
                "messages": [s.messages.dto(message) for message in s.store.messages.get(cid, [])],
            }
        )

    @app.post("/api/v1/conversations")
    def conversation(body: ConversationInput, u=Depends(current_user)):
        return data(s.messages.create(u["userId"], str(body.userVehicleId)))

    @app.get("/api/v1/conversations")
    def conversations(
        userVehicleId: UUID | None = None,
        limit: int = Query(20, ge=1, le=100),
        cursor: str | None = None,
        u=Depends(current_user),
    ):
        items = [
            c
            for c in s.store.conversations.values()
            if c["userId"] == u["userId"] and (not userVehicleId or c["userVehicleId"] == str(userVehicleId))
        ]
        return paged(sorted(items, key=lambda c: c["lastMessageAt"], reverse=True), limit, cursor)

    @app.get("/api/v1/conversations/search")
    def search(
        q: str,
        userVehicleId: UUID | None = None,
        limit: int = Query(20, ge=1, le=100),
        cursor: str | None = None,
        u=Depends(current_user),
    ):
        found = []
        for c in s.store.conversations.values():
            if c["userId"] != u["userId"] or (userVehicleId and c["userVehicleId"] != str(userVehicleId)):
                continue
            for m in s.store.messages[c["id"]]:
                if q.casefold() in m["content"].casefold():
                    found.append(
                        {
                            "conversationId": c["id"],
                            "conversationTitle": c["title"],
                            "messageId": m["id"],
                            "seq": m["seq"],
                            "role": m["role"],
                            "snippet": html.escape(m["content"][:200]),
                            "createdAt": m["createdAt"],
                        }
                    )
        return paged(found, limit, cursor)

    @app.get("/api/v1/conversations/{cid}/messages")
    def messages(
        cid: UUID,
        limit: int = Query(30, ge=1, le=100),
        before: int | None = None,
        after: int | None = None,
        u=Depends(current_user),
    ):
        s.messages.owned(u["userId"], str(cid))
        items = [
            s.messages.dto(m)
            for m in s.store.messages[str(cid)]
            if (before is None or m["seq"] < before) and (after is None or m["seq"] > after)
        ]
        chosen = items[:limit] if after is not None else items[-limit:]
        return {
            "data": chosen,
            "page": {
                "hasMore": len(items) > limit,
                "nextCursor": str(chosen[0]["seq"]) if chosen and len(items) > limit else None,
            },
        }

    @app.post("/api/v1/conversations/{cid}/messages")
    async def send(cid: UUID, body: MessageInput, request: Request, u=Depends(current_user)):
        s.messages.owned(u["userId"], str(cid))
        if s.store.chat_locks[str(cid)].locked():
            raise DemoError("CONVERSATION_BUSY", "Hội thoại đang trả lời.", 409)
        return StreamingResponse(
            app.state.chat.stream(u["userId"], str(cid), body.content, body.clientMessageId),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.get("/api/v1/demo/documents/{document_id}")
    def document(document_id: str):
        if document_id not in DOCUMENTS:
            raise DemoError("DOCUMENT_NOT_FOUND", "Không tìm thấy tài liệu.", 404)
        return PlainTextResponse((ROOT / DOCUMENTS[document_id][0]).read_text(encoding="utf-8"))

    @app.post("/api/v1/demo/reset")
    async def reset(u=Depends(current_user)):
        uid = u["userId"]
        async with s.store.booking_lock:
            owned = [cid for cid, c in s.store.conversations.items() if c["userId"] == uid]
            if any(s.store.chat_locks[cid].locked() for cid in owned):
                raise DemoError("CONVERSATION_BUSY", "Đợi agent hoàn tất trước khi reset.", 409)
            for cid in owned:
                await app.state.chat.memory.adelete_thread(cid)
                del s.store.conversations[cid], s.store.messages[cid], s.store.chat_locks[cid]
            for name in ("bookings", "tokens", "proposals"):
                mapping = getattr(s.store, name)
                for key in [k for k, v in mapping.items() if v["userId"] == uid]:
                    del mapping[key]
            for key in [k for k in s.store.operations if k[0] == uid]:
                del s.store.operations[key]
        return data({"reset": True, "scope": "current_user"})

    @app.delete("/api/v1/conversations/{cid}", status_code=204)
    async def delete_conversation(cid: UUID, u=Depends(current_user)):
        cid = str(cid)
        s.messages.owned(u["userId"], cid)
        if s.store.chat_locks[cid].locked():
            raise DemoError("CONVERSATION_BUSY", "Hội thoại đang trả lời.", 409)
        await app.state.chat.memory.adelete_thread(cid)
        del s.store.conversations[cid], s.store.messages[cid], s.store.chat_locks[cid]
        for pid in [p for p, value in s.store.proposals.items() if value["conversationId"] == cid]:
            del s.store.proposals[pid]
        return Response(status_code=204)

    return app


app = create_app()
