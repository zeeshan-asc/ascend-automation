from __future__ import annotations

from collections.abc import Sequence

from app.domain.models import Transcript
from app.infrastructure.mongo.base import MongoRepository


class TranscriptRepository(MongoRepository[Transcript]):
    collection_name = "transcripts"
    model = Transcript

    async def ensure_indexes(self) -> None:
        await self.collection.create_index("transcript_id", unique=True)
        await self.collection.create_index("episode_id", unique=True)

    async def create(self, transcript: Transcript) -> Transcript:
        await self.collection.insert_one(self.to_document(transcript))
        return transcript

    async def get_by_episode_id(self, episode_id: str) -> Transcript | None:
        return self.from_document(await self.collection.find_one({"episode_id": episode_id}))

    async def get_status_by_episode_id(self, episode_id: str) -> str | None:
        document = await self.collection.find_one(
            {"episode_id": episode_id},
            {"_id": 0, "status": 1},
        )
        if document is None:
            return None
        return str(document["status"])

    async def get_text_by_episode_id(self, episode_id: str) -> str | None:
        document = await self.collection.find_one(
            {"episode_id": episode_id},
            {"_id": 0, "text": 1},
        )
        if document is None:
            return None
        text = document.get("text")
        return str(text) if text is not None else None

    async def list_existing_episode_ids(self, episode_ids: Sequence[str]) -> set[str]:
        if not episode_ids:
            return set()
        cursor = self.collection.find(
            {"episode_id": {"$in": episode_ids}},
            {"_id": 0, "episode_id": 1},
        )
        return {str(document["episode_id"]) async for document in cursor}
