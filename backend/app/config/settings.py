"""Central application configuration via pydantic-settings.

All settings are read from environment variables or the local ``.env`` file.
Secrets are never hardcoded or committed.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Core -------------------------------------------------------------
    app_name: str = "AEGIS Security Gateway"
    environment: str = "development"  # development | test | production
    debug: bool = False
    api_prefix: str = "/api"
    log_level: str = "INFO"
    version: str = "0.1.0"

    # --- Database ---------------------------------------------------------
    database_url: str = (
        "postgresql+asyncpg://aegis:aegis@127.0.0.1:5433/aegis"
    )

    # --- Auth / JWT -------------------------------------------------------
    # SECRET_KEY must be set from an environment variable or secrets manager.
    # The default below exists only so the app boots in a local dev environment;
    # startup refuses to run in production with the default value unless
    # AEGIS_ALLOW_INSECURE_SECRET=true is explicitly set.
    secret_key: str = "dev-only-insecure-secret-key-change-me"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    refresh_token_expire_days: int = 7
    token_issuer: str = "aegis"
    allow_insecure_secret: bool = False
    auth_lockout_max_failed: int = 5
    auth_lockout_minutes: int = 15

    # --- Gateway / upstream ----------------------------------------------
    upstream_base_url: str = "http://127.0.0.1:8100"
    upstream_timeout_seconds: float = 30.0
    max_request_body_bytes: int = 5_000_000  # 5 MB
    max_response_body_bytes: int = 10_000_000  # 10 MB
    trust_forwarded_headers: bool = True
    gateway_timeout_seconds: float = 35.0
    gateway_rate_limit_auth_per_min: int = 600
    gateway_rate_limit_anon_per_min: int = 120
    login_rate_limit_per_min: int = 10

    # --- ML ---------------------------------------------------------------
    ml_model_dir: str = str(Path("models"))
    ml_enabled: bool = True
    ml_anomaly_threshold: float = 0.80  # anomaly probability (0..1) cutoff
    ml_train_synthetic_size: int = 20_000
    ml_train_synthetic_seed: int = 42
    ml_max_train_size: int = 100_000

    # --- LLM upstream provider (mock | real) ---------------------------
    llm_provider: str = "mock"  # mock | real
    llm_model: str = ""
    llm_api_key: str = ""
    llm_base_url: str = ""
    llm_timeout_seconds: float = 15.0
    llm_max_tokens: int = 512
    llm_max_input_tokens: int = 4096
    llm_max_output_tokens: int = 512
    llm_max_response_chars: int = 50_000
    llm_max_retries: int = 2
    llm_max_prompt_chars: int = 12_000
    llm_max_concurrent_requests: int = 10
    llm_max_session_requests: int = 50
    llm_max_actor_requests_per_hour: int = 120
    llm_max_tool_call_depth: int = 3
    # --- LLM security analyzer (optional external classifier) ----------
    llm_analyzer_provider: str = "none"  # none | openai
    llm_analyzer_enabled: bool = False
    llm_max_calls_per_minute: int = 20
    llm_fallback_deterministic: bool = True
    # --- LLM cost-abuse controls (USD) -----------------------------------
    llm_price_per_1k_prompt_tokens: float = 0.03
    llm_price_per_1k_completion_tokens: float = 0.06
    llm_daily_budget_usd: float = 10.0
    llm_actor_budget_usd: float = 1.0

    # --- Risk engine ------------------------------------------------------
    risk_low_max: int = 19
    risk_medium_max: int = 49
    risk_high_max: int = 74
    risk_critical_min: int = 75

    # --- Responses --------------------------------------------------------
    auto_block_ip: bool = False  # never auto-block IPs in dev by default
    default_response_mode: str = "mock"  # mock | real

    # --- Event pipeline ---------------------------------------------------
    event_poll_interval_seconds: float = 1.0
    event_batch_size: int = 100
    event_retention_days: int = 30
    correlation_window_seconds: int = 900  # 15 minutes

    # --- CORS -------------------------------------------------------------
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:3000"]

    # --- Geo --------------------------------------------------------------
    geo_enabled: bool = False  # deterministic geo is mocked in dev

    # --- Misc -------------------------------------------------------------
    seed_demo_data: bool = True
    workers: int = 1

    _DEFAULT_SECRET = "dev-only-insecure-secret-key-change-me"

    @field_validator("ml_anomaly_threshold")
    @classmethod
    def _clamp_anomaly_threshold(cls, value: float) -> float:
        return max(0.0, min(1.0, value))

    @model_validator(mode="after")
    def _refuse_default_secret_in_production(self) -> "Settings":
        if (
            self.environment == "production"
            and self.secret_key == self._DEFAULT_SECRET
            and not self.allow_insecure_secret
        ):
            raise ValueError(
                "SECRET_KEY must be overridden in production; set "
                "ALLOW_INSECURE_SECRET=true to override (not recommended)"
            )
        return self

    # --- Derived ----------------------------------------------------------
    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def database_url_sync(self) -> str:
        """A synchronous URL for Alembic / SQLAlchemy engine."""
        return self.database_url.replace("+asyncpg", "+psycopg", 1)


@lru_cache
def get_settings() -> Settings:
    return Settings()
