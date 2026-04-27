from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from pymongo import ReturnDocument

from app.domain.enums import RunItemStatus
from app.domain.models import RunItem
from app.infrastructure.mongo.base import MongoRepository


class RunItemRepository(MongoRepository[RunItem]):
    collection_name = "run_items"
    model = RunItem

    async def ensure_indexes(self) -> None:
        await self.collection.create_index("run_item_id", unique=True)
        await self.collection.create_index([("run_id", 1), ("episode_id", 1)], unique=True)
        await self.collection.create_index("run_id")
        await self.collection.create_index("episode_id")

    async def create_many(self, items: Sequence[RunItem]) -> list[RunItem]:
        if not items:
            return []
        await self.collection.insert_many([self.to_document(item) for item in items], ordered=False)
        return list(items)

    async def get_by_run_item_id(self, run_item_id: str) -> RunItem | None:
        return self.from_document(await self.collection.find_one({"run_item_id": run_item_id}))

    async def get_by_run_and_episode(self, run_id: str, episode_id: str) -> RunItem | None:
        return self.from_document(
            await self.collection.find_one({"run_id": run_id, "episode_id": episode_id}),
        )

    async def list_by_run_id(
        self,
        *,
        run_id: str,
        page: int,
        limit: int,
    ) -> tuple[list[RunItem], int]:
        filters = {"run_id": run_id}
        cursor = (
            self.collection.find(filters)
            .sort("created_at", 1)
            .skip((page - 1) * limit)
            .limit(limit)
        )
        results = [self.model.model_validate(document) async for document in cursor]
        total = await self.collection.count_documents(filters)
        return results, total

    async def list_all(self) -> list[RunItem]:
        cursor = self.collection.find({}).sort("created_at", -1)
        return [self.model.model_validate(document) async for document in cursor]

    async def list_all_by_run_id(self, run_id: str) -> list[RunItem]:
        cursor = self.collection.find({"run_id": run_id}).sort("created_at", 1)
        return [self.model.model_validate(document) async for document in cursor]

    async def update_status(
        self,
        *,
        run_item_id: str,
        status: RunItemStatus,
        error: str | None = None,
        now: datetime,
    ) -> RunItem | None:
        updates: dict[str, object] = {"status": status.value, "updated_at": now}
        if error is not None:
            updates["error"] = error
        document = await self.collection.find_one_and_update(
            {"run_item_id": run_item_id},
            {"$set": updates},
            return_document=ReturnDocument.AFTER,
        )
        return self.from_document(document)

    async def reset_for_retry(self, *, run_item_id: str, now: datetime) -> RunItem | None:
        document = await self.collection.find_one_and_update(
            {"run_item_id": run_item_id},
            {
                "$set": {
                    "status": RunItemStatus.PENDING.value,
                    "error": None,
                    "updated_at": now,
                }
            },
            return_document=ReturnDocument.AFTER,
        )
        return self.from_document(document)
