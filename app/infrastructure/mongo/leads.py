from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from pymongo import ReturnDocument

from app.domain.enums import OutreachStatus
from app.domain.models import Lead
from app.infrastructure.mongo.base import MongoRepository


class LeadRepository(MongoRepository[Lead]):
    collection_name = "leads"
    model = Lead

    async def ensure_indexes(self) -> None:
        await self.collection.create_index("lead_id", unique=True)
        await self.collection.create_index("episode_id", unique=True)
        await self.collection.create_index("status")
        await self.collection.create_index("outreach_status")
        await self.collection.create_index("created_at")

    async def create(self, lead: Lead) -> Lead:
        await self.collection.insert_one(self.to_document(lead))
        return lead

    async def get_by_episode_id(self, episode_id: str) -> Lead | None:
        return self.from_document(await self.collection.find_one({"episode_id": episode_id}))

    async def get_by_lead_id(self, lead_id: str) -> Lead | None:
        return self.from_document(await self.collection.find_one({"lead_id": lead_id}))

    async def list_by_episode_ids(self, episode_ids: Sequence[str]) -> list[Lead]:
        if not episode_ids:
            return []
        cursor = self.collection.find({"episode_id": {"$in": episode_ids}})
        return [self.model.model_validate(document) async for document in cursor]

    async def update_outreach_status(
        self,
        *,
        lead_id: str,
        outreach_status: OutreachStatus,
        now: datetime,
    ) -> Lead | None:
        document = await self.collection.find_one_and_update(
            {"lead_id": lead_id},
            {
                "$set": {
                    "outreach_status": str(outreach_status),
                    "updated_at": now,
                }
            },
            return_document=ReturnDocument.AFTER,
        )
        return self.from_document(document)

    async def update_email_draft(
        self,
        *,
        lead_id: str,
        email_subject: str,
        email_body: str,
        now: datetime,
    ) -> Lead | None:
        document = await self.collection.find_one_and_update(
            {"lead_id": lead_id},
            {
                "$set": {
                    "email_subject": email_subject,
                    "email_body": email_body,
                    "updated_at": now,
                }
            },
            return_document=ReturnDocument.AFTER,
        )
        return self.from_document(document)

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

    async def list_leads(
        self,
        *,
        page: int,
        limit: int,
        status: str | None = None,
        search: str | None = None,
    ) -> tuple[list[Lead], int]:
        filters: dict[str, object] = {}
        if status:
            filters["status"] = status
        if search:
            filters["$or"] = [
                {"guest_name": {"$regex": search, "$options": "i"}},
                {"guest_company": {"$regex": search, "$options": "i"}},
            ]
        cursor = (
            self.collection.find(filters)
            .sort("created_at", -1)
            .skip((page - 1) * limit)
            .limit(limit)
        )
        results = [self.model.model_validate(document) async for document in cursor]
        total = await self.collection.count_documents(filters)
        return results, total
