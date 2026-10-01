"""
Vehicle module — utility / in-memory repository stub.

This file provides an InMemoryVehicleRepository that implements the
VehicleRepositoryPort interface.  It is used purely for demonstration
and testing purposes — no real database is needed to run this example.

In the full project, the concrete PostgreSQL adapter would live in
    `src/infrastructure/postgres/vehicle_repository.py`
and would be wired in via `dependency.py`.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from src.modules.examples.model import VehicleRepositoryPort


class InMemoryVehicleRepository(VehicleRepositoryPort):
    """
    Simple dict-backed repository for demo / unit-test purposes.

    Thread-safety caveat: this is fine for single-worker dev servers.
    Production code should use a proper database adapter.
    """

    def __init__(self) -> None:
        self._store: Dict[str, dict] = {}

    async def get_by_id(self, vehicle_id: str) -> Optional[dict]:
        return deepcopy(self._store.get(vehicle_id))

    async def get_by_plate(self, plate: str) -> Optional[dict]:
        plate_upper = plate.upper().strip()
        for v in self._store.values():
            if v["license_plate"] == plate_upper:
                return deepcopy(v)
        return None

    async def list_by_owner(
        self, owner_id: str, *, page: int = 1, page_size: int = 20
    ) -> Tuple[List[dict], int]:
        owned = [v for v in self._store.values() if v["owner_id"] == owner_id]
        total = len(owned)

        # Simple pagination
        start = (page - 1) * page_size
        end = start + page_size
        items = [deepcopy(v) for v in owned[start:end]]

        return items, total

    async def create(self, vehicle_data: dict) -> dict:
        record = deepcopy(vehicle_data)
        self._store[record["id"]] = record
        return deepcopy(record)

    async def update(self, vehicle_id: str, updates: dict) -> Optional[dict]:
        if vehicle_id not in self._store:
            return None

        record = self._store[vehicle_id]
        for key, value in updates.items():
            if key in record:
                record[key] = value
        record["updated_at"] = datetime.utcnow()

        return deepcopy(record)

    async def delete(self, vehicle_id: str) -> bool:
        return self._store.pop(vehicle_id, None) is not None
