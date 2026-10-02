"""
Vehicle module — domain and application exceptions.

Hierarchy:
    ApplicationException  (common base, defined in common/)
      └─ VehicleException (module-level base)
            ├─ VehicleNotFoundError        → 404
            ├─ VehiclePlateAlreadyExists   → 409
            └─ VehicleOwnershipDenied      → 403

Rules:
    - Service layer raises these exceptions instead of returning HTTP responses.
    - The global exception handler (common/exception_handlers.py) translates
      each exception into the appropriate HTTP status code and JSON body.
    - Never import FastAPI, Request, or Response here.
"""


class VehicleException(Exception):
    """Base exception for the vehicle module."""

    pass


class VehicleNotFoundError(VehicleException):
    """Raised when the requested vehicle does not exist."""

    def __init__(self, vehicle_id: str) -> None:
        self.vehicle_id = vehicle_id
        super().__init__(f"Vehicle '{vehicle_id}' not found.")


class VehiclePlateAlreadyExistsError(VehicleException):
    """Raised when a license plate is already registered."""

    def __init__(self, plate: str) -> None:
        self.plate = plate
        super().__init__(f"License plate '{plate}' is already registered.")


class VehicleOwnershipDeniedError(VehicleException):
    """Raised when a user tries to access a vehicle they do not own."""

    def __init__(self, user_id: str, vehicle_id: str) -> None:
        self.user_id = user_id
        self.vehicle_id = vehicle_id
        super().__init__(f"User '{user_id}' is not the owner of vehicle '{vehicle_id}'.")
