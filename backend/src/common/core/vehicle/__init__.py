"""Vehicle domain: vehicles linked to a vehicle-owner account."""

from .user_vehicle import (
    UserVehicle,
    UserVehicleRepository,
    VehicleLinkStatus,
    VehicleVerificationStatus,
    VerificationFailureReason,
)
from .vehicle_odometer_reading import (
    OemSyncTrigger,
    OemUsageSource,
    VehicleOdometerReading,
    VehicleOdometerReadingRepository,
)
from .vehicle_oem_sync import VehicleOemSync, VehicleOemSyncRepository
from .vehicle_service_record import (
    ServiceRecordSource,
    VehicleServiceRecord,
    VehicleServiceRecordRepository,
)

__all__ = [
    "OemSyncTrigger",
    "OemUsageSource",
    "ServiceRecordSource",
    "UserVehicle",
    "UserVehicleRepository",
    "VehicleLinkStatus",
    "VehicleOdometerReading",
    "VehicleOdometerReadingRepository",
    "VehicleOemSync",
    "VehicleOemSyncRepository",
    "VehicleServiceRecord",
    "VehicleServiceRecordRepository",
    "VehicleVerificationStatus",
    "VerificationFailureReason",
]
