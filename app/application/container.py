from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.config import Settings
from app.database import MongoManager
from app.domain.interfaces import (
    EpisodeRepositoryProtocol,
    LeadRepositoryProtocol,
    OpenAIProviderProtocol,
    PasswordHasherProtocol,
    RunItemRepositoryProtocol,
    RunRepositoryProtocol,
    SourceResolverProtocol,
    TokenManagerProtocol,
    TranscriptRepositoryProtocol,
    UserRepositoryProtocol,
)
from app.infrastructure.jwt_tokens import JWTTokenManager
from app.infrastructure.mongo.episodes import EpisodeRepository
from app.infrastructure.mongo.leads import LeadRepository
from app.infrastructure.mongo.run_items import RunItemRepository
from app.infrastructure.mongo.runs import RunRepository
from app.infrastructure.mongo.transcripts import TranscriptRepository
from app.infrastructure.mongo.users import UserRepository
from app.infrastructure.passwords import PasswordHasher
from app.infrastructure.providers.openai_client import OpenAIProvider
from app.infrastructure.providers.rss import RSSProvider
from app.infrastructure.providers.source_resolver import (
    DirectAudioResolver,
    EpisodePageResolver,
    SourceResolver,
)


@dataclass(slots=True)
class AppContainer:
    settings: Settings
    mongo_manager: MongoManager | Any
    run_repository: RunRepositoryProtocol
    episode_repository: EpisodeRepositoryProtocol
    run_item_repository: RunItemRepositoryProtocol
    transcript_repository: TranscriptRepositoryProtocol
    lead_repository: LeadRepositoryProtocol
    user_repository: UserRepositoryProtocol
    openai_provider: OpenAIProviderProtocol
    source_resolver: SourceResolverProtocol
    password_hasher: PasswordHasherProtocol
    token_manager: TokenManagerProtocol

    @property
    def rss_provider(self) -> SourceResolverProtocol:
        return self.source_resolver

    @rss_provider.setter
    def rss_provider(self, value: SourceResolverProtocol) -> None:
        self.source_resolver = value

    @classmethod
    async def build(
        cls,
        *,
        settings: Settings,
        mongo_manager: MongoManager | Any,
    ) -> AppContainer:
        database = mongo_manager.database
        rss_provider = RSSProvider(timeout_seconds=settings.rss_fetch_timeout_seconds)
        container = cls(
            settings=settings,
            mongo_manager=mongo_manager,
            run_repository=RunRepository(database),
            episode_repository=EpisodeRepository(database),
            run_item_repository=RunItemRepository(database),
            transcript_repository=TranscriptRepository(database),
            lead_repository=LeadRepository(database),
            user_repository=UserRepository(database),
            openai_provider=OpenAIProvider(
                api_key=settings.openai_api_key.get_secret_value(),
                model=settings.openai_model,
                prompt_version=settings.openai_prompt_version,
                max_inflight=settings.openai_max_inflight,
            ),
            source_resolver=SourceResolver(
                rss_resolver=rss_provider,
                direct_audio_resolver=DirectAudioResolver(
                    timeout_seconds=settings.rss_fetch_timeout_seconds,
                ),
                episode_page_resolver=EpisodePageResolver(
                    timeout_seconds=settings.rss_fetch_timeout_seconds,
                ),
            ),
            password_hasher=PasswordHasher(iterations=settings.auth_password_hash_iterations),
            token_manager=JWTTokenManager(secret_key=settings.auth_jwt_secret.get_secret_value()),
        )
        await container.ensure_indexes()
        return container

    async def ensure_indexes(self) -> None:
        await self.run_repository.ensure_indexes()
        await self.episode_repository.ensure_indexes()
        await self.run_item_repository.ensure_indexes()
        await self.transcript_repository.ensure_indexes()
        await self.lead_repository.ensure_indexes()
        await self.user_repository.ensure_indexes()
