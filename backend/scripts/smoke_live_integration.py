"""Live BE + configured OEM + Redis/Celery + LLM smoke check.

Run from backend/: python scripts/smoke_live_integration.py --user-id 9
Uses the development conversation guard, real DB/services and configured LLM.
Creates a temporary conversation and deletes it on exit. Does not book slots.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx
from redis.asyncio import Redis
from sqlalchemy import func
from sqlmodel import Session, select

from src.common.core.vehicle import UserVehicle, VehicleOdometerReading, VehicleOemSync
from src.config import get_settings
from src.infrastructure.supabase.db import engine
from src.modules.oem_integration.service import as_utc, eligible_vehicle_filter

logging.basicConfig(level=logging.ERROR)


def vehicle_for_owner(user_id: int) -> dict:
    with Session(engine) as db:
        vehicle = db.exec(select(UserVehicle).where(UserVehicle.user_id == user_id, *eligible_vehicle_filter())).first()
        if vehicle is None:
            raise RuntimeError("No eligible linked vehicle for the requested owner")
        return {"id": str(vehicle.id), "external_id": vehicle.external_vehicle_id, "plate": vehicle.license_plate}


def sync_snapshot(vehicle_id: str) -> dict:
    from uuid import UUID

    with Session(engine) as db:
        vid = UUID(vehicle_id)
        state = db.get(VehicleOemSync, vid)
        odo = db.exec(
            select(func.max(VehicleOdometerReading.odo_km)).where(VehicleOdometerReading.user_vehicle_id == vid)
        ).one()
        return {
            "attempted_at": as_utc(state.last_attempt_at) if state and state.last_attempt_at else None,
            "usage_synced_at": as_utc(state.usage_synced_at) if state and state.usage_synced_at else None,
            "history_synced_at": as_utc(state.service_history_synced_at)
            if state and state.service_history_synced_at
            else None,
            "error": state.last_error_code if state else None,
            "trigger": state.last_trigger.value if state and state.last_trigger else None,
            "current_km": odo,
        }


async def stream_turn(client, conversation_id, headers, content, client_message_id=None) -> dict:
    started = time.perf_counter()
    result = {"client_message_id": client_message_id or str(uuid4()), "events": [], "tools": []}
    tokens = []
    event_name = ""
    async with client.stream(
        "POST",
        f"/api/v1/conversations/{conversation_id}/messages",
        headers=headers,
        json={"clientMessageId": result["client_message_id"], "content": content},
    ) as response:
        result["http_status"] = response.status_code
        if response.status_code != 200:
            result["error"] = (await response.aread()).decode()[:1000]
        else:
            async for line in response.aiter_lines():
                if line.startswith("event:"):
                    event_name = line[6:].strip()
                elif line.startswith("data:"):
                    payload = json.loads(line[5:].strip())
                    result["events"].append(event_name)
                    if event_name == "message.accepted":
                        result["replayed"] = payload.get("replayed", False)
                    elif event_name == "status" and payload.get("tool"):
                        result["tools"].append(payload["tool"])
                    elif event_name == "token":
                        tokens.append(payload.get("delta", ""))
                    elif event_name == "error":
                        result["error"] = payload
                    elif event_name == "message.completed":
                        result["message_id"] = payload["message"]["id"]
                        result["answer"] = payload["message"]["content"]
    result["duration_seconds"] = round(time.perf_counter() - started, 2)
    result["token_events"] = len(tokens)
    result["ok"] = bool(result.get("message_id")) and not result.get("error")
    if "Hệ thống gặp sự cố trong quá trình xử lý" in result.get("answer", ""):
        result["ok"] = False
        result["error"] = "Agent returned its provider/tool failure fallback"
    return result


async def main(user_id: int, output: Path) -> int:
    settings = get_settings()
    if settings.app_env == "production":
        raise RuntimeError("This smoke script requires the development conversation guard")
    report = {
        "started_at": datetime.now(UTC).isoformat(),
        "backend": "http://127.0.0.1:8000",
        "oem": settings.oem_api_base_url,
        "llm_provider": settings.llm_provider,
        "llm_model": getattr(settings, f"{settings.llm_provider}_model", settings.model_name),
        "auth": "development X-User-Id; Firebase login is not exercised",
        "checks": {},
    }
    checks = report["checks"]
    vehicle = await asyncio.to_thread(vehicle_for_owner, user_id)
    report["vehicle_id"] = vehicle["id"]
    redis = Redis.from_url(settings.redis_connection_url)
    conversation_id = None
    stop_probe = asyncio.Event()
    probe = None
    headers = {"X-User-Id": str(user_id)}
    async with httpx.AsyncClient(base_url=report["backend"], timeout=45, trust_env=False) as client:
        try:
            health = await client.get("/health")
            checks["backend_health"] = {"ok": health.status_code == 200, "http_status": health.status_code}
            checks["redis"] = {"ok": bool(await redis.ping())}
            oem_url = settings.oem_api_base_url.rstrip("/")
            oem_health = await client.get(oem_url + "/health")
            checks["oem_health"] = {"ok": oem_health.status_code == 200}
            usage = await client.get(f"{oem_url}/vehicles/{vehicle['external_id']}/usage")
            history = await client.get(f"{oem_url}/vehicles/{vehicle['external_id']}/service-history")
            checks["oem_read"] = {
                "ok": usage.status_code == history.status_code == 200,
                "usage_status": usage.status_code,
                "history_status": history.status_code,
                "current_km": usage.json().get("current_km"),
                "history_records": len(history.json()) if history.status_code == 200 else None,
            }
            if not checks["oem_read"]["ok"]:
                raise RuntimeError("Configured OEM could not return linked vehicle data")

            if settings.uses_static_odometer():
                # OEM_SYNC_MODE=static: no webhook -> Celery pull; the vehicle keeps one
                # seeded ODO and its sync state is marked done.
                snapshot = await asyncio.to_thread(sync_snapshot, vehicle["id"])
                checks["oem_static_odometer"] = {
                    "ok": snapshot["current_km"] is not None and snapshot["usage_synced_at"] is not None,
                    **snapshot,
                }
                if not checks["oem_static_odometer"]["ok"]:
                    raise RuntimeError("Static ODO mode is on but the vehicle has no seeded reading")
                print("Static ODO seeded: PASS", flush=True)
            else:
                # Wait out an existing successful debounce window so this event
                # must schedule a new task instead of reusing an earlier signal.
                debounce_key = f"{settings.redis_key_prefix}:oem:webhook:debounce:{vehicle['id']}"
                for _ in range(44):
                    if not await redis.exists(debounce_key):
                        break
                    await asyncio.sleep(0.25)
                sync_started = datetime.now(UTC)
                delivered = await client.post(
                    oem_url + "/webhooks/test-events",
                    json={
                        "event_type": "vehicle.usage.updated",
                        "vehicle_id": vehicle["external_id"],
                    },
                )
                delivery = delivered.json()
                checks["oem_webhook"] = {
                    "ok": delivered.status_code == 200 and delivery.get("delivered") is True,
                    "http_status": delivered.status_code,
                    "delivery": delivery,
                }
                if not checks["oem_webhook"]["ok"]:
                    raise RuntimeError("OEM could not deliver its signed webhook to the real backend")

                deadline = time.monotonic() + 40
                while time.monotonic() < deadline:
                    snapshot = await asyncio.to_thread(sync_snapshot, vehicle["id"])
                    if (
                        snapshot["usage_synced_at"]
                        and snapshot["history_synced_at"]
                        and snapshot["usage_synced_at"] >= sync_started
                        and snapshot["history_synced_at"] >= sync_started
                        and not snapshot["error"]
                    ):
                        break
                    await asyncio.sleep(1)
                else:
                    raise RuntimeError("The webhook was accepted but its Celery sync did not finish successfully")
                checks["oem_worker_db_sync"] = {"ok": True, **snapshot}
                print("OEM webhook -> Celery -> database: PASS", flush=True)

            response = await client.post(
                "/api/v1/conversations",
                headers=headers,
                json={
                    "userVehicleId": vehicle["id"],
                    "title": f"[SMOKE] Live integration {uuid4().hex[:8]}",
                },
            )
            response.raise_for_status()
            conversation_id = response.json()["data"]["id"]

            async def probe_pages():
                results = {"health": [], "history": [], "errors": []}
                checks["concurrent_pages"] = results
                while not stop_probe.is_set():
                    for name, path in (("health", "/health"), ("history", "/api/v1/conversations?limit=5")):
                        started = time.perf_counter()
                        try:
                            response = await client.get(path, headers=headers, timeout=5)
                            results[name].append(round((time.perf_counter() - started) * 1000, 2))
                            if response.status_code != 200:
                                results["errors"].append({"page": name, "http_status": response.status_code})
                        except httpx.HTTPError as exc:
                            results["errors"].append({"page": name, "error": type(exc).__name__})
                    await asyncio.sleep(0.5)

            probe = asyncio.create_task(probe_pages())
            first_prompt = (
                "Hãy tra cứu số km hiện tại của xe tôi và mốc bảo dưỡng tiếp theo. "
                "Chỉ đọc dữ liệu, chưa tạo đề xuất hoặc đặt lịch."
            )
            first = await stream_turn(client, conversation_id, headers, first_prompt)
            checks["chat_vehicle_maintenance"] = first
            first["km_matches_synced_data"] = str(snapshot["current_km"]) in first.get("answer", "").replace(
                ".", ""
            ).replace(",", "")
            first["ok"] &= first["km_matches_synced_data"] and "get_due_maintenance" in first["tools"]
            print(f"Chat maintenance: {'PASS' if first['ok'] else 'FAIL'} ({first['duration_seconds']}s)", flush=True)

            day = (datetime.now(UTC) + timedelta(days=3)).date().isoformat()
            second = await stream_turn(
                client,
                conversation_id,
                headers,
                f"Chỉ tra cứu, không tạo đề xuất hoặc lịch hẹn: tìm xưởng phù hợp và khung giờ trống vào {day} buổi chiều; "
                "cho biết dự toán chi phí cho mốc bảo dưỡng kế tiếp. Hãy dùng công cụ tra cứu giá và lịch trống.",
            )
            checks["chat_cost_and_slots"] = second
            second["ok"] &= {"estimate_service_cost", "get_available_slots"}.issubset(second["tools"])
            print(f"Chat costs/slots: {'PASS' if second['ok'] else 'FAIL'} ({second['duration_seconds']}s)", flush=True)

            if first.get("message_id"):
                replay = await stream_turn(client, conversation_id, headers, first_prompt, first["client_message_id"])
                replay["ok"] &= replay.get("replayed") is True and replay.get("message_id") == first["message_id"]
                checks["chat_retry"] = replay
        except Exception as exc:  # report diagnostic failures without leaking credentials
            message = str(exc)
            for value in (
                settings.gemini_api_key,
                settings.openai_api_key,
                settings.openrouter_api_key,
                settings.qdrant_api_key,
            ):
                if value:
                    message = message.replace(value, "[REDACTED]")
            report["failure"] = {"type": type(exc).__name__, "message": message[:1200]}
        finally:
            stop_probe.set()
            if probe is not None:
                await probe
                metrics = checks["concurrent_pages"]
                metrics["ok"] = not metrics["errors"]
                for name in ("health", "history"):
                    samples = metrics.pop(name)
                    metrics[name] = {
                        "samples": len(samples),
                        "max_ms": max(samples, default=0),
                        "mean_ms": round(sum(samples) / len(samples), 2) if samples else 0,
                    }
            if conversation_id:
                cleaned = await client.delete(f"/api/v1/conversations/{conversation_id}", headers=headers)
                checks["cleanup_conversation"] = {"ok": cleaned.status_code == 204, "http_status": cleaned.status_code}
            await redis.aclose()
    # Avoid putting a vehicle plate or provider credentials into the artifact.
    serialized = json.dumps(report, ensure_ascii=False, indent=2, default=str)
    if vehicle["plate"]:
        serialized = serialized.replace(vehicle["plate"], "[PLATE]")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(serialized, encoding="utf-8")
    ok = not report.get("failure") and all(check.get("ok") for check in checks.values())
    print(f"Live integration: {'PASS' if ok else 'FAIL'}; report: {output}", flush=True)
    return 0 if ok else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--user-id", type=int, required=True)
    parser.add_argument("--output", type=Path, default=Path("../logs/live-integration-report.json"))
    arguments = parser.parse_args()
    raise SystemExit(asyncio.run(main(arguments.user_id, arguments.output)))
