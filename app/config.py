from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = Field(default="development", alias="APP_ENV")
    app_host: str = Field(default="127.0.0.1", alias="APP_HOST")
    app_port: int = Field(default=8000, alias="APP_PORT")
    app_base_url: str = Field(default="http://127.0.0.1:8000", alias="APP_BASE_URL")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    log_dir: str = Field(default="logs", alias="LOG_DIR")
    auth_jwt_secret: SecretStr = Field(alias="AUTH_JWT_SECRET")
    auth_allowed_email_domain: str = Field(
        default="ascendanalytics.co",
        alias="AUTH_ALLOWED_EMAIL_DOMAIN",
    )
    auth_cookie_name: str = Field(default="ascend_access_token", alias="AUTH_COOKIE_NAME")
    auth_cookie_secure: bool = Field(default=False, alias="AUTH_COOKIE_SECURE")
    auth_cookie_max_age_seconds: int = Field(
        default=315360000,
        alias="AUTH_COOKIE_MAX_AGE_SECONDS",
        ge=1,
    )
    auth_password_hash_iterations: int = Field(
        default=310000,
        alias="AUTH_PASSWORD_HASH_ITERATIONS",
        ge=1000,
    )

    mongodb_uri: str = Field(alias="MONGODB_URI")
    mongodb_db_name: str = Field(default="rss_pipeline", alias="MONGODB_DB_NAME")

    openai_api_key: SecretStr = Field(alias="OPENAI_API_KEY")
    openai_model: str = Field(default="gpt-4.1-2025-04-14", alias="OPENAI_MODEL")
    openai_prompt_version: str = Field(default="v1.0", alias="OPENAI_PROMPT_VERSION")

    assemblyai_api_key: SecretStr = Field(alias="ASSEMBLYAI_API_KEY")
    assemblyai_base_url: str = Field(
        default="https://api.assemblyai.com",
        alias="ASSEMBLYAI_BASE_URL",
    )

    max_episodes_per_run: int = Field(
        default=5,
        alias="MAX_EPISODES_PER_RUN",
        ge=1,
        le=5,
    )
    queue_poll_interval_seconds: int = Field(default=2, alias="QUEUE_POLL_INTERVAL_SECONDS")
    run_heartbeat_seconds: int = Field(default=30, alias="RUN_HEARTBEAT_SECONDS")
    stale_run_seconds: int = Field(default=300, alias="STALE_RUN_SECONDS")
    rss_fetch_timeout_seconds: int = Field(default=10, alias="RSS_FETCH_TIMEOUT_SECONDS")
    assemblyai_poll_interval_seconds: int = Field(
        default=5,
        alias="ASSEMBLYAI_POLL_INTERVAL_SECONDS",
    )
    assemblyai_timeout_seconds: int = Field(default=600, alias="ASSEMBLYAI_TIMEOUT_SECONDS")
    run_worker_concurrency: int = Field(default=3, alias="RUN_WORKER_CONCURRENCY")
    episodes_per_run_concurrency: int = Field(
        default=2,
        alias="EPISODES_PER_RUN_CONCURRENCY",
    )
    assemblyai_max_inflight: int = Field(default=6, alias="ASSEMBLYAI_MAX_INFLIGHT")
    openai_max_inflight: int = Field(default=6, alias="OPENAI_MAX_INFLIGHT")
    dashboard_refresh_seconds: int = Field(default=3, alias="DASHBOARD_REFRESH_SECONDS")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    @property
    def project_root(self) -> Path:
        return Path(__file__).resolve().parent.parent

    @property
    def resolved_log_dir(self) -> Path:
        path = Path(self.log_dir)
        if path.is_absolute():
            return path
        return self.project_root / path


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
