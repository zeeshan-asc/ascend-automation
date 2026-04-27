import logging
from dataclasses import dataclass
from typing import Any

from pymongo import AsyncMongoClient
from pymongo.asynchronous.database import AsyncDatabase

from app.config import Settings

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class MongoContext:
    client: AsyncMongoClient[Any]
    database: AsyncDatabase[Any]


class MongoManager:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client: AsyncMongoClient[Any] | None = None
        self._database: AsyncDatabase[Any] | None = None

    async def initialize(self) -> MongoContext:
        if self._client is None or self._database is None:
            logger.info(
                "mongo.initializing database=%s",
                self._settings.mongodb_db_name,
            )
            self._client = AsyncMongoClient(self._settings.mongodb_uri)
            self._database = self._client[self._settings.mongodb_db_name]
        return MongoContext(client=self._client, database=self._database)

    async def close(self) -> None:
        if self._client is not None:
            logger.info("mongo.closing")
            await self._client.close()
        self._client = None
        self._database = None

    async def ensure_indexes(self) -> None:
        if self._database is None:
            raise RuntimeError("MongoDB is not initialized")
        logger.info("mongo.ensure_indexes collection=runs")
        await self._database["runs"].create_index("run_id", unique=True)
        await self._database["runs"].create_index(
            [("status", 1), ("heartbeat_at", 1), ("submitted_at", -1)],
        )

    @property
    def database(self) -> AsyncDatabase[Any]:
        if self._database is None:
            raise RuntimeError("MongoDB is not initialized")
        return self._database


async def bootstrap_mongo(settings: Settings) -> MongoManager:
    manager = MongoManager(settings)
    await manager.initialize()
    await manager.ensure_indexes()
    return manager
