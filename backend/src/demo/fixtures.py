"""Deterministic identities, synthetic prices, and a snapshot of OEM VEH-003."""

from uuid import NAMESPACE_URL, uuid5

from .store import DemoStore


def stable_id(name: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"ev-care-demo:{name}"))


WORKSHOP_IDS = [stable_id("workshop-1"), stable_id("workshop-2")]
SLOT_TIMES = ["08:30:00", "10:00:00", "14:00:00", "15:30:00", "16:30:00"]


def seed_store(store: DemoStore) -> None:
    store.rules = [
        {"itemCode": "BRAKE_CHECK", "itemName": "Kiểm tra phanh", "isCoveredByWarranty": False},
        {"itemCode": "BATTERY_CHECK", "itemName": "Kiểm tra pin cao áp", "isCoveredByWarranty": False},
        {"itemCode": "CABIN_FILTER", "itemName": "Thay lọc gió điều hòa", "isCoveredByWarranty": False},
        {"itemCode": "TIRE_INSPECTION", "itemName": "Kiểm tra lốp và áp suất", "isCoveredByWarranty": False},
    ]
    for i, wid in enumerate(WORKSHOP_IDS):
        store.workshops[wid] = {
            "workshopId": wid,
            "name": f"Xưởng demo EV Care {i + 1}",
            "address": ["Thanh Xuân, Hà Nội", "Cầu Giấy, Hà Nội"][i],
            "region": "Hà Nội",
            "distanceKm": None,
            "isPreferred": i == 0,
            "operatingHoursToday": {"isClosed": False, "openTime": "08:00:00", "closeTime": "18:00:00"},
            "availability": None,
        }
        store.prices[wid] = dict(
            zip(
                [r["itemCode"] for r in store.rules],
                [60000, 50000, 250000 + i * 20000, 40000],
                strict=True,
            )
        )


def ensure_user(store: DemoStore, claims: dict) -> dict:
    uid = str(claims["uid"])
    if uid in store.users:
        return store.users[uid]
    user_id = max((user["userId"] for user in store.users.values()), default=0) + 1
    user = {
        "userId": user_id,
        "uid": uid,
        "email": claims.get("email"),
        "displayName": claims.get("name") or "Chủ xe demo",
        "avatarUrl": claims.get("picture"),
        "fullName": claims.get("name") or "Chủ xe demo",
        "accountStatus": "active",
        "roles": ["vehicle_user"],
    }
    store.users[uid] = user
    vehicle_id = stable_id(f"vehicle:{uid}")
    store.vehicles[vehicle_id] = {
        "userVehicleId": vehicle_id,
        "userId": user_id,
        "modelName": "VF6",
        "modelId": "MDL-02",
        "externalVehicleId": "VEH-003",
        "trim": "Eco",
        "licensePlate": "51A-11111",
        "color": "Trắng",
        "odoKm": 38210,
        "lastServiceOdo": 22000,
        "lastServiceDate": "2025-03-20",
        "odoRecordedAt": "2026-10-01T05:35:11.021848+00:00",
        "warranties": [
            {"component": "BATTERY", "startDate": "2024-01-20", "endDate": "2032-01-20", "kmLimit": 160000},
            {"component": "MOTOR", "startDate": "2024-01-20", "endDate": "2029-01-20", "kmLimit": 120000},
            {"component": "CHASSIS", "startDate": "2024-01-20", "endDate": "2027-01-20", "kmLimit": 100000},
            {"component": "ELECTRONICS", "startDate": "2024-01-20", "endDate": "2027-01-20", "kmLimit": 100000},
        ],
        "manufactureDate": "2024-01-20",
        "verified": store.skip_onboarding,
        "active": store.skip_onboarding,
        "snapshotSource": "backend/mock-ev-system/seed-data/ev-mock-dump.json:VEH-003",
    }
    return user
