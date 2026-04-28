import io
import logging

import pytest
from pydantic import ValidationError

from app.config import Settings
from app.logging import SensitiveDataFilter, configure_logging


def test_settings_defaults_and_overrides(test_settings: Settings) -> None:
    assert test_settings.app_env == "test"
    assert test_settings.app_base_url == "http://testserver"
    assert test_settings.openai_model == "gpt-4.1-2025-04-14"
    assert test_settings.max_episodes_per_run == 5
    assert test_settings.auth_allowed_email_domain == "ascendanalytics.co"


def test_settings_reject_more_than_five_episodes_per_run() -> None:
    with pytest.raises(ValidationError):
        Settings(
            APP_ENV="test",
            APP_HOST="127.0.0.1",
            APP_PORT=8000,
            APP_BASE_URL="http://testserver",
            LOG_LEVEL="INFO",
            AUTH_JWT_SECRET="auth-test-secret",
            MONGODB_URI="mongodb://example.invalid:27017",
            MONGODB_DB_NAME="rss_pipeline_test",
            OPENAI_API_KEY="openai-test-key",
            OPENAI_MODEL="gpt-4.1-2025-04-14",
            OPENAI_PROMPT_VERSION="v1.0-test",
            ASSEMBLYAI_API_KEY="assemblyai-test-key",
            ASSEMBLYAI_BASE_URL="https://api.assemblyai.com",
            MAX_EPISODES_PER_RUN=6,
        )


@pytest.mark.asyncio
async def test_health_endpoint(authenticated_client) -> None:
    response = await authenticated_client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_root_page_requires_authentication(client) -> None:
    response = await client.get("/", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/auth?next=%2F"


@pytest.mark.asyncio
async def test_auth_page_serves_auth_shell(client) -> None:
    response = await client.get("/auth")
    assert response.status_code == 200
    assert "RSS Automation" in response.text
    assert "Create account" in response.text
    assert "Sign in" in response.text


def test_sensitive_data_filter_redacts_secrets() -> None:
    logger = logging.getLogger("tests.redaction")
    logger.setLevel(logging.INFO)
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    logger.handlers = [handler]
    logger.filters = [SensitiveDataFilter(["secret-value"])]
    logger.propagate = False

    logger.info("payload secret-value should be redacted")

    assert "***REDACTED***" in stream.getvalue()
    assert "secret-value" not in stream.getvalue()


def test_configure_logging_writes_service_log_file(tmp_path) -> None:
    configure_logging(
        "INFO",
        ["another-secret"],
        service_name="test-service",
        log_directory=tmp_path,
    )
    logger = logging.getLogger("tests.file-logging")
    logger.info("workflow another-secret event")

    log_file = tmp_path / "test-service.log"
    assert log_file.exists()
    contents = log_file.read_text(encoding="utf-8")
    assert "[test-service]" in contents
    assert "***REDACTED***" in contents
    assert "another-secret" not in contents
