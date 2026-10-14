"""OpenTelemetry setup: traces, metrics and logs -> OTLP/HTTP -> OTel Collector.

One call per process (``setup_telemetry``): the API process at import of
``src.main``, each Celery worker child in ``worker_process_init`` (after fork,
as the SDK requires). Disabled unless ``OTEL_ENABLED=true``, and always under
``APP_ENV=test`` — then nothing is patched and every call here is a no-op.

Export runs on background threads with timeouts: a dead collector costs log
warnings, never a failed request.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass

from opentelemetry import metrics, trace
from opentelemetry._logs import set_logger_provider
from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk._logs import LoggerProvider
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor, LogRecordExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import MetricReader, PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SpanExporter

from src.config import Settings, get_settings

logger = logging.getLogger(__name__)

BACKEND_SERVICE = "ev-care-backend"
WORKER_SERVICE = "ev-care-worker"
# Regexes searched in the request URL: health probes would flood the traces.
EXCLUDED_URLS = "/health$,/api/v1/health"
_EXPORT_TIMEOUT_SECONDS = 10


@dataclass(frozen=True)
class Telemetry:
    tracer_provider: TracerProvider
    meter_provider: MeterProvider
    logger_provider: LoggerProvider

    def shutdown(self) -> None:
        """Flush and stop every provider; safe to call once at process exit."""
        for provider in (self.tracer_provider, self.meter_provider, self.logger_provider):
            try:
                provider.shutdown()
            except Exception:  # noqa: BLE001 — never block shutdown on the exporter
                logger.warning("OpenTelemetry provider shutdown failed", exc_info=True)


_telemetry: Telemetry | None = None


def is_enabled(settings: Settings) -> bool:
    return settings.otel_enabled and settings.app_env != "test"


def build_resource(service_name: str, settings: Settings) -> Resource:
    # Railway sets RAILWAY_GIT_COMMIT_SHA on every deploy -> filter by release in Grafana.
    version = (os.environ.get("RAILWAY_GIT_COMMIT_SHA") or "dev")[:12]
    return Resource.create(
        {
            # No service.namespace: Grafana would turn job="ev-care-backend" into "ns/name".
            "service.name": service_name,
            "service.version": version,
            "deployment.environment": settings.otel_deployment_environment,
        }
    )


def build_telemetry(
    service_name: str,
    settings: Settings,
    *,
    span_exporter: SpanExporter | None = None,
    metric_reader: MetricReader | None = None,
    log_exporter: LogRecordExporter | None = None,
) -> Telemetry:
    """Create the three providers (no global state). Exporters are injectable for tests."""
    endpoint = settings.otel_exporter_otlp_endpoint.rstrip("/")
    resource = build_resource(service_name, settings)

    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(
        BatchSpanProcessor(
            span_exporter or OTLPSpanExporter(endpoint=f"{endpoint}/v1/traces", timeout=_EXPORT_TIMEOUT_SECONDS)
        )
    )

    reader = metric_reader or PeriodicExportingMetricReader(
        OTLPMetricExporter(endpoint=f"{endpoint}/v1/metrics", timeout=_EXPORT_TIMEOUT_SECONDS),
        export_interval_millis=settings.otel_metric_export_interval_ms,
    )
    meter_provider = MeterProvider(resource=resource, metric_readers=[reader])

    logger_provider = LoggerProvider(resource=resource)
    logger_provider.add_log_record_processor(
        BatchLogRecordProcessor(
            log_exporter or OTLPLogExporter(endpoint=f"{endpoint}/v1/logs", timeout=_EXPORT_TIMEOUT_SECONDS)
        )
    )
    return Telemetry(tracer_provider, meter_provider, logger_provider)


def _instrument_libraries(telemetry: Telemetry) -> None:
    """Patch the client libraries once per process (outgoing HTTP, Redis, Celery, DB)."""
    from opentelemetry.instrumentation.celery import CeleryInstrumentor
    from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
    from opentelemetry.instrumentation.redis import RedisInstrumentor
    from opentelemetry.instrumentation.requests import RequestsInstrumentor
    from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

    providers = {"tracer_provider": telemetry.tracer_provider, "meter_provider": telemetry.meter_provider}
    instrumentors = (
        ("httpx", lambda: HTTPXClientInstrumentor().instrument(**providers)),
        ("requests", lambda: RequestsInstrumentor().instrument(**providers)),
        ("redis", lambda: RedisInstrumentor().instrument(**providers)),
        # Producer side (API enqueues) and consumer side (worker runs) share one trace.
        ("celery", lambda: CeleryInstrumentor().instrument(**providers)),
        ("sqlalchemy", lambda: _instrument_sqlalchemy(SQLAlchemyInstrumentor(), providers)),
    )
    for name, instrument in instrumentors:
        try:
            instrument()
        except Exception:  # noqa: BLE001 — one broken instrumentation must not stop the app
            logger.warning("OpenTelemetry instrumentation failed: %s", name, exc_info=True)


def _instrument_sqlalchemy(instrumentor, providers: dict) -> None:
    # The engine is created at import time, before this runs: instrument it directly.
    from src.infrastructure.supabase.db import engine

    instrumentor.instrument(engine=engine, **providers)


def setup_telemetry(service_name: str, settings: Settings | None = None) -> Telemetry | None:
    """Install global providers + library instrumentation; ``None`` when disabled.

    Idempotent: a second call returns the first result.
    """
    global _telemetry
    if _telemetry is not None:
        return _telemetry
    settings = settings or get_settings()
    if not is_enabled(settings):
        return None

    # Stable HTTP semantic conventions (http.server.request.duration in seconds,
    # http.request.method, ...) instead of the legacy names. Read at instrument time.
    os.environ.setdefault("OTEL_SEMCONV_STABILITY_OPT_IN", "http")

    telemetry = build_telemetry(service_name, settings)
    trace.set_tracer_provider(telemetry.tracer_provider)
    metrics.set_meter_provider(telemetry.meter_provider)
    set_logger_provider(telemetry.logger_provider)
    _instrument_libraries(telemetry)
    _telemetry = telemetry
    logger.info(
        "OpenTelemetry enabled: service=%s endpoint=%s environment=%s",
        service_name,
        settings.otel_exporter_otlp_endpoint,
        settings.otel_deployment_environment,
    )
    return telemetry


def log_service_started(service_name: str, settings: Settings | None = None) -> None:
    """One log line per process start (deploy or restart); Grafana alerts on it in Loki.

    Call once logging is configured, so the line reaches the OTLP log handler.
    """
    settings = settings or get_settings()
    logger.info(
        "Service started",
        extra={
            "service": service_name,
            "service_version": (os.environ.get("RAILWAY_GIT_COMMIT_SHA") or "dev")[:12],
            "deployment_environment": settings.otel_deployment_environment,
        },
    )


def get_telemetry() -> Telemetry | None:
    return _telemetry


def instrument_fastapi(app, telemetry: Telemetry | None = None) -> None:
    """Server spans + HTTP metrics for ``app``; no-op when telemetry is off.

    The OTel middleware wraps the whole middleware stack, so CorrelationIdMiddleware
    and AuditLogMiddleware already run inside the request span.
    """
    telemetry = telemetry or _telemetry
    if telemetry is None:
        return
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

    FastAPIInstrumentor.instrument_app(
        app,
        tracer_provider=telemetry.tracer_provider,
        meter_provider=telemetry.meter_provider,
        excluded_urls=EXCLUDED_URLS,
    )


def shutdown_telemetry() -> None:
    global _telemetry
    if _telemetry is not None:
        _telemetry.shutdown()
        _telemetry = None
