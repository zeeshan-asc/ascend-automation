from __future__ import annotations

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
