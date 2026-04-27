from __future__ import annotations

import asyncio
import logging
from collections.abc import Mapping

from pymongo import AsyncMongoClient

from app.config import get_settings
from app.logging import configure_logging

TARGET_COLLECTIONS = (
    "runs",
    "episodes",
    "run_items",
    "transcripts",
    "leads",
)

logger = logging.getLogger(__name__)


async def clear_app_database() -> dict[str, int]:
    settings = get_settings()
    configure_logging(
        settings.log_level,
        [
            settings.openai_api_key.get_secret_value(),
            settings.assemblyai_api_key.get_secret_value(),
        ],
        service_name="maintenance",
        log_directory=settings.resolved_log_dir,
    )

    logger.info(
        "database.clear.started database=%s collections=%s",
        settings.mongodb_db_name,
        ",".join(TARGET_COLLECTIONS),
    )
    client: AsyncMongoClient[dict[str, object]] = AsyncMongoClient(settings.mongodb_uri)
    try:
        database = client[settings.mongodb_db_name]
        deleted_counts: dict[str, int] = {}
        for collection_name in TARGET_COLLECTIONS:
            collection = database[collection_name]
            before_count = int(await collection.count_documents({}))
            if before_count:
                result = await collection.delete_many({})
                deleted_counts[collection_name] = int(result.deleted_count)
            else:
                deleted_counts[collection_name] = 0
            logger.info(
                "database.clear.collection collection=%s deleted=%s",
                collection_name,
                deleted_counts[collection_name],
            )
        logger.info("database.clear.completed database=%s", settings.mongodb_db_name)
        return deleted_counts
    finally:
        await client.close()


def format_summary(deleted_counts: Mapping[str, int]) -> str:
    return ", ".join(f"{name}={count}" for name, count in deleted_counts.items())


async def _main() -> None:
    deleted_counts = await clear_app_database()
    print(format_summary(deleted_counts))


if __name__ == "__main__":
    asyncio.run(_main())

