from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from pymongo import ReturnDocument

from app.domain.enums import RunStatus
from app.domain.models import Run, RunSubmitter
from app.infrastructure.mongo.base import MongoRepository


class RunRepository(MongoRepository[Run]):
    collection_name = "runs"
    model = Run

    async def ensure_indexes(self) -> None:
        await self.collection.create_index("run_id", unique=True)
        await self.collection.create_index("submitted_at")
        await self.collection.create_index([("submitted_by_email", 1), ("submitted_at", -1)])
        await self.collection.create_index(
            [("status", 1), ("heartbeat_at", 1), ("submitted_at", -1)],
        )
        await self.collection.create_index("submitted_by_email")

    async def create(self, run: Run) -> Run:
        await self.collection.insert_one(self.to_document(run))
        return run

    async def get_by_run_id(self, run_id: str) -> Run | None:
        return self.from_document(await self.collection.find_one({"run_id": run_id}))

    async def list_by_run_ids(self, run_ids: Sequence[str]) -> list[Run]:
        if not run_ids:
            return []
        cursor = self.collection.find({"run_id": {"$in": list(run_ids)}})
        return [self.model.model_validate(document) async for document in cursor]

    async def count_all(self) -> int:
        return int(await self.collection.count_documents({}))

    async def get_status_counts(self) -> dict[str, int]:
        pipeline = [
            {"$group": {"_id": "$status", "count": {"$sum": 1}}},
        ]
        counts: dict[str, int] = {}
        cursor = await self.collection.aggregate(pipeline)
        async for row in cursor:
            counts[str(row["_id"])] = int(row["count"])
        return counts

    async def list_runs(
        self,
        *,
        page: int,
        limit: int,
        status: str | None = None,
        submitted_by_email: str | None = None,
    ) -> tuple[list[Run], int]:
        filters: dict[str, object] = {}
        if status:
            filters["status"] = status
        if submitted_by_email:
            filters["submitted_by_email"] = submitted_by_email
        cursor = (
            self.collection.find(filters)
            .sort("submitted_at", -1)
            .skip((page - 1) * limit)
            .limit(limit)
        )
        results = [self.model.model_validate(document) async for document in cursor]
        total = await self.collection.count_documents(filters)
        return results, total

    async def list_submitters(self) -> list[RunSubmitter]:
        pipeline = [
            {"$sort": {"submitted_at": -1}},
            {
                "$group": {
                    "_id": "$submitted_by_email",
                    "submitted_by": {"$first": "$submitted_by"},
                    "submitted_by_email": {"$first": "$submitted_by_email"},
                    "run_count": {"$sum": 1},
                    "submitted_at": {"$first": "$submitted_at"},
                }
            },
            {"$sort": {"submitted_at": -1}},
        ]
        cursor = await self.collection.aggregate(pipeline)
        return [
            RunSubmitter(
                submitted_by=str(document["submitted_by"]),
                submitted_by_email=str(document["submitted_by_email"]),
                run_count=int(document["run_count"]),
            )
            async for document in cursor
        ]

    async def has_active_runs(self) -> bool:
        active_count = int(await self.collection.count_documents(
            {
                "status": {
                    "$in": [
                        RunStatus.QUEUED.value,
                        RunStatus.CLAIMED.value,
                        RunStatus.RUNNING.value,
                    ]
                }
            },
            limit=1,
        ))
        return active_count > 0

    async def claim_next(self, *, worker_id: str, now: datetime) -> Run | None:
        document = await self.collection.find_one_and_update(
            {"status": RunStatus.QUEUED.value},
            {
                "$set": {
                    "status": RunStatus.CLAIMED.value,
                    "worker_id": worker_id,
                    "heartbeat_at": now,
                    "started_at": now,
                    "completed_at": None,
                    "updated_at": now,
                }
            },
            sort=[("submitted_at", 1)],
            return_document=ReturnDocument.AFTER,
        )
        return self.from_document(document)

    async def mark_running(self, run_id: str, now: datetime) -> Run | None:
        document = await self.collection.find_one_and_update(
            {"run_id": run_id, "status": RunStatus.CLAIMED.value},
            {"$set": {"status": RunStatus.RUNNING.value, "updated_at": now, "heartbeat_at": now}},
            return_document=ReturnDocument.AFTER,
        )
        return self.from_document(document)

    async def update_heartbeat(self, *, run_id: str, worker_id: str, now: datetime) -> Run | None:
        document = await self.collection.find_one_and_update(
            {"run_id": run_id, "worker_id": worker_id},
            {"$set": {"heartbeat_at": now, "updated_at": now}},
            return_document=ReturnDocument.AFTER,
        )
        return self.from_document(document)

    async def update_progress(
        self,
        *,
        run_id: str,
        total_items: int | None = None,
        completed_items: int | None = None,
        failed_items: int | None = None,
        error: str | None = None,
        now: datetime,
    ) -> Run | None:
        updates: dict[str, object] = {"updated_at": now}
        if total_items is not None:
            updates["total_items"] = total_items
        if completed_items is not None:
            updates["completed_items"] = completed_items
        if failed_items is not None:
            updates["failed_items"] = failed_items
        if error is not None:
            updates["error"] = error
        document = await self.collection.find_one_and_update(
            {"run_id": run_id},
            {"$set": updates},
            return_document=ReturnDocument.AFTER,
        )
        return self.from_document(document)

    async def finalize(
        self,
        *,
        run_id: str,
        status: RunStatus,
        total_items: int,
        completed_items: int,
        failed_items: int,
        error: str | None,
        now: datetime,
    ) -> Run | None:
        document = await self.collection.find_one_and_update(
            {"run_id": run_id},
            {
                "$set": {
                    "status": status.value,
                    "total_items": total_items,
                    "completed_items": completed_items,
                    "failed_items": failed_items,
                    "error": error,
                    "completed_at": now,
                    "retry_run_item_ids": None,
                    "updated_at": now,
                    "heartbeat_at": now,
                }
            },
            return_document=ReturnDocument.AFTER,
        )
        return self.from_document(document)

    async def queue_retry(
        self,
        *,
        run_id: str,
        retry_run_item_ids: Sequence[str],
        now: datetime,
    ) -> Run | None:
        document = await self.collection.find_one_and_update(
            {"run_id": run_id},
            {
                "$set": {
                    "status": RunStatus.QUEUED.value,
                    "worker_id": None,
                    "heartbeat_at": None,
                    "started_at": None,
                    "completed_at": None,
                    "error": None,
                    "retry_run_item_ids": list(retry_run_item_ids),
                    "updated_at": now,
                }
            },
            return_document=ReturnDocument.AFTER,
        )
        return self.from_document(document)

    async def reclaim_stale(self, *, threshold: datetime, now: datetime) -> list[str]:
        stale_filters = {
            "status": {"$in": [RunStatus.CLAIMED.value, RunStatus.RUNNING.value]},
            "heartbeat_at": {"$lt": threshold},
        }
        stale_runs = [
            self.model.model_validate(document)
            async for document in self.collection.find(stale_filters)
        ]
        reclaimed_run_ids: list[str] = []
        for run in stale_runs:
            await self.collection.update_one(
                {"run_id": run.run_id},
                {
                    "$set": {
                        "status": RunStatus.QUEUED.value,
                        "worker_id": None,
                        "error": "Run reclaimed after stale heartbeat",
                        "updated_at": now,
                    }
                },
            )
            reclaimed_run_ids.append(run.run_id)
        return reclaimed_run_ids
