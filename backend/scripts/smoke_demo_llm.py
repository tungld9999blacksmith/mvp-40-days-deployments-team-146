"""Opt-in real LLM smoke. No Firebase/browser claim; never prints keys/tokens."""

import asyncio
import json
from uuid import uuid4

from src.demo.chat_service import DemoChatService
from src.demo.dependency import make_services
from src.demo.fixtures import ensure_user


async def main():
    services = make_services()
    user = ensure_user(services.store, {"uid": "cli-smoke"})
    vid = services.vehicles.list(user["userId"])[0]["userVehicleId"]
    conversation = services.messages.create(user["userId"], vid)
    chat = DemoChatService(services)
    tools = []
    completed = False
    async for event in chat.stream(
        user["userId"],
        conversation["id"],
        "Xe tôi đến hạn bảo dưỡng gì? Hãy tra dữ liệu xe qua tool và nói rõ dữ liệu mock.",
        str(uuid4()),
    ):
        payload = json.loads(event.split("data: ", 1)[1])
        if event.startswith("event: status") and payload.get("tool"):
            tools.append(payload["tool"])
        if event.startswith("event: error"):
            print("FAIL:", payload["code"])
        if event.startswith("event: message.completed"):
            completed = True
    print(
        json.dumps(
            {
                "completed": completed,
                "tools": tools,
                "bookings": len(services.store.bookings),
                "failure": chat.last_failure,
            }
        )
    )
    return 0 if completed and "read_maintenance" in tools else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
