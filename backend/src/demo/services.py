"""API and agent ports share these stateful services, never canned booking success."""

from __future__ import annotations

import asyncio
import calendar
import hashlib
import json
import secrets
from copy import deepcopy
from datetime import date, datetime, time, timedelta
from uuid import uuid4

from .fixtures import SLOT_TIMES, stable_id
from .store import DemoError, DemoStore


class MockVehicleService:
    def __init__(self, store: DemoStore):
        self.store = store

    def owned(self, user_id: int, vehicle_id: str) -> dict:
        vehicle = self.store.vehicles.get(str(vehicle_id))
        if not vehicle or vehicle["userId"] != user_id:
            raise DemoError("VEHICLE_NOT_FOUND", "Không tìm thấy xe.", 404)
        if not vehicle["active"] or not vehicle["verified"]:
            raise DemoError("VEHICLE_NOT_ACTIVE", "Xe chưa được xác thực.", 409)
        return vehicle

    def list(self, user_id: int) -> list[dict]:
        keys = ("userVehicleId", "modelName", "trim", "licensePlate", "color")
        return [
            {k: v[k] for k in keys}
            for v in self.store.vehicles.values()
            if v["userId"] == user_id and v["active"] and v["verified"]
        ]

    def profile(self, user_id: int, vehicle_id: str) -> dict:
        v = self.owned(user_id, vehicle_id)
        return {
            **{
                k: v[k]
                for k in ("userVehicleId", "modelName", "modelId", "trim", "licensePlate", "color", "manufactureDate")
            },
            "vinMasked": "VF6*********0001",
            "productionYear": 2024,
            "batteryCapacityKwh": 59.6,
            "motorPowerKw": 150,
            "warranties": [
                {
                    **w,
                    "isActive": self.store.clock().date() <= date.fromisoformat(w["endDate"])
                    and (v["odoKm"] is None or v["odoKm"] <= w["kmLimit"]),
                }
                for w in v["warranties"]
            ],
            "odometer": self.odometer(v),
            "oemSyncedAt": self.store.timestamp(),
            "lastService": {
                "serviceDate": v["lastServiceDate"],
                "odoKm": v["lastServiceOdo"],
                "source": "OEM",
                "centerName": "Xưởng hãng giả lập SC-02",
            },
        }

    def odometer(self, vehicle: dict) -> dict | None:
        if vehicle["odoKm"] is None:
            return None
        return {
            "odoKm": vehicle["odoKm"],
            "recordedAt": vehicle["odoRecordedAt"],
            "isStale": (self.store.clock() - datetime.fromisoformat(vehicle["odoRecordedAt"])).days > 30,
            "dataSource": "OEM_DEMO_SNAPSHOT",
        }


class MockMaintenanceService:
    def __init__(self, store: DemoStore, vehicles: MockVehicleService):
        self.store, self.vehicles = store, vehicles

    def calculate(self, user_id: int, vehicle_id: str) -> dict:
        v = self.vehicles.owned(user_id, vehicle_id)
        today = self.store.clock().date()
        last = date.fromisoformat(v["lastServiceDate"])
        # Demo rule: repeated 12,000 km / 12 months after the last completed milestone.
        km = ((v["lastServiceOdo"] or 0) // 12000 + 1) * 12000
        due = last.replace(year=last.year + 1, day=min(last.day, calendar.monthrange(last.year + 1, last.month)[1]))
        remaining_km = km - v["odoKm"] if v["odoKm"] is not None else None
        remaining_days = (due - today).days
        if remaining_km is None:
            status, reason = "UNKNOWN", None
        else:
            by_km, by_time = remaining_km <= 0, remaining_days <= 0
            reason = "BOTH" if by_km and by_time else "KM" if by_km else "TIME" if by_time else None
            status = (
                "OVERDUE"
                if by_km or by_time
                else "DUE_SOON"
                if remaining_km <= 500 or remaining_days <= 14
                else "NORMAL"
            )
        return {
            "userVehicleId": vehicle_id,
            "dueStatus": status,
            "dueReason": reason,
            "calculationBasis": "KM_AND_TIME" if remaining_km is not None else "TIME_ONLY",
            "unknownReason": "OEM_DATA_NOT_SYNCED" if remaining_km is None else None,
            "nextMilestone": {
                "odoMilestoneKm": km,
                "monthMilestone": 12,
                "label": f"{km} km / 12 months",
                "dueDate": due.isoformat(),
                "isRecurring": True,
                "items": deepcopy(self.store.rules),
            },
            "remainingKm": remaining_km,
            "remainingDays": remaining_days,
            "odometer": self.vehicles.odometer(v),
            "lastService": {"type": "PERIODIC", "date": last.isoformat(), "odoKm": v["lastServiceOdo"]},
            "thresholds": {"dueSoonKm": 500, "dueSoonDays": 14},
            "oemSyncedAt": self.store.timestamp(),
            "calculatedAt": self.store.timestamp(),
            "dataSource": "DEMO_RULE",
            "note": "Thông tin bảo dưỡng tham khảo; không phải xác nhận chính sách hãng.",
        }


class MockCostService:
    def __init__(self, store: DemoStore, vehicles: MockVehicleService, maintenance: MockMaintenanceService):
        self.store, self.vehicles, self.maintenance = store, vehicles, maintenance

    def estimate(
        self, user_id: int, vehicle_id: str, workshop_id: str | None = None, milestone: int | None = None
    ) -> dict:
        v = self.vehicles.owned(user_id, vehicle_id)
        wid = workshop_id or next(iter(self.store.workshops))
        if wid not in self.store.workshops:
            raise DemoError("WORKSHOP_NOT_FOUND", "Không tìm thấy xưởng.", 404)
        current = self.maintenance.calculate(user_id, vehicle_id)["nextMilestone"]
        if milestone is not None and milestone != current["odoMilestoneKm"]:
            raise DemoError("INVALID_MILESTONE", "Mốc không khớp dữ liệu xe.")
        items = [
            {
                "maintenanceRuleId": stable_id(r["itemCode"]),
                "itemCode": r["itemCode"],
                "itemName": r["itemName"],
                "covered": r["isCoveredByWarranty"],
                "price": 0 if r["isCoveredByWarranty"] else self.store.prices[wid][r["itemCode"]],
                "priceSource": "DEMO_WORKSHOP_PRICE",
            }
            for r in self.store.rules
        ]
        return {
            "status": "SUCCESS",
            "userVehicleId": vehicle_id,
            "modelId": v["modelId"],
            "milestone": {"odoMilestoneKm": current["odoMilestoneKm"], "monthMilestone": 12, "isNext": True},
            "workshop": {"workshopId": wid, "name": self.store.workshops[wid]["name"], "selectedBy": "SPECIFIED"},
            "warrantyStatus": "DEMO",
            "items": items,
            "coveredCount": sum(i["covered"] for i in items),
            "chargeableTotal": sum(i["price"] for i in items),
            "hasReferencePrice": True,
            "currency": "VND",
            "estimateLabel": "Chi phí ước tính",
            "computedAt": self.store.timestamp(),
        }


class MockMessageService:
    def __init__(self, store: DemoStore, vehicles: MockVehicleService):
        self.store, self.vehicles = store, vehicles

    def owned(self, user_id: int, conversation_id: str) -> dict:
        c = self.store.conversations.get(str(conversation_id))
        if not c or c["userId"] != user_id:
            raise DemoError("CONVERSATION_NOT_FOUND", "Không tìm thấy hội thoại.", 404)
        return c

    def create(self, user_id: int, vehicle_id: str, title: str | None = None) -> dict:
        self.vehicles.owned(user_id, vehicle_id)
        cid = str(uuid4())
        c = {
            "id": cid,
            "userId": user_id,
            "userVehicleId": vehicle_id,
            "title": title,
            "lastMessageAt": self.store.timestamp(),
            "createdAt": self.store.timestamp(),
        }
        self.store.conversations[cid], self.store.messages[cid] = c, []
        self.store.chat_locks[cid] = asyncio.Lock()
        return c

    def append(self, cid: str, role: str, content: str, **extra) -> dict:
        self.store.seq += 1
        msg = {
            "id": str(uuid4()),
            "seq": self.store.seq,
            "role": role,
            "content": content,
            "citations": [],
            "refs": {},
            "card": None,
            "createdAt": self.store.timestamp(),
            **extra,
        }
        self.store.messages[cid].append(msg)
        c = self.store.conversations[cid]
        c["lastMessageAt"] = msg["createdAt"]
        if not c["title"] and role == "user":
            c["title"] = content[:60]
        return msg

    def dto(self, message: dict) -> dict:
        result = {k: v for k, v in message.items() if k not in ("clientMessageId", "replyTo")}
        card = result.get("card")
        if card and card.get("type") == "booking_proposal":
            booked = next((b for b in self.store.bookings.values() if b.get("proposalId") == card["proposalId"]), None)
            status = (
                "CONFIRMED"
                if booked
                else "EXPIRED"
                if datetime.fromisoformat(card["expiresAt"]) <= self.store.clock()
                else "PROPOSED"
            )
            result["card"] = {
                **card,
                "status": status,
                "booking": {
                    "bookingId": booked["bookingId"],
                    "bookingCode": booked["bookingCode"],
                    "status": booked["status"].upper(),
                    "ownerCancelableUntil": None,
                }
                if booked
                else None,
            }
        return result


class MockBookingService:
    def __init__(
        self, store: DemoStore, vehicles: MockVehicleService, cost: MockCostService, messages: MockMessageService
    ):
        self.store, self.vehicles, self.cost, self.messages = store, vehicles, cost, messages

    def workshop(self, wid: str) -> dict:
        w = self.store.workshops.get(str(wid))
        if not w:
            raise DemoError("WORKSHOP_NOT_FOUND", "Không tìm thấy xưởng.", 404)
        return w

    def validate_slot(self, wid: str, d: str, t: str | None = None) -> str | None:
        self.workshop(wid)
        try:
            day = date.fromisoformat(d)
            canonical = time.fromisoformat(t).isoformat() if t else None
        except ValueError as exc:
            raise DemoError("INVALID_REQUEST", "Ngày/giờ không hợp lệ.") from exc
        now = self.store.clock()
        if day < now.date() or day > now.date() + timedelta(days=30):
            raise DemoError("INVALID_DATE", "Chọn ngày trong 30 ngày tới.")
        if canonical and (
            canonical not in SLOT_TIMES
            or datetime.combine(day, time.fromisoformat(canonical), tzinfo=now.tzinfo) <= now
        ):
            raise DemoError("SLOT_OUT_OF_HOURS", "Khung giờ đã qua hoặc ngoài giờ làm việc.")
        return canonical

    def remaining(self, wid: str, d: str, t: str) -> int:
        # First slot is full; afternoon slot has exactly one place for race testing.
        capacity = self.store.slot_capacity.get((wid, d, t), 0 if t == SLOT_TIMES[0] else 1 if t == "14:00:00" else 2)
        used = sum(
            b["status"] in ("pending", "confirmed", "checked_in", "in_progress", "completed")
            and b["workshopId"] == wid
            and b["bookingDate"] == d
            and b["timeSlot"] == t
            for b in self.store.bookings.values()
        )
        return max(0, capacity - used)

    def availability(self, user_id: int, wid: str, d: str, t: str | None = None, alternatives: bool = True) -> dict:
        t = self.validate_slot(wid, d, t)
        now = self.store.clock()
        slots = [
            {"timeSlot": x, "available": self.remaining(wid, d, x) > 0, "remaining": self.remaining(wid, d, x)}
            for x in SLOT_TIMES
            if datetime.combine(date.fromisoformat(d), time.fromisoformat(x), tzinfo=now.tzinfo) > now
        ]
        requested = next((dict(s) for s in slots if s["timeSlot"] == t), None)
        if requested:
            requested["confirmationToken"] = None
            if requested["available"]:
                token = secrets.token_urlsafe(24)
                self.store.tokens[token] = {
                    "userId": user_id,
                    "workshopId": wid,
                    "date": d,
                    "timeSlot": t,
                    "expiresAt": now + timedelta(minutes=10),
                    "used": False,
                }
                requested["confirmationToken"] = token
        alts = [
            {
                "workshopId": wid,
                "name": self.workshop(wid)["name"],
                "date": d,
                "timeSlot": s["timeSlot"],
                "remaining": s["remaining"],
            }
            for s in slots
            if s["available"] and s["timeSlot"] != t
        ][:3]
        return {
            "workshopId": wid,
            "date": d,
            "requested": requested,
            "slots": slots,
            "alternatives": alts if alternatives else [],
        }

    def nearby(
        self,
        user_id: int,
        vehicle_id: str | None = None,
        query: str | None = None,
        d: str | None = None,
        t: str | None = None,
    ) -> dict:
        if vehicle_id:
            self.vehicles.owned(user_id, vehicle_id)
        workshops = []
        for w in self.store.workshops.values():
            if query and query.casefold() not in (w["address"] + w["name"] + w["region"]).casefold():
                continue
            out = deepcopy(w)
            if d and t:
                requested = self.availability(user_id, w["workshopId"], d, t)["requested"]
                out["availability"] = {"date": d, **requested} if requested else None
            workshops.append(out)
        return {
            "anchor": {
                "source": "SPECIFIED" if query else "PROFILE",
                "province": "Hà Nội",
                "lat": None,
                "lng": None,
                "query": query,
                "rankedBy": "REGION",
            },
            "workshops": workshops,
        }

    def proposal(self, user_id: int, vehicle_id: str, cid: str, source_id: str, wid: str, d: str, t: str) -> dict:
        vehicle = self.vehicles.owned(user_id, vehicle_id)
        conv = self.messages.owned(user_id, cid)
        if conv["userVehicleId"] != vehicle_id:
            raise DemoError("VEHICLE_NOT_FOUND", "Xe không thuộc hội thoại.", 404)
        av = self.availability(user_id, wid, d, t)
        if not av["requested"] or not av["requested"]["available"]:
            raise DemoError("SLOT_FULL", "Khung giờ đã đầy.", 409, alternatives=av["alternatives"])
        pid = str(uuid4())
        estimate = self.cost.estimate(user_id, vehicle_id, wid)
        proposal = {
            "type": "booking_proposal",
            "vehicle": {
                "userVehicleId": vehicle_id,
                "modelName": vehicle["modelName"],
                "trim": vehicle["trim"],
                "licensePlateMasked": vehicle["licensePlate"],
            },
            "proposalId": pid,
            "userId": user_id,
            "userVehicleId": vehicle_id,
            "conversationId": cid,
            "sourceMessageId": source_id,
            "workshopId": wid,
            "workshopName": self.workshop(wid)["name"],
            "date": d,
            "timeSlot": av["requested"]["timeSlot"],
            "odoMilestone": estimate["milestone"]["odoMilestoneKm"],
            "estimatedCost": estimate["chargeableTotal"],
            "items": estimate["items"],
            "expiresAt": (self.store.clock() + timedelta(minutes=10)).isoformat(),
            "confirmationToken": av["requested"]["confirmationToken"],
        }
        self.store.proposals[pid] = proposal
        return {k: v for k, v in proposal.items() if k not in ("userId", "confirmationToken")}

    def owned_proposal(self, user_id: int, pid: str) -> dict:
        p = self.store.proposals.get(pid)
        if not p or p["userId"] != user_id:
            raise DemoError("PROPOSAL_NOT_FOUND", "Không tìm thấy đề xuất.", 404)
        self.vehicles.owned(user_id, p["userVehicleId"])
        return p

    def prepare_proposal(self, user_id: int, pid: str) -> dict:
        p = self.owned_proposal(user_id, pid)
        av = self.availability(user_id, p["workshopId"], p["date"], p["timeSlot"])
        if not av["requested"]["available"]:
            raise DemoError("SLOT_FULL", "Khung giờ đã đầy.", 409, alternatives=av["alternatives"])
        p["confirmationToken"] = av["requested"]["confirmationToken"]
        p["expiresAt"] = (self.store.clock() + timedelta(minutes=10)).isoformat()
        return {
            "proposal": {k: v for k, v in p.items() if k not in ("userId", "confirmationToken")},
            "confirmationToken": p["confirmationToken"],
            "workshop": deepcopy(self.workshop(p["workshopId"])),
        }

    async def create(self, user_id: int, payload: dict, idem_key: str) -> dict:
        if not idem_key or len(idem_key) > 200:
            raise DemoError("INVALID_REQUEST", "Cần Idempotency-Key ổn định.")
        fingerprint = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        async with self.store.booking_lock:
            operation = self.store.operations.get((user_id, idem_key))
            if operation:
                if operation[0] != fingerprint:
                    raise DemoError("IDEMPOTENCY_CONFLICT", "Khóa thao tác đã dùng cho yêu cầu khác.", 409)
                return self.out(self.owned(user_id, operation[1]))
            vid = str(payload["userVehicleId"])
            self.vehicles.owned(user_id, vid)
            tok = self.store.tokens.get(payload["confirmationToken"])
            if not tok or tok["userId"] != user_id or tok["used"]:
                raise DemoError("INVALID_CONFIRMATION_TOKEN", "Token xác nhận không hợp lệ.", 409)
            if tok["expiresAt"] <= self.store.clock():
                raise DemoError("HOLD_EXPIRED", "Token xác nhận đã hết hạn.", 409)
            self.validate_slot(tok["workshopId"], tok["date"], tok["timeSlot"])
            proposal = self.owned_proposal(user_id, payload["proposalId"]) if payload.get("proposalId") else None
            if proposal and (
                proposal["userVehicleId"] != vid
                or any(proposal[k] != tok[k] for k in ("workshopId", "date", "timeSlot"))
            ):
                raise DemoError("INVALID_CONFIRMATION_TOKEN", "Token không khớp đề xuất.", 409)
            if payload.get("quoteId"):
                raise DemoError("QUOTE_EXPIRED", "Demo này chưa hỗ trợ báo giá duyệt.", 409)
            if any(
                b["userVehicleId"] == vid and b["status"] in ("pending", "confirmed", "checked_in", "in_progress")
                for b in self.store.bookings.values()
            ):
                raise DemoError("OPEN_BOOKING_EXISTS", "Xe đã có lịch hẹn đang mở.", 409)
            if self.remaining(tok["workshopId"], tok["date"], tok["timeSlot"]) == 0:
                raise DemoError(
                    "SLOT_FULL",
                    "Khung giờ đã đầy.",
                    409,
                    alternatives=self.availability(user_id, tok["workshopId"], tok["date"], tok["timeSlot"])[
                        "alternatives"
                    ],
                )
            estimate = self.cost.estimate(
                user_id, vid, tok["workshopId"], int(payload["milestoneRef"]) if payload.get("milestoneRef") else None
            )
            bid = str(uuid4())
            b = {
                "bookingId": bid,
                "userId": user_id,
                "userVehicleId": vid,
                "status": "confirmed",
                "confirmationMode": "AUTO",
                "workshopId": tok["workshopId"],
                "bookingDate": tok["date"],
                "timeSlot": tok["timeSlot"],
                "bookingCode": f"EVC-{secrets.token_hex(4).upper()}",
                "estimatedCost": estimate["chargeableTotal"],
                "items": estimate["items"],
                "odoMilestone": estimate["milestone"]["odoMilestoneKm"],
                "proposalId": payload.get("proposalId"),
                "createdAt": self.store.timestamp(),
                "note": payload.get("note"),
                "history": [
                    {
                        "fromStatus": None,
                        "toStatus": "CONFIRMED",
                        "actorType": "OWNER",
                        "source": "BOOKING",
                        "reasonCode": None,
                        "note": None,
                        "at": self.store.timestamp(),
                    }
                ],
            }
            self.store.bookings[bid] = b
            tok["used"] = True
            if proposal:
                confirmation = self.messages.append(
                    proposal["conversationId"],
                    "user",
                    "Xác nhận đặt lịch",
                    refs={"bookingId": bid},
                    replyTo=proposal["sourceMessageId"],
                )
                b["sourceMessageId"] = confirmation["id"]
                b["conversationId"] = proposal["conversationId"]
                self.messages.append(
                    proposal["conversationId"],
                    "assistant",
                    f"Đã đặt lịch. Mã lịch hẹn: {b['bookingCode']}.",
                    refs={"bookingId": bid},
                    replyTo=confirmation["id"],
                )
            self.store.operations[(user_id, idem_key)] = (fingerprint, bid)
            return self.out(b)

    def owned(self, user_id: int, bid: str) -> dict:
        b = self.store.bookings.get(str(bid))
        if not b or b["userId"] != user_id:
            raise DemoError("BOOKING_NOT_FOUND", "Không tìm thấy lịch hẹn.", 404)
        return b

    def out(self, b: dict) -> dict:
        return {
            k: b[k]
            for k in (
                "bookingId",
                "status",
                "confirmationMode",
                "workshopId",
                "bookingDate",
                "timeSlot",
                "bookingCode",
                "estimatedCost",
            )
        } | {
            "workshopName": self.workshop(b["workshopId"])["name"],
            "holdExpiresAt": None,
            "ownerCancelableUntil": None,
            "qrUrl": None,
            "estimateLabel": "Chi phí ước tính",
            "quoteId": None,
        }

    def ticket(self, user_id: int, bid: str) -> dict:
        b = self.owned(user_id, bid)
        v = self.vehicles.owned(user_id, b["userVehicleId"])
        w = self.workshop(b["workshopId"])
        return {
            **self.out(b),
            "workshop": {**deepcopy(w), "phone": None},
            "vehicle": {
                "userVehicleId": v["userVehicleId"],
                "modelName": v["modelName"],
                "plateMasked": v["licensePlate"],
            },
            "appointmentAt": f"{b['bookingDate']}T{b['timeSlot']}+07:00",
            "odoMilestone": b["odoMilestone"],
            "items": [{"itemName": i["itemName"], "covered": i["covered"]} for i in b["items"]],
            "cost": {"amount": b["estimatedCost"], "label": "ESTIMATE", "quoteId": None},
            "documentsToBring": ["Giấy đăng ký xe"],
            "history": deepcopy(b.get("history", [])),
            "actualCost": b.get("actualCost"),
            "allowedActions": [],
            "conversationId": b.get("conversationId"),
            "sourceMessageId": b.get("sourceMessageId"),
        }
