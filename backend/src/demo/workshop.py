"""Workshop demo: Firebase identity, scoped board and shared booking transitions."""
# ruff: noqa: N803 -- query names mirror the existing HTTP contract.

import json
import os
from copy import deepcopy
from datetime import date, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request, Response

from src.modules.workshop_board.schemas import BookingStatusIn, TransitionRequest

from .dependency import verified_claims
from .fixtures import SLOT_TIMES, WORKSHOP_IDS, stable_id
from .store import DemoError

router = APIRouter(prefix="/api/v1/workshop-owner")


def onboarding():
    return {
        "status": "ACTIVE",
        "nextStep": "DASHBOARD",
        "profileCompleted": True,
        "profileCompletedAt": None,
        "completedAt": None,
        "expiresAt": None,
    }


async def owner(request: Request, authorization: str | None = Header(default=None)):
    claims = await verified_claims(request, authorization)
    defaults = {f"workshop{i + 1}@example.com": wid for i, wid in enumerate(WORKSHOP_IDS)}
    try:
        accounts = json.loads(os.environ["DEMO_WORKSHOP_OWNERS"]) if os.getenv("DEMO_WORKSHOP_OWNERS") else defaults
        if not isinstance(accounts, dict):
            raise ValueError()
    except (ValueError, TypeError):
        raise DemoError("DEMO_CONFIG_ERROR", "Cấu hình tài khoản xưởng không hợp lệ.", 503) from None
    email = (claims.get("email") or "").lower()
    store = request.app.state.services.store
    wid = accounts.get(email)
    if not claims.get("email_verified") or wid not in store.workshops:
        raise DemoError("WORKSHOP_OWNER_NOT_REGISTERED", "Email chưa được cấp quyền xưởng demo.", 403)
    uid = str(claims["uid"])
    previous = store.workshop_owners.get(uid)
    if previous and (previous["email"] != email or previous["workshopId"] != wid):
        raise DemoError("EMAIL_ALREADY_LINKED", "Tài khoản đã liên kết với xưởng khác.", 403)
    value = previous or {
        "ownerId": stable_id(f"workshop-owner:{uid}"),
        "email": email,
        "displayName": claims.get("name") or "Chủ xưởng demo",
        "fullName": claims.get("name") or "Chủ xưởng demo",
        "avatarUrl": claims.get("picture"),
        "accountStatus": "active",
        "roles": ["workshop_owner"],
        "workshopId": wid,
        "lastLoginAt": None,
        "lastLogoutAt": None,
    }
    store.workshop_owners[uid] = value
    return value


def summary(store, wid):
    return {
        **deepcopy(store.workshops[wid]),
        "centerId": wid,
        "type": "SERVICE_ONLY",
        "status": "ACTIVE",
        "latitude": store.workshops[wid].get("latitude"),
        "longitude": store.workshops[wid].get("longitude"),
        "hotline": store.workshops[wid].get("hotline"),
        "totalTechnicians": store.workshops[wid].get("totalTechnicians", 2),
        "emergencySlotsReserved": store.workshops[wid].get("emergencySlotsReserved", 0),
        "onboardedAt": None,
        "operatingHours": store.workshops[wid].get("operatingHours")
        or [{"dayOfWeek": d, "isClosed": False, "openTime": "08:00", "closeTime": "18:00"} for d in range(1, 8)],
    }


def owned(store, wid, bid):
    b = store.bookings.get(str(bid))
    if not b or b["workshopId"] != wid:
        raise DemoError("BOOKING_NOT_FOUND", "Không tìm thấy lịch hẹn.", 404)
    return b


def actions(store, b):
    if b["status"] == "confirmed":
        return (["CHECK_IN"] if b["bookingDate"] == store.clock().date().isoformat() else []) + ["CANCEL"]
    return {"checked_in": ["START"], "in_progress": ["COMPLETE"]}.get(b["status"], [])


def detail(store, b):
    user = next(u for u in store.users.values() if u["userId"] == b["userId"])
    vehicle = store.vehicles[b["userVehicleId"]]
    return {
        "bookingId": b["bookingId"],
        "bookingCode": b["bookingCode"],
        "status": b["status"].upper(),
        "bookingDate": b["bookingDate"],
        "timeSlot": b["timeSlot"],
        "customer": {"fullName": user["fullName"], "phone": None},
        "vehicle": {"modelName": vehicle["modelName"], "licensePlate": vehicle["licensePlate"]},
        "milestoneLabel": f"Mốc {b['odoMilestone']:,} km",
        "estimatedCost": b["estimatedCost"],
        "actualCost": b.get("actualCost"),
        "quote": None,
        "attendanceConfirmedAt": None,
        "confirmDeadline": None,
        "allowedActions": actions(store, b),
        "note": b.get("note"),
        "statusHistory": deepcopy(b.get("history", [])),
        "items": deepcopy(b["items"]),
    }


@router.post("/oauth/sign-in")
async def sign_in(request: Request, o=Depends(owner)):
    from .registration import snapshot

    store = request.app.state.services.store
    o["lastLoginAt"] = store.timestamp()
    state = snapshot(store, o, "workshop")[1]
    return {
        "data": {
            "isNewOwner": not state["onboarding"]["profileCompleted"],
            "owner": {k: v for k, v in o.items() if k not in ("workshopId", "lastLoginAt", "lastLogoutAt")},
            "onboarding": state["onboarding"],
            "workshop": state["workshop"],
        }
    }


@router.get("/oauth/session")
async def session(request: Request, o=Depends(owner)):
    from .registration import snapshot

    return {
        "data": {
            **{k: o[k] for k in ("ownerId", "email", "accountStatus", "lastLoginAt", "lastLogoutAt")},
            "onboarding": snapshot(request.app.state.services.store, o, "workshop")[1]["onboarding"],
        }
    }


@router.post("/oauth/logout", status_code=204)
async def logout(request: Request, o=Depends(owner)):
    o["lastLogoutAt"] = request.app.state.services.store.timestamp()
    return Response(status_code=204)


@router.get("/onboarding")
async def snapshot(request: Request, o=Depends(owner)):
    from .registration import snapshot as registration_snapshot

    return {"data": registration_snapshot(request.app.state.services.store, o, "workshop")[1]}


@router.get("/bookings")
async def board(
    request: Request,
    from_: date | None = Query(default=None, alias="from"),
    to: date | None = None,
    status: list[BookingStatusIn] | None = Query(default=None),
    q: str | None = None,
    o=Depends(owner),
):
    store = request.app.state.services.store
    start = from_ or store.clock().date()
    end = to or start + timedelta(days=29)
    if start > end or (end - start).days >= 31 or start < store.clock().date() - timedelta(days=90):
        raise DemoError("INVALID_REQUEST", "Chọn khoảng tối đa 31 ngày, không quá 90 ngày trong quá khứ.")
    if q is not None and not 2 <= len(q.strip()) <= 20:
        raise DemoError("INVALID_REQUEST", "Tìm kiếm cần 2–20 ký tự.")
    rows = sorted(
        (
            b
            for b in store.bookings.values()
            if b["workshopId"] == o["workshopId"] and start.isoformat() <= b["bookingDate"] <= end.isoformat()
        ),
        key=lambda b: (b["bookingDate"], b["timeSlot"]),
    )
    counts = {s.value: sum(b["status"].upper() == s.value for b in rows) for s in BookingStatusIn}
    items = [detail(store, b) for b in rows if not status or b["status"].upper() in status]
    if q:
        items = [
            b for b in items if q.strip().casefold() in f"{b['bookingCode']} {b['vehicle']['licensePlate']}".casefold()
        ]
    return {
        "data": {
            "workshopId": o["workshopId"],
            "confirmationMode": "AUTO",
            "demoNow": store.timestamp(),
            "from": start.isoformat(),
            "to": end.isoformat(),
            "summary": counts,
            "items": items,
        }
    }


@router.get("/bookings/by-code/{code}")
async def lookup_code(request: Request, code: str, o=Depends(owner)):
    store = request.app.state.services.store
    b = next(
        (b for b in store.bookings.values() if b["workshopId"] == o["workshopId"] and b["bookingCode"] == code.upper()),
        None,
    )
    if not b:
        raise DemoError("BOOKING_NOT_FOUND", "Không tìm thấy lịch hẹn.", 404)
    eligibility = (
        "ALREADY_CHECKED_IN"
        if b["status"] in {"checked_in", "in_progress", "completed"}
        else "NOT_CONFIRMED"
        if b["status"] != "confirmed"
        else "NOT_TODAY"
        if b["bookingDate"] != store.clock().date().isoformat()
        else "ELIGIBLE"
    )
    return {
        "data": {
            **detail(store, b),
            "checkInEligibility": eligibility,
            "checkedInAt": next((e["at"] for e in b.get("history", []) if e["toStatus"] == "CHECKED_IN"), None),
        }
    }


@router.get("/capacity")
async def capacity(
    request: Request, from_: date = Query(alias="from"), days: int = Query(7, ge=1, le=31), o=Depends(owner)
):
    services = request.app.state.services
    store = services.store
    wid = o["workshopId"]
    result = []
    for offset in range(days):
        day = (from_ + timedelta(days=offset)).isoformat()
        slots = []
        for time_slot in SLOT_TIMES:
            occupied = sum(
                b["workshopId"] == wid
                and b["bookingDate"] == day
                and b["timeSlot"] == time_slot
                and b["status"] != "cancelled"
                for b in store.bookings.values()
            )
            slots.append(
                {
                    "timeSlot": time_slot,
                    "occupied": occupied,
                    "blocked": 0,
                    "remaining": services.booking.remaining(wid, day, time_slot),
                    "maxBlock": 0,
                    "blockReason": None,
                    "blockNote": None,
                }
            )
        result.append({"date": day, "isClosed": False, "openTime": "08:00", "closeTime": "18:00", "slots": slots})
    return {"data": {"totalTechnicians": 2, "emergencySlotsReserved": 0, "days": result}}


@router.get("/booking-settings")
async def booking_settings(o=Depends(owner)):
    return {"data": {"confirmationMode": "AUTO", "wsConfirmDeadlineHours": 24, "pendingCount": 0}}


@router.put("/booking-settings")
@router.put("/slot-blocks")
async def unsupported_settings(o=Depends(owner)):
    raise DemoError("FEATURE_NOT_AVAILABLE", "Demo hiện chỉ hỗ trợ xác nhận tự động và xem sức chứa.", 409)


@router.get("/bookings/{bid}")
async def booking(request: Request, bid: UUID, o=Depends(owner)):
    store = request.app.state.services.store
    return {"data": detail(store, owned(store, o["workshopId"], bid))}


@router.post("/bookings/{bid}/transitions")
async def transition(request: Request, bid: UUID, body: TransitionRequest, o=Depends(owner)):
    services = request.app.state.services
    store = services.store
    async with store.booking_lock:
        b = owned(store, o["workshopId"], bid)
        if b["status"].upper() != body.expected_status:
            raise DemoError("STATUS_CONFLICT", "Lịch hẹn đã thay đổi. Hãy tải lại.", 409)
        if body.action not in actions(store, b):
            raise DemoError("INVALID_TRANSITION", "Thao tác không hợp lệ với trạng thái hoặc ngày hẹn.", 409)
        if body.source.value == "QR_SCAN" and body.action != "CHECK_IN":
            raise DemoError("INVALID_REQUEST", "QR_SCAN chỉ hợp lệ cho tiếp nhận xe.")
        if body.action == "CANCEL" and (body.reason_code != "OTHER" or not (body.note or "").strip()):
            raise DemoError("INVALID_REQUEST", "Cần nhập lý do hủy.")
        if body.action == "COMPLETE" and body.actual_cost is None:
            raise DemoError("INVALID_REQUEST", "Cần nhập chi phí thực tế.")
        target = {"CHECK_IN": "checked_in", "START": "in_progress", "COMPLETE": "completed", "CANCEL": "cancelled"}[
            body.action
        ]
        event = {
            "fromStatus": b["status"].upper(),
            "toStatus": target.upper(),
            "actorType": "WORKSHOP",
            "source": body.source.value,
            "reasonCode": body.reason_code,
            "note": body.note,
            "at": store.timestamp(),
        }
        b.setdefault("history", []).append(event)
        b["status"] = target
        if body.actual_cost is not None:
            b["actualCost"] = float(body.actual_cost)
        if body.note:
            b["note"] = body.note
        cid = b.get("conversationId")
        if cid in store.conversations:
            services.messages.append(
                cid,
                "assistant",
                f"Xưởng cập nhật lịch {b['bookingCode']}: {target.upper()}.",
                refs={"bookingId": b["bookingId"]},
            )
        return {
            "data": {
                "bookingId": b["bookingId"],
                "status": target.upper(),
                "actualCost": b.get("actualCost"),
                "effects": None,
                "allowedActions": actions(store, b),
            }
        }
