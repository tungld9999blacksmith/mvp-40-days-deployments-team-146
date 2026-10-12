"""Read-only usage calculation, gated independently from agent memory/email."""

import logging
from datetime import datetime, timedelta
from time import perf_counter

from sqlalchemy import and_, false
from sqlalchemy.exc import ProgrammingError, SQLAlchemyError
from sqlmodel import Session, select

from src import config as app_config
from src.common.core.notification import UserNotificationSetting
from src.common.core.vehicle import UserVehicle, VehicleOdometerReading
from src.config import Settings
from src.modules.user_vehicle.domain import DueResult

from .domain import Reading, UsageConfig, calculate_forecast, utc
from .schemas import MaintenanceForecast

PERSONALIZATION_POLICY_VERSION = "driving-usage-2026-10-v1"
logger = logging.getLogger(__name__)


def consent_enabled(setting: UserNotificationSetting | None) -> bool:
    return bool(
        setting
        and setting.personalized_reminders_enabled
        and setting.personalization_consent_at
        and setting.personalization_policy_version == PERSONALIZATION_POLICY_VERSION
    )


class VehicleUsageService:
    def __init__(self, db: Session, settings: Settings | None = None):
        self.db, self.settings = db, settings or app_config.get_settings()

    def forecast(self, vehicle: UserVehicle, result: DueResult, now: datetime) -> MaintenanceForecast:
        started = perf_counter()
        out = self._forecast(vehicle, result, now)
        logger.info(
            "forecast_evaluated mode=%s status=%s duration_ms=%.2f",
            self.settings.personalized_reminders_mode_for(vehicle.user_id),
            out.status,
            (perf_counter() - started) * 1000,
        )
        return out

    def _forecast(self, vehicle: UserVehicle, result: DueResult, now: datetime) -> MaintenanceForecast:
        if self.settings.personalized_reminders_mode == "off":
            return MaintenanceForecast(status="DISABLED", calculated_at=utc(now))
        config = UsageConfig(max_daily_km=self.settings.usage_max_daily_km)
        setting, reading = UserNotificationSetting, VehicleOdometerReading
        allowed = and_(
            setting.personalized_reminders_enabled.is_(True),
            setting.personalization_policy_version == PERSONALIZATION_POLICY_VERSION,
            setting.personalization_consent_at.is_not(None),
        )
        history = (
            and_(
                reading.user_vehicle_id == vehicle.id,
                reading.recorded_at >= utc(now) - timedelta(days=config.window_days),
                allowed,
            )
            if not self.settings.uses_static_odometer()
            else false()
        )
        # One statement gates history on fresh consent, including when no rows
        # exist. Select only required columns instead of materializing ORM rows.
        statement = (
            select(
                setting.personalized_reminders_enabled,
                setting.personalization_policy_version,
                setting.personalization_consent_at,
                reading.odo_km,
                reading.recorded_at,
            )
            .select_from(setting)
            .outerjoin(reading, history)
            .where(setting.user_id == vehicle.user_id)
            .order_by(reading.recorded_at.desc())
            .limit(config.max_readings + 1)
        )
        try:
            bind = self.db.get_bind()
            if bind.dialect.name == "postgresql":
                engine = getattr(bind, "engine", bind)
                # Independent, read-only autocommit SELECT: query errors cannot
                # abort the job's write transaction, and no SAVEPOINT round trips.
                read_engine = engine.get_execution_options().get("usage_read_engine")
                read_engine = read_engine or engine.execution_options(isolation_level="AUTOCOMMIT")
                with read_engine.connect() as connection:
                    rows = connection.execute(statement).all()
            else:
                # SQLite fixtures share one connection; preserve pending writes.
                with self.db.begin_nested():
                    rows = self.db.exec(statement).all()
            if not rows or not (rows[0][0] and rows[0][1] == PERSONALIZATION_POLICY_VERSION and rows[0][2]):
                return MaintenanceForecast(status="DISABLED", calculated_at=utc(now))
            if self.settings.uses_static_odometer():
                return MaintenanceForecast(status="UNSUPPORTED_DATA_SOURCE", calculated_at=utc(now))
            readings = [Reading(row[3], row[4]) for row in rows if row[3] is not None]
            if len(readings) > config.max_readings:
                return MaintenanceForecast(status="DATA_LIMIT", calculated_at=utc(now))
            return calculate_forecast(readings, result, now=now, config=config)
        except ProgrammingError:
            # Missing migrations and SQL programming errors must be visible.
            raise
        except (SQLAlchemyError, ArithmeticError, ValueError, TypeError) as exc:
            logger.warning("forecast_failed error_type=%s", type(exc).__name__)
            return MaintenanceForecast(status="CALCULATION_ERROR", calculated_at=utc(now))
