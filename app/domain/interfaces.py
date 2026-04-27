from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Protocol

from app.domain.enums import RunItemStatus, RunStatus
from app.domain.models import (
    Episode,
    Lead,
    LeadDraft,
    ParsedEpisode,
    Run,
    RunItem,
    Transcript,
    TranscriptResult,
)


class RunRepositoryProtocol(Protocol):
    async def ensure_indexes(self) -> None: ...
    async def create(self, run: Run) -> Run: ...
    async def get_by_run_id(self, run_id: str) -> Run | None: ...
    async def count_all(self) -> int: ...
    async def get_status_counts(self) -> dict[str, int]: ...
    async def list_runs(
        self,
        *,
        page: int,
        limit: int,
        status: str | None = None,
        submitted_by_email: str | None = None,
    ) -> tuple[list[Run], int]: ...
    async def claim_next(self, *, worker_id: str, now: datetime) -> Run | None: ...
    async def mark_running(self, run_id: str, now: datetime) -> Run | None: ...
    async def update_heartbeat(
        self,
        *,
        run_id: str,
        worker_id: str,
        now: datetime,
    ) -> Run | None: ...
    async def update_progress(
        self,
        *,
        run_id: str,
        total_items: int | None = None,
        completed_items: int | None = None,
        failed_items: int | None = None,
        error: str | None = None,
        now: datetime,
    ) -> Run | None: ...
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
    ) -> Run | None: ...
    async def reclaim_stale(self, *, threshold: datetime, now: datetime) -> list[str]: ...


class EpisodeRepositoryProtocol(Protocol):
    async def ensure_indexes(self) -> None: ...
    async def upsert(self, episode: Episode) -> Episode: ...
    async def get_by_dedupe_key(self, dedupe_key: str) -> Episode | None: ...
    async def get_by_episode_id(self, episode_id: str) -> Episode | None: ...
    async def count_all(self, *, feed_url: str | None = None) -> int: ...
    async def claim_processing(
        self,
        *,
        episode_id: str,
        owner: str,
        now: datetime,
        stale_before: datetime,
    ) -> Episode | None: ...
    async def release_processing(self, *, episode_id: str, now: datetime) -> Episode | None: ...
    async def list_episodes(
        self,
        *,
        page: int,
        limit: int,
        feed_url: str | None = None,
    ) -> tuple[list[Episode], int]: ...


class RunItemRepositoryProtocol(Protocol):
    async def ensure_indexes(self) -> None: ...
    async def create_many(self, items: Sequence[RunItem]) -> list[RunItem]: ...
    async def get_by_run_and_episode(self, run_id: str, episode_id: str) -> RunItem | None: ...
    async def list_by_run_id(
        self,
        *,
        run_id: str,
        page: int,
        limit: int,
    ) -> tuple[list[RunItem], int]: ...
    async def list_all_by_run_id(self, run_id: str) -> list[RunItem]: ...
    async def update_status(
        self,
        *,
        run_item_id: str,
        status: RunItemStatus,
        error: str | None = None,
        now: datetime,
    ) -> RunItem | None: ...


class TranscriptRepositoryProtocol(Protocol):
    async def ensure_indexes(self) -> None: ...
    async def create(self, transcript: Transcript) -> Transcript: ...
    async def get_by_episode_id(self, episode_id: str) -> Transcript | None: ...


class LeadRepositoryProtocol(Protocol):
    async def ensure_indexes(self) -> None: ...
    async def create(self, lead: Lead) -> Lead: ...
    async def get_by_episode_id(self, episode_id: str) -> Lead | None: ...
    async def get_by_lead_id(self, lead_id: str) -> Lead | None: ...
    async def count_all(self) -> int: ...
    async def get_status_counts(self) -> dict[str, int]: ...
    async def list_leads(
        self,
        *,
        page: int,
        limit: int,
        status: str | None = None,
        search: str | None = None,
    ) -> tuple[list[Lead], int]: ...


class RSSProviderProtocol(Protocol):
    async def fetch_episodes(self, rss_url: str, max_results: int) -> list[ParsedEpisode]: ...


class AssemblyAIProviderProtocol(Protocol):
    async def submit_transcription(self, audio_url: str) -> str: ...
    async def poll_transcription(self, job_id: str) -> TranscriptResult: ...


class OpenAIProviderProtocol(Protocol):
    @property
    def prompt_version(self) -> str: ...

    @property
    def model(self) -> str: ...

    async def generate_lead_draft(
        self,
        *,
        transcript_text: str,
        tone_instructions: str | None,
    ) -> LeadDraft: ...
