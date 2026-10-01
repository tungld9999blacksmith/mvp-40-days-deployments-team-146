"""Generate a consistent EV data set (owners → vehicles → usage, warranties, claims, service history).

The generator reads the reference data already on the mock (vehicle models, warranty
policies, maintenance schedules, service centers) and the existing ids / VINs / plates,
so the result never collides with what is there and every foreign key resolves.
"""

from __future__ import annotations

import random
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any

LAST_NAMES = ["Nguyễn", "Trần", "Lê", "Phạm", "Hoàng", "Huỳnh", "Phan", "Vũ", "Võ", "Đặng", "Bùi", "Đỗ", "Hồ", "Ngô", "Dương", "Lý"]
MIDDLE_NAMES = ["Văn", "Thị", "Hữu", "Đức", "Minh", "Thanh", "Ngọc", "Quốc", "Gia", "Bảo", "Hoài", "Anh"]
FIRST_NAMES = ["An", "Bình", "Cường", "Dũng", "Giang", "Hà", "Hải", "Hạnh", "Hiếu", "Hoa", "Hùng", "Khánh", "Lan", "Linh", "Long", "Mai", "Nam", "Ngọc", "Phong", "Phúc", "Quân", "Sơn", "Tâm", "Thảo", "Trang", "Tuấn", "Vy", "Yến"]
COLORS = ["Trắng", "Đen", "Xám", "Bạc", "Đỏ", "Xanh dương", "Xanh lá", "Vàng", "Trắng ngọc trai"]
# Plate prefix → province code used in national ids (first 3 digits)
REGIONS = [("30", "001"), ("29", "001"), ("51", "079"), ("59", "079"), ("43", "048"), ("15", "031"), ("92", "049")]
PLATE_SERIES = "ABCDEFGHK"
KM_PER_YEAR = (12_000, 22_000)
REJECT_REASONS = [
    "Hư hỏng do va chạm / tai nạn — không thuộc phạm vi bảo hành.",
    "Xe đã được can thiệp, sửa chữa tại cơ sở không chính hãng.",
    "Mức suy giảm nằm trong phạm vi hao mòn tự nhiên, chưa đạt ngưỡng bảo hành.",
    "Yêu cầu ngoài thời hạn hoặc vượt giới hạn km của hợp đồng bảo hành.",
    "Hư hỏng do ngập nước — không thuộc phạm vi bảo hành.",
]


def _ascii(text: str) -> str:
    text = text.replace("đ", "d").replace("Đ", "D")
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()


def _add_months(d: date, months: int) -> date:
    y, m = divmod(d.month - 1 + months, 12)
    year, month = d.year + y, m + 1
    for day in (d.day, 30, 29, 28):
        try:
            return date(year, month, day)
        except ValueError:
            continue
    raise ValueError(d)


class IdAllocator:
    """Next id per prefix after the highest existing one, keeping the zero padding."""

    def __init__(self, existing: list[str]) -> None:
        self.next: dict[str, int] = {}
        self.width: dict[str, int] = {}
        for value in existing:
            m = re.fullmatch(r"(.*?)(\d+)", value or "")
            if m:
                prefix, num = m.group(1), m.group(2)
                self.next[prefix] = max(self.next.get(prefix, 1), int(num) + 1)
                self.width[prefix] = max(self.width.get(prefix, 0), len(num))

    def new(self, prefix: str, width: int = 3) -> str:
        n = self.next.get(prefix, 1)
        self.next[prefix] = n + 1
        return f"{prefix}{n:0{self.width.get(prefix, width)}d}"


@dataclass
class Reference:
    """What the mock already holds — loaded once before generating."""

    models: list[dict]
    policies: list[dict]
    schedules: list[dict]
    centers: list[dict]
    ids: dict[str, list[str]] = field(default_factory=dict)
    vins: set[str] = field(default_factory=set)
    plates: set[str] = field(default_factory=set)
    emails: set[str] = field(default_factory=set)
    national_ids: set[str] = field(default_factory=set)

    @classmethod
    def load(cls, client: Any) -> "Reference":
        get = client.all_records
        vehicles, owners = get("vehicles"), get("owners")
        ref = cls(get("vehicle_models"), get("warranty_policies"), get("maintenance_schedules"), get("service_centers"))
        ref.ids = {
            "owners": [o["owner_id"] for o in owners],
            "vehicles": [v["vehicle_id"] for v in vehicles],
            "warranties": [w["warranty_id"] for w in get("warranties")],
            "warranty_claims": [c["claim_id"] for c in get("warranty_claims")],
            "service_history": [s["order_id"] for s in get("service_history")],
        }
        ref.vins = {v["vin"] for v in vehicles}
        ref.plates = {v["license_plate"] for v in vehicles}
        ref.emails = {o["email"] for o in owners}
        ref.national_ids = {o["national_id"] for o in owners}
        return ref


@dataclass
class Options:
    owners: int = 5
    vehicles_min: int = 1
    vehicles_max: int = 2
    claim_rate: float = 0.3
    model_ids: list[str] | None = None
    email_domain: str = "example.com"
    today: date = field(default_factory=date.today)


class DataGenerator:
    def __init__(self, ref: Reference, opts: Options, seed: int | None = None) -> None:
        if not ref.models:
            raise ValueError("the mock has no vehicle models — import vehicle_models first")
        if not ref.centers:
            raise ValueError("the mock has no service centers — import service_centers first")
        self.ref = ref
        self.opts = opts
        self.rnd = random.Random(seed)
        self.ids = IdAllocator([i for ids in ref.ids.values() for i in ids])
        self.models = [m for m in ref.models if not opts.model_ids or m["model_id"] in opts.model_ids]
        if not self.models:
            raise ValueError(f"no vehicle model matches {opts.model_ids}")

    # ── public ──────────────────────────────────────────────────────
    def generate(self) -> dict[str, list[dict]]:
        out: dict[str, list[dict]] = {k: [] for k in ("owners", "vehicles", "vehicle_usage", "warranties", "warranty_claims", "service_history")}
        for _ in range(self.opts.owners):
            region = self.rnd.choice(REGIONS)
            owner = self._owner(region)
            out["owners"].append(owner)
            for _ in range(self.rnd.randint(self.opts.vehicles_min, self.opts.vehicles_max)):
                model = self.rnd.choice(self.models)
                vehicle = self._vehicle(owner, model, region)
                usage = self._usage(vehicle)
                warranties = self._warranties(vehicle, model)
                out["vehicles"].append(vehicle)
                out["vehicle_usage"].append(usage)
                out["warranties"].extend(warranties)
                out["warranty_claims"].extend(self._claims(vehicle, warranties))
                out["service_history"].extend(self._service_history(vehicle, model, usage, region))
        return out

    # ── entities ────────────────────────────────────────────────────
    def _owner(self, region: tuple[str, str]) -> dict:
        last, middle, first = self.rnd.choice(LAST_NAMES), self.rnd.choice(MIDDLE_NAMES), self.rnd.choice(FIRST_NAMES)
        base = f"{_ascii(first)}.{_ascii(last)}".lower()
        email = f"{base}@{self.opts.email_domain}"
        n = 1
        while email in self.ref.emails:
            n += 1
            email = f"{base}{n}@{self.opts.email_domain}"
        self.ref.emails.add(email)
        national_id = self._unique(lambda: f"{region[1]}{self.rnd.randint(0, 1)}{self.rnd.randint(60, 99):02d}{self.rnd.randint(0, 999_999):06d}", self.ref.national_ids)
        return {
            "owner_id": self.ids.new("OWN-"),
            "full_name": f"{last} {middle} {first}",
            "phone": f"09{self.rnd.randint(0, 99_999_999):08d}",
            "email": email,
            "national_id": national_id,
        }

    def _vehicle(self, owner: dict, model: dict, region: tuple[str, str]) -> dict:
        year = model["production_year"]
        mfg = date(year, 1, 1) + timedelta(days=self.rnd.randint(0, 364))
        mfg = min(mfg, self.opts.today - timedelta(days=30))
        stem = _ascii(f"{model['model_name']}{model['trim']}{year}").upper().replace(" ", "")[:11]
        vin = self._unique(lambda: f"{stem}{self.rnd.randint(0, 10 ** (17 - len(stem)) - 1):0{17 - len(stem)}d}", self.ref.vins)
        plate = self._unique(lambda: f"{region[0]}{self.rnd.choice(PLATE_SERIES)}-{self.rnd.randint(10_000, 99_999)}", self.ref.plates)
        return {
            "vehicle_id": self.ids.new("VEH-"),
            "vin": vin,
            "model_id": model["model_id"],
            "current_owner_id": owner["owner_id"],
            "color": self.rnd.choice(COLORS),
            "manufacture_date": mfg.isoformat(),
            "license_plate": plate,
        }

    def _usage(self, vehicle: dict) -> dict:
        age_years = max((self.opts.today - date.fromisoformat(vehicle["manufacture_date"])).days / 365, 0.05)
        km = int(age_years * self.rnd.randint(*KM_PER_YEAR))
        soh = round(max(80.0, 100 - age_years * self.rnd.uniform(0.8, 2.0) - km / 100_000), 1)
        return {
            "vehicle_id": vehicle["vehicle_id"],
            "current_km": km,
            "battery_soh": soh,
            "data_source": "telematics" if self.rnd.random() < 0.85 else "manual",
            "last_updated_at": datetime.combine(self.opts.today, datetime.min.time()).replace(hour=8).isoformat(),
        }

    def _warranties(self, vehicle: dict, model: dict) -> list[dict]:
        start = date.fromisoformat(vehicle["manufacture_date"])
        result = []
        for policy in (p for p in self.ref.policies if p["model_id"] == model["model_id"]):
            end = _add_months(start, policy["duration_months"])
            result.append({
                "warranty_id": self.ids.new("WRT-"),
                "vehicle_id": vehicle["vehicle_id"],
                "policy_id": policy["policy_id"],
                "start_date": start.isoformat(),
                "end_date": end.isoformat(),
                "km_limit": policy["km_limit"],
                "status": "active" if end > self.opts.today else "expired",
            })
        return result

    def _claims(self, vehicle: dict, warranties: list[dict]) -> list[dict]:
        if not warranties or self.rnd.random() >= self.opts.claim_rate:
            return []
        warranty = self.rnd.choice(warranties)
        start = date.fromisoformat(warranty["start_date"])
        claim_date = start + timedelta(days=self.rnd.randint(30, max(31, (self.opts.today - start).days)))
        status = self.rnd.choices(["approved", "rejected", "pending"], weights=[4, 4, 2])[0]
        if claim_date > date.fromisoformat(warranty["end_date"]):
            status = "rejected"
        return [{
            "claim_id": self.ids.new("CLM-"),
            "vehicle_id": vehicle["vehicle_id"],
            "warranty_id": warranty["warranty_id"],
            "claim_date": claim_date.isoformat(),
            "status": status,
            "reject_reason": self.rnd.choice(REJECT_REASONS) if status == "rejected" else None,
        }]

    def _service_history(self, vehicle: dict, model: dict, usage: dict, region: tuple[str, str]) -> list[dict]:
        schedules = sorted((s for s in self.ref.schedules if s["model_id"] == model["model_id"]), key=lambda s: s["milestone_km"])
        mfg = date.fromisoformat(vehicle["manufacture_date"])
        days_owned = max((self.opts.today - mfg).days, 1)
        centers = [c for c in self.ref.centers if region[1] in c.get("manager_national_id", "")[:3]] or self.ref.centers
        result = []
        for s in schedules:
            if s["milestone_km"] > usage["current_km"] or self.rnd.random() < 0.15:  # some owners skip a milestone
                continue
            km = s["milestone_km"] + self.rnd.randint(-800, 1_200)
            km = min(km, usage["current_km"])
            served = mfg + timedelta(days=int(days_owned * km / max(usage["current_km"], 1)))
            result.append({
                "order_id": self.ids.new("SH-"),
                "vehicle_id": vehicle["vehicle_id"],
                "service_center_id": self.rnd.choice(centers)["center_id"],
                "service_date": min(served, self.opts.today).isoformat(),
                "km_at_service": km,
                "items_done": s["description"],
                "is_periodic": True,
                "total_cost": self.rnd.choice([0, 150_000, 350_000, 900_000, 1_900_000, 2_500_000]),
            })
        return result

    # ── helpers ─────────────────────────────────────────────────────
    def _unique(self, make: Any, taken: set[str]) -> str:
        for _ in range(1000):
            value = make()
            if value not in taken:
                taken.add(value)
                return value
        raise RuntimeError("could not generate a unique value")
