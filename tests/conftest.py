import os
from collections.abc import AsyncIterator

import pytest
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient

os.environ.setdefault("MONGODB_URI", "mongodb://example.invalid:27017")
os.environ.setdefault("OPENAI_API_KEY", "openai-test-key")
os.environ.setdefault("ASSEMBLYAI_API_KEY", "assemblyai-test-key")

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
