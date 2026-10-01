"""Health module — HTTP endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Response, status

from .schemas import DependenciesHealth
from .service import check_dependencies

router = APIRouter(prefix="/health", tags=["health"])


@router.get(
    "/dependencies",
    response_model=DependenciesHealth,
    summary="Heartbeat Redis, Qdrant and the database (Supabase)",
    responses={
        status.HTTP_503_SERVICE_UNAVAILABLE: {
            "model": DependenciesHealth,
            "description": "At least one dependency is down",
        },
    },
)
async def dependencies_health(response: Response) -> DependenciesHealth:
    result = await check_dependencies()
    if result.status != "ok":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return result
