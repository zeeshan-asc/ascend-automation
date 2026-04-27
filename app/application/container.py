from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.config import Settings
from app.database import MongoManager
from app.domain.interfaces import (
    EpisodeRepositoryProtocol,
    LeadRepositoryProtocol,
    RunItemRepositoryProtocol,
    RunRepositoryProtocol,
    TranscriptRepositoryProtocol,
)
from app.infrastructure.mongo.episodes import EpisodeRepository
from app.infrastructure.mongo.leads import LeadRepository
from app.infrastructure.mongo.run_items import RunItemRepository
from app.infrastructure.mongo.runs import RunRepository
from app.infrastructure.mongo.transcripts import TranscriptRepository


@dataclass(slots=True)
class AppContainer:
    settings: Settings
    mongo_manager: MongoManager | Any
    run_repository: RunRepositoryProtocol
    episode_repository: EpisodeRepositoryProtocol
    run_item_repository: RunItemRepositoryProtocol
    transcript_repository: TranscriptRepositoryProtocol
    lead_repository: LeadRepositoryProtocol

    @classmethod
    async def build(
        cls,
        *,
        settings: Settings,
        mongo_manager: MongoManager | Any,
    ) -> AppContainer:
        database = mongo_manager.database
        container = cls(
            settings=settings,
            mongo_manager=mongo_manager,
            run_repository=RunRepository(database),
            episode_repository=EpisodeRepository(database),
            run_item_repository=RunItemRepository(database),
            transcript_repository=TranscriptRepository(database),
            lead_repository=LeadRepository(database),
        )
        await container.ensure_indexes()
        return container

    async def ensure_indexes(self) -> None:
        await self.run_repository.ensure_indexes()
        await self.episode_repository.ensure_indexes()
        await self.run_item_repository.ensure_indexes()
        await self.transcript_repository.ensure_indexes()
        await self.lead_repository.ensure_indexes()
