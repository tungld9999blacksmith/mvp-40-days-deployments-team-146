from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import quote_plus

from pydantic import AliasChoices, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Single env file for the whole repo (backend, frontend, docker compose).
ROOT_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ROOT_ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # App
    app_name: str = "AI20K Agent"
    app_env: Literal["development", "production", "test"] = "development"
    app_port: int = Field(default=8000, ge=1, le=65535)
    app_host: str = "0.0.0.0"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    # structlog renderer: human-readable colored console output (default) or JSON lines.
    log_json: bool = False
    # Mask / drop secrets and PII (emails, phones, tokens, API keys) in every log output.
    log_redact_pii: bool = True
    # File exports, comma-separated subset of "log,json,csv" ("" = stdout only).
    log_file_formats: str = "log"
    log_dir: str = "logs"
    log_file_max_bytes: int = Field(default=10 * 1024 * 1024, ge=1024)
    log_file_backup_count: int = Field(default=5, ge=0)
    cors_origins: str = "http://localhost:3000"

    # LLM
    openai_api_key: str = ""
    model_name: str = "gpt-4o-mini"
    llm_temperature: float = Field(default=0.7, ge=0.0, le=2.0)

    # LLM providers (standardized interface, see infrastructure/llm/)
    llm_provider: Literal["openai", "anthropic", "gemini", "grok", "deepseek", "openrouter"] = "openai"
    # Empty stage overrides inherit the default provider/model for compatibility.
    llm_orchestrator_provider: Literal["", "openai", "gemini", "openrouter"] = ""
    llm_orchestrator_model: str = ""
    llm_rewrite_provider: Literal["", "openai", "gemini", "openrouter"] = ""
    llm_rewrite_model: str = ""
    llm_rag_provider: Literal["", "openai", "gemini", "openrouter"] = ""
    llm_rag_model: str = ""
    llm_booking_provider: Literal["", "openai", "gemini", "openrouter"] = ""
    llm_booking_model: str = ""
    llm_booking_check_enabled: bool = False
    llm_fallback_provider: Literal["", "gemini"] = ""
    openrouter_api_key: str = ""
    openrouter_model: str = "google/gemini-3.5-flash-lite"
    # Optional role overrides; an unset/blank role keeps OPENROUTER_MODEL.
    openrouter_agent_model: str | None = None
    openrouter_rewrite_model: str | None = None
    openrouter_rag_model: str | None = None
    openrouter_write_model: str | None = None
    # Optional comma-separated provider endpoint preferences. Stage overrides
    # keep Mistral routing separate from a future write model's routing.
    openrouter_endpoint_order: str = ""
    openrouter_agent_endpoint_order: str = ""
    openrouter_rewrite_endpoint_order: str = ""
    openrouter_rag_endpoint_order: str = ""
    openrouter_write_endpoint_order: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_max_tokens: int = Field(default=1024, ge=1)
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-opus-5"
    gemini_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("gemini_api_key", "GEMINI_API_KEY", "google_api_key", "GOOGLE_API_KEY"),
    )
    gemini_model: str = "gemini-3.5-flash-lite"
    grok_api_key: str = ""
    grok_model: str = "grok-4"
    grok_base_url: str = "https://api.x.ai/v1"
    deepseek_api_key: str = ""
    deepseek_model: str = "deepseek-chat"
    deepseek_base_url: str = "https://api.deepseek.com"

    @field_validator("openrouter_agent_model", "openrouter_rewrite_model", "openrouter_rag_model", "openrouter_write_model", mode="before")
    @classmethod
    def normalize_stage_model(cls, value):
        if isinstance(value, str):
            return value.strip() or None
        return value

    def openrouter_model_for_stage(self, stage: Literal["agent", "rewrite", "rag", "write"]) -> str:
        if stage not in {"agent", "rewrite", "rag", "write"}:
            raise ValueError(f"Unknown LLM stage: {stage}")
        return getattr(self, "openrouter_" + stage + "_model") or self.openrouter_model

    def openrouter_endpoints_for_stage(self, stage: Literal["agent", "rewrite", "rag", "write"]) -> tuple[str, ...]:
        self.openrouter_model_for_stage(stage)  # Validate the stage name.
        value = getattr(self, "openrouter_" + stage + "_endpoint_order", "") or self.openrouter_endpoint_order
        return tuple(part.strip() for part in value.split(",") if part.strip())

    # Database
    database_url: str | None = None
    database_host: str = "localhost"
    database_port: int = Field(default=5432, ge=1, le=65535)
    database_name: str = "postgres"
    database_user: str = "postgres"
    database_password: str = ""
    database_sslmode: str = "prefer"
    # Fail fast instead of hanging when the pooler stalls (shared Supabase dev DB).
    database_connect_timeout_seconds: int = Field(default=10, ge=1)
    database_keepalive_idle_seconds: int = Field(default=30, ge=1)

    # Supabase
    supabase_url: str = ""
    supabase_key: str = ""

    # File storage (infrastructure/storage — standardized bucket interface)
    file_storage: Literal["supabase"] = "supabase"
    supabase_storage_bucket: str = "documents"
    storage_signed_url_ttl_seconds: int = Field(default=3600, ge=1)

    # EV manufacturer system (OEM). In dev this points at mock-ev-system.
    oem_api_base_url: str = "http://localhost:8100"
    oem_api_timeout_seconds: float = Field(default=8.0, gt=0)

    # OEM data sync + webhook (FEAT-VEH-001, docs/specs/sprint-2/**/us-017*)
    oem_sync_interval_seconds: int = Field(default=7200, ge=60)  # Q-309: 120 minutes
    # "static": seed one fixed random ODO per vehicle (demo, no OEM pull); "oem": pull
    # from the OEM. Unset: static outside production, always "oem" in production.
    oem_sync_mode: Literal["", "oem", "static"] = ""
    oem_sync_alert_failures: int = Field(default=3, ge=1)  # BR-ENT-437 / Q-312
    oem_webhook_secret: str = ""
    oem_webhook_tolerance_seconds: int = Field(default=300, ge=1)

    # Maintenance due status (FEAT-VEH-001 BR-002, BR-006, BR-009)
    due_soon_km: int = Field(default=500, ge=0)
    due_soon_days: int = Field(default=14, ge=0)
    maintenance_recurring_km: int = Field(default=15_000, ge=1)  # VinFast EV: every 15,000 km / 1 year since 2026-01-01
    maintenance_recurring_months: int = Field(default=12, ge=1)
    odo_stale_days: int = Field(default=30, ge=1)

    # Maintenance reminders + notifications (FEAT-NOTI-001, docs/specs/sprint-2/**/us-021*)
    reminder_default_lead_days: int = Field(default=2, ge=0, le=30)
    reminder_job_hour: int = Field(default=8, ge=0, le=23)
    reminder_max_attempts: int = Field(default=3, ge=1)
    frontend_url: str = ""
    # Main email is explicit; DEMO_EMAIL_MODE never enables sends on main.
    email_mode: Literal["mock", "resend", "off"] = "mock"
    email_from: str = ""
    email_app_url: str = "http://localhost:5173"
    resend_api_key: str = ""
    resend_webhook_secret: str = ""
    email_payload_retention_days: int = Field(default=30, ge=2)
    # Prevent real-email mode from using emulator identities or a demo clock.
    firebase_auth_emulator_host: str = ""
    demo_now: str = ""
    agent_checkpoint_mode: Literal["auto", "memory", "postgres"] = "auto"
    agent_memory_context_mode: Literal["off", "shadow", "on"] = "off"
    agent_memory_input_token_budget: int = Field(default=12000, ge=1000)
    agent_memory_summary_trigger_ratio: float = Field(default=0.75, gt=0, lt=1)
    agent_memory_summary_max_tokens: int = Field(default=1000, ge=100)
    agent_memory_recent_turns: int = Field(default=6, ge=1)
    agent_memory_recall_max_tokens: int = Field(default=500, ge=100)
    agent_memory_context_window: int = Field(default=32768, ge=2000)
    agent_memory_output_reserve: int = Field(default=2048, ge=128)
    agent_memory_read_enabled: bool = False
    agent_memory_write_enabled: bool = False
    # Empty preserves global flag behavior; a nonempty list limits P2 to a canary.
    agent_memory_canary_user_ids: list[int] = Field(default_factory=list)
    agent_memory_preference_retention_days: int = Field(default=180, ge=1)
    agent_memory_retention_enabled: bool = False

    # SMS channel (us-021 BR-506) through eSMS.vn: offered to owners only once
    # ESMS_API_KEY, ESMS_SECRET_KEY and ESMS_BRANDNAME are filled in.
    esms_api_key: str = ""
    esms_secret_key: str = ""
    esms_brandname: str = ""
    esms_sms_type: str = "2"  # 2 = customer care (CSKH) brandname
    esms_unicode: bool = False  # False: diacritics are stripped (cheaper, 160 chars/segment)
    esms_sandbox: bool = False  # True: eSMS accepts the request but sends nothing
    esms_timeout_seconds: float = Field(default=10.0, gt=0)

    # Booking by capacity & location (FEAT-BOOK-001, docs/specs/sprint-3/**/us-029*)
    slot_minutes: int = Field(default=60, ge=1)  # PQ-03
    hold_minutes: int = Field(default=10, ge=1)  # PQ-02 — owner cancel window
    booking_nearby_limit: int = Field(default=5, ge=1, le=10)  # Q-402
    workshop_geo_cache_ttl_seconds: int = Field(default=600, ge=10)  # Redis GEO index TTL
    workshop_geo_candidates: int = Field(default=20, ge=1, le=200)  # GEO candidates before ranking

    # Location search (docs/specs/platform/location-search.api.md §11) — Amazon Location
    # Places v2. GrabMaps data only in ap-southeast-1 / ap-southeast-5.
    location_provider: Literal["aws", "fake"] = "fake"
    aws_location_region: str = "ap-southeast-1"
    aws_location_places_api_key: str = ""
    location_timeout_seconds: float = Field(default=3.0, gt=0, le=30)
    location_suggest_rate_per_minute: int = Field(default=30, ge=1)
    location_detail_rate_per_minute: int = Field(default=20, ge=1)
    location_reverse_radius_meters: int = Field(default=500, ge=1, le=100_000)
    booking_search_horizon_days: int = Field(default=7, ge=1)  # Q-403
    booking_ws_confirm_deadline_hours: int = Field(default=12, ge=1)  # Q-404 (BR-015)
    booking_confirmation_token_ttl_seconds: int = Field(default=600, ge=30)  # card token
    booking_lock_ttl_seconds: int = Field(default=10, ge=1)  # Redis capacity lock (BR-001)

    # Quick booking from the AI assistant (docs/specs/sprint-4/**/us-061*)
    quick_booking_proposal_ttl_minutes: int = Field(default=30, ge=1)  # BR-1508
    quick_booking_min_lead_minutes: int = Field(default=120, ge=0)  # BR-1504
    quick_booking_horizon_days: int = Field(default=14, ge=1)  # BR-1504
    quick_booking_not_due_lead_days: int = Field(default=7, ge=0)  # BR-1504 (NORMAL)
    quick_booking_max_lookahead_days: int = Field(default=60, ge=1)  # EF-1504
    quick_booking_max_workshops: int = Field(default=5, ge=1, le=10)  # BR-1506

    # Booking ticket, reminders actions & reschedule (docs/specs/sprint-3/**/us-033*, us-053*)
    feature_reschedule_enabled: bool = True  # Q-703 — rescheduleMode F6B vs GUIDE
    reschedule_min_lead_minutes: int = Field(default=60, ge=0)  # BR-1206
    reschedule_max_count: int = Field(default=2, ge=0)  # BR-1207
    my_bookings_past_days: int = Field(default=90, ge=1)  # BR-1213
    app_base_url: str = ""  # QR payload base: {APP_BASE_URL}/c/{bookingCode} (BR-1203)
    # BR-1208 — JSON list of documents the owner should bring.
    booking_documents_to_bring: str = '["Giấy đăng ký xe", "Sổ bảo hành / sổ bảo dưỡng", "CCCD của chủ xe"]'

    # 24h appointment reminder job (docs/specs/sprint-3/**/us-033*)
    booking_reminder_lead_hours: int = Field(default=24, ge=1)  # BR-702
    booking_reminder_min_lead_hours: int = Field(default=2, ge=0)  # BR-702, BR-711
    booking_reminder_job_interval_minutes: int = Field(default=15, ge=1)

    # Workshop Board (docs/specs/sprint-3/**/us-037*)
    board_history_days: int = Field(default=30, ge=0)
    board_max_range_days: int = Field(default=7, ge=1)
    no_show_grace_minutes: int = Field(default=30, ge=0)  # BR-806
    slot_block_max_days_ahead: int = Field(default=30, ge=0)  # BR-809

    # Quotes with workshop approval (docs/specs/sprint-3/**/us-049*)
    quote_default_validity_days: int = Field(default=7, ge=1)
    quote_max_validity_days: int = Field(default=30, ge=1)
    quote_draft_refresh_hours: int = Field(default=24, ge=1)  # Q-1104
    quote_draft_ttl_days: int = Field(default=7, ge=1)  # BR-1112 — purge job
    # docs/designs/bao-gia-hai-tang.md — pricing flow of NEW bookings; each booking keeps
    # the flow it was created with (booking.pricing_flow), so switching back is safe.
    quote_flow: Literal["legacy", "two_tier"] = "legacy"
    # Private bucket for photos of extra items (D16); signed URLs only.
    booking_line_photo_bucket: str = "booking-line-photos"
    booking_line_photo_url_ttl_seconds: int = Field(default=600, ge=60)

    # Post-service follow-up (docs/specs/sprint-4/**/us-041*)
    follow_up_delay_hours: int = Field(default=12, ge=0)  # BR-902
    follow_up_response_window_hours: int = Field(default=72, ge=1)  # BR-905
    follow_up_quiet_start_hour: int = Field(default=21, ge=0, le=23)
    follow_up_quiet_end_hour: int = Field(default=8, ge=0, le=23)
    # AI-007 TOOL-702 — classify answers with `llm_provider`; off ⇒ keyword/rating rules only.
    follow_up_llm_classifier_enabled: bool = False

    # Detailed service progress (docs/specs/sprint-4/**/us-057*)
    feature_service_progress_enabled: bool = True

    # Onboarding rules (see docs/specs/sprint-1/entity spec)
    onboarding_retention_days: int = Field(default=15, ge=1)
    vehicle_verify_max_failed_attempts: int = Field(default=5, ge=1)
    consent_policy_version: str = "2026-09"

    # Workshop-owner onboarding (FEAT-AUTH-003, docs/specs/sprint-1/**/us-009*)
    workshop_verify_max_failed_attempts: int = Field(default=5, ge=1)
    # Background retries after an OEM timeout: 5 retries, ~30 minutes in total.
    workshop_verify_retry_delays_seconds: str = "60,120,300,600,720"
    # Consent policy versions currently accepted (managed by the company).
    workshop_consent_policy_versions: str = "WS-2026-09"

    # Workshop-owner auth audit (FEAT-AUTH-004, docs/specs/sprint-1/**/us-013*)
    workshop_auth_event_retention_days: int = Field(default=60, ge=1)

    @property
    def workshop_verify_retry_delays(self) -> list[int]:
        return [int(v) for v in self.workshop_verify_retry_delays_seconds.split(",") if v.strip()]

    @property
    def workshop_consent_policy_version_list(self) -> list[str]:
        return [v.strip() for v in self.workshop_consent_policy_versions.split(",") if v.strip()]

    @model_validator(mode="after")
    def _no_demo_odometer_in_production(self) -> "Settings":
        if self.app_env == "production" and self.oem_sync_mode == "static":
            raise ValueError("OEM_SYNC_MODE=static writes made-up odometer readings; it is not allowed in production")
        return self

    def uses_static_odometer(self) -> bool:
        mode = self.oem_sync_mode or ("oem" if self.app_env == "production" else "static")
        return mode == "static"

    @property
    def sqlalchemy_database_url(self) -> str:
        if self.database_url:
            return self.database_url

        if not self.database_password:
            return "sqlite:///./data/app.db"

        user = quote_plus(self.database_user)
        password = quote_plus(self.database_password)
        database = quote_plus(self.database_name)
        return (
            f"postgresql+psycopg2://{user}:{password}@"
            f"{self.database_host}:{self.database_port}/{database}"
            f"?sslmode={quote_plus(self.database_sslmode)}"
        )

    # Embedding engine (infrastructure/embedding — standardized multi-provider interface)
    embedding_provider: Literal["openai", "openrouter", "gemini", "huggingface", "local"] = "gemini"
    # Vector dimension every store/table is built for. MUST match the chosen
    # embedding model's output size (see infrastructure/embedding/base.py).
    embedding_dimensions: int = Field(default=3072, ge=1)
    embedding_batch_size: int = Field(default=128, ge=1)
    embedding_openai_model: str = "text-embedding-3-small"
    embedding_gemini_model: str = "gemini-embedding-001"
    # OpenRouter /embeddings (OPENROUTER_API_KEY + OPENROUTER_BASE_URL); same model as Gemini by default.
    embedding_openrouter_model: str = "google/gemini-embedding-001"
    huggingface_api_key: str = ""
    embedding_huggingface_model: str = "BAAI/bge-m3"
    # Local sentence-transformers model id (requires the optional dependency).
    embedding_local_model: str = "BAAI/bge-m3"

    # Conversation & Chat (F4 — docs/specs/sprint-2/**/us-025*, platform/conversation-messaging.api.md)
    chat_message_max_chars: int = Field(default=2000, ge=1)
    chat_rate_limit_per_minute: int = Field(default=10, ge=1)
    chat_rate_limit_per_day: int = Field(default=200, ge=1)
    chat_run_timeout_seconds: int = Field(default=30, ge=1)
    # How long a stopped turn may take to clean up before its run lock is released anyway.
    chat_run_cleanup_timeout_seconds: float = Field(default=15, gt=0)
    # Per LLM request; keep well below the turn timeout so a fallback still fits.
    llm_call_timeout_seconds: int = Field(default=10, ge=1)
    chat_run_lock_ttl_seconds: int = Field(default=60, ge=1)
    chat_history_page_size: int = Field(default=50, ge=1, le=100)
    chat_excerpt_max_messages: int = Field(default=20, ge=1)
    chat_retention_days: int = Field(default=180, ge=1)  # PQ-09
    chat_purge_batch: int = Field(default=200, ge=1)
    # Optional message embedding + semantic search (Q-604). Default OFF: gates both
    # TASK-MSG-001 (embed on write) and the per-conversation semantic search.
    conversation_semantic_index_enabled: bool = False
    conversation_ws_auth_timeout_seconds: int = Field(default=5, ge=1)
    conversation_ws_ping_seconds: int = Field(default=25, ge=1)
    conversation_ws_max_per_user: int = Field(default=5, ge=1)

    # Qdrant is the default; Chroma and pgvector remain available as alternatives.
    vector_store: Literal["qdrant", "chroma", "pgvector"] = "qdrant"

    # Vector Store - ChromaDB (HTTP client, used when VECTOR_STORE=chroma)
    chroma_persist_dir: str = "./data/chroma"
    chroma_host: str = "localhost"
    chroma_port: int = Field(default=8000, ge=1, le=65535)
    chroma_user: str = ""
    chroma_password: str = ""

    # Vector Store - Qdrant (Cloud / Local)
    qdrant_url: str = Field(
        default="",
        validation_alias=AliasChoices("qdrant_url", "QDRANT_URL"),
    )
    qdrant_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("qdrant_api_key", "QDRANT_API_KEY"),
    )
    qdrant_collection_name: str = "ev_care_knowledge_base_3072"
    qdrant_prefer_grpc: bool = False

    # Redis (cache, locks, pub/sub, queue, ... — see infrastructure/redis/)
    redis_url: str | None = None
    redis_host: str = "localhost"
    redis_port: int = Field(default=6379, ge=1, le=65535)
    redis_db: int = Field(default=2, ge=0)
    redis_password: str = ""
    redis_max_connections: int = Field(default=50, ge=1)
    redis_key_prefix: str = "p146"
    redis_default_cache_ttl: int = Field(default=300, ge=1)

    @property
    def redis_connection_url(self) -> str:
        if self.redis_url:
            return self.redis_url
        return self._redis_url_for_db(self.redis_db)

    # Celery (broker + result backend). An explicit URL wins; otherwise the URL
    # is built from REDIS_HOST / REDIS_PORT / REDIS_PASSWORD with its own DB.
    redis_broker_url: str | None = None
    redis_backend_url: str | None = None
    celery_broker_db: int = Field(default=0, ge=0)
    celery_backend_db: int = Field(default=1, ge=0)

    @property
    def celery_broker_url(self) -> str:
        return self.redis_broker_url or self._redis_url_for_db(self.celery_broker_db)

    @property
    def celery_backend_url(self) -> str:
        return self.redis_backend_url or self._redis_url_for_db(self.celery_backend_db)

    def _redis_url_for_db(self, db: int) -> str:
        auth = f":{quote_plus(self.redis_password)}@" if self.redis_password else ""
        return f"redis://{auth}{self.redis_host}:{self.redis_port}/{db}"


@lru_cache
def get_settings() -> Settings:
    return Settings()
