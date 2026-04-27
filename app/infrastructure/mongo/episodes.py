from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from pymongo import ReturnDocument

from app.domain.models import Episode
from app.infrastructure.mongo.base import MongoRepository


class EpisodeRepository(MongoRepository[Episode]):
    collection_name = "episodes"
    model = Episode

    async def ensure_indexes(self) -> None:
        await self.collection.create_index("episode_id", unique=True)
        await self.collection.create_index("dedupe_key", unique=True)
        await self.collection.create_index("feed_url")

    async def upsert(self, episode: Episode) -> Episode:
        await self.collection.update_one(
            {"dedupe_key": episode.dedupe_key},
            {"$setOnInsert": self.to_document(episode)},
            upsert=True,
        )
        stored = await self.collection.find_one({"dedupe_key": episode.dedupe_key})
        return self.model.model_validate(stored)

    async def get_by_dedupe_key(self, dedupe_key: str) -> Episode | None:
        return self.from_document(await self.collection.find_one({"dedupe_key": dedupe_key}))

    async def get_by_episode_id(self, episode_id: str) -> Episode | None:
        return self.from_document(await self.collection.find_one({"episode_id": episode_id}))

    async def list_by_episode_ids(self, episode_ids: Sequence[str]) -> list[Episode]:
        if not episode_ids:
            return []
        cursor = self.collection.find({"episode_id": {"$in": episode_ids}})
        return [self.model.model_validate(document) async for document in cursor]

    async def count_all(self, *, feed_url: str | None = None) -> int:
        filters: dict[str, object] = {}
        if feed_url:
            filters["feed_url"] = feed_url
        return int(await self.collection.count_documents(filters))

    async def claim_processing(
        self,
        *,
        episode_id: str,
        owner: str,
        now: datetime,
        stale_before: datetime,
    ) -> Episode | None:
        document = await self.collection.find_one_and_update(
            {
                "episode_id": episode_id,
                "$or": [
                    {"processing_owner": None},
                    {"processing_started_at": {"$lt": stale_before}},
                ],
            },
            {
                "$set": {
                    "processing_owner": owner,
                    "processing_started_at": now,
                    "updated_at": now,
                }
            },
            return_document=ReturnDocument.AFTER,
        )
        return self.from_document(document)

    async def release_processing(self, *, episode_id: str, now: datetime) -> Episode | None:
        document = await self.collection.find_one_and_update(
            {"episode_id": episode_id},
            {
                "$set": {
                    "processing_owner": None,
                    "processing_started_at": None,
                    "updated_at": now,
                }
            },
            return_document=ReturnDocument.AFTER,
        )
        return self.from_document(document)

    async def list_episodes(
        self,
        *,
        page: int,
        limit: int,
        feed_url: str | None = None,
    ) -> tuple[list[Episode], int]:
        filters: dict[str, object] = {}
        if feed_url:
            filters["feed_url"] = feed_url
        cursor = (
            self.collection.find(filters)
            .sort("created_at", -1)
            .skip((page - 1) * limit)
            .limit(limit)
        )
        results = [self.model.model_validate(document) async for document in cursor]
        total = await self.collection.count_documents(filters)
        return results, total
