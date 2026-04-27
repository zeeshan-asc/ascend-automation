import os
from collections.abc import AsyncIterator

import pytest
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient

os.environ.setdefault("MONGODB_URI", "mongodb://example.invalid:27017")
os.environ.setdefault("OPENAI_API_KEY", "openai-test-key")
os.environ.setdefault("ASSEMBLYAI_API_KEY", "assemblyai-test-key")
os.environ.setdefault("AUTH_JWT_SECRET", "auth-test-secret")

from app.application.container import AppContainer
from app.config import Settings
from app.main import create_app
from tests.helpers.async_mongomock import FakeMongoManager


def build_test_settings() -> Settings:
    return Settings(
        APP_ENV="test",
        APP_HOST="127.0.0.1",
        APP_PORT=8000,
        APP_BASE_URL="http://testserver",
        LOG_LEVEL="INFO",
        AUTH_JWT_SECRET="auth-test-secret",
        AUTH_ALLOWED_EMAIL_DOMAIN="ascendanalytics.co",
        AUTH_COOKIE_NAME="ascend_access_token",
        AUTH_COOKIE_SECURE=False,
        AUTH_COOKIE_MAX_AGE_SECONDS=315360000,
        AUTH_PASSWORD_HASH_ITERATIONS=1000,
        MONGODB_URI="mongodb://example.invalid:27017",
        MONGODB_DB_NAME="rss_pipeline_test",
        OPENAI_API_KEY="openai-test-key",
        OPENAI_MODEL="gpt-4.1-2025-04-14",
        OPENAI_PROMPT_VERSION="v1.0-test",
        ASSEMBLYAI_API_KEY="assemblyai-test-key",
        ASSEMBLYAI_BASE_URL="https://api.assemblyai.com",
        QUEUE_POLL_INTERVAL_SECONDS=0,
        RUN_HEARTBEAT_SECONDS=1,
        STALE_RUN_SECONDS=1,
        RSS_FETCH_TIMEOUT_SECONDS=1,
        ASSEMBLYAI_POLL_INTERVAL_SECONDS=0,
        ASSEMBLYAI_TIMEOUT_SECONDS=2,
    )


@pytest.fixture
def test_settings() -> Settings:
    return build_test_settings()


@pytest.fixture
def mongo_manager() -> FakeMongoManager:
    return FakeMongoManager()


@pytest.fixture
async def app_container(
    test_settings: Settings,
    mongo_manager: FakeMongoManager,
) -> AppContainer:
    return await AppContainer.build(settings=test_settings, mongo_manager=mongo_manager)


@pytest.fixture
async def client(
    test_settings: Settings,
    mongo_manager: FakeMongoManager,
    app_container: AppContainer,
) -> AsyncIterator[AsyncClient]:
    app = create_app(settings=test_settings, mongo_manager=mongo_manager, container=app_container)
    async with LifespanManager(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as http_client:
            yield http_client


@pytest.fixture
def auth_credentials() -> dict[str, str]:
    return {
        "name": "Test User",
        "email": "tester@ascendanalytics.co",
        "password": "Password123!",
    }


@pytest.fixture
async def authenticated_client(
    client: AsyncClient,
    auth_credentials: dict[str, str],
) -> AsyncIterator[AsyncClient]:
    response = await client.post("/api/auth/signup", json=auth_credentials)
    assert response.status_code == 201
    yield client
