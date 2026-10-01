"""Cost-estimate module — domain errors (FEAT-COST-001).

Codes and HTTP statuses follow ``docs/specs/sprint-2/api/us-045-sprint-2-spec.api.md`` §6.
"""

from __future__ import annotations


class CostEstimateError(Exception):
    code: str = "COST_ESTIMATE_ERROR"

    def __init__(self, message: str, *, details: dict | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details


class InvalidRequestError(CostEstimateError):
    code = "INVALID_REQUEST"


class VehicleNotFoundError(CostEstimateError):
    """Missing, foreign, unverified or unlinked vehicle — never reveal which (BR-1008)."""

    code = "VEHICLE_NOT_FOUND"

    def __init__(self) -> None:
        super().__init__("Vehicle was not found.")


class WorkshopNotFoundError(CostEstimateError):
    code = "WORKSHOP_NOT_FOUND"

    def __init__(self) -> None:
        super().__init__("Workshop was not found or is not active.")


class MilestoneNotFoundError(CostEstimateError):
    code = "MILESTONE_NOT_FOUND"

    def __init__(self, valid_milestones: list[int]) -> None:
        super().__init__(
            "The maintenance milestone is not in the schedule of this vehicle.",
            details={"validMilestones": valid_milestones},
        )


class MilestoneRequiredError(CostEstimateError):
    code = "MILESTONE_REQUIRED"

    def __init__(self, valid_milestones: list[int]) -> None:
        super().__init__(
            "The next milestone is unknown. Please choose a milestone.",
            details={"validMilestones": valid_milestones},
        )


class WorkshopRequiredError(CostEstimateError):
    code = "WORKSHOP_REQUIRED"

    def __init__(self) -> None:
        super().__init__("Please choose a workshop or provide a location (EDGE-1005).")


ERROR_STATUS: dict[str, int] = {
    "INVALID_REQUEST": 400,
    "VEHICLE_NOT_FOUND": 404,
    "WORKSHOP_NOT_FOUND": 404,
    "MILESTONE_NOT_FOUND": 422,
    "MILESTONE_REQUIRED": 422,
    "WORKSHOP_REQUIRED": 422,
    "SERVICE_UNAVAILABLE": 503,
}


def status_for(code: str) -> int:
    return ERROR_STATUS.get(code, 400)
