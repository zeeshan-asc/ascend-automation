from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Protocol

from app.domain.enums import OutreachStatus, RunItemStatus, RunStatus, SourceKind
from app.domain.models import (
    Episode,
    Lead,
    LeadDraft,
    LeadEmailDraft,
    ParsedEpisode,
    Run,
    RunItem,
    RunSubmitter,
    TokenClaims,
    Transcript,
    TranscriptResult,
    User,
)


class RunRepositoryProtocol(Protocol):
    async def ensure_indexes(self) -> None: ...
    async def create(self, run: Run) -> Run: ...
    async def get_by_run_id(self, run_id: str) -> Run | None: ...
    async def list_by_run_ids(self, run_ids: Sequence[str]) -> list[Run]: ...
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
    async def list_submitters(self) -> list[RunSubmitter]: ...
    async def has_active_runs(self) -> bool: ...
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
    async def queue_retry(
        self,
        *,
        run_id: str,
        retry_run_item_ids: Sequence[str],
        now: datetime,
    ) -> Run | None: ...
    async def reclaim_stale(self, *, threshold: datetime, now: datetime) -> list[str]: ...


class EpisodeRepositoryProtocol(Protocol):
    async def ensure_indexes(self) -> None: ...
    async def upsert(self, episode: Episode) -> Episode: ...
    async def get_by_dedupe_key(self, dedupe_key: str) -> Episode | None: ...
    async def get_by_audio_url(self, audio_url: str) -> Episode | None: ...
    async def get_by_episode_id(self, episode_id: str) -> Episode | None: ...
    async def list_by_episode_ids(self, episode_ids: Sequence[str]) -> list[Episode]: ...
    async def count_all(self, *, source_url: str | None = None) -> int: ...
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
        source_url: str | None = None,
    ) -> tuple[list[Episode], int]: ...


class RunItemRepositoryProtocol(Protocol):
    async def ensure_indexes(self) -> None: ...
    async def create_many(self, items: Sequence[RunItem]) -> list[RunItem]: ...
    async def get_by_run_item_id(self, run_item_id: str) -> RunItem | None: ...
    async def get_by_run_and_episode(self, run_id: str, episode_id: str) -> RunItem | None: ...
    async def list_all(self) -> list[RunItem]: ...
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
    async def reset_for_retry(self, *, run_item_id: str, now: datetime) -> RunItem | None: ...


class TranscriptRepositoryProtocol(Protocol):
    async def ensure_indexes(self) -> None: ...
    async def create(self, transcript: Transcript) -> Transcript: ...
    async def get_by_episode_id(self, episode_id: str) -> Transcript | None: ...
    async def get_status_by_episode_id(self, episode_id: str) -> str | None: ...
    async def get_text_by_episode_id(self, episode_id: str) -> str | None: ...
    async def list_existing_episode_ids(self, episode_ids: Sequence[str]) -> set[str]: ...


class LeadRepositoryProtocol(Protocol):
    async def ensure_indexes(self) -> None: ...
    async def create(self, lead: Lead) -> Lead: ...
    async def get_by_episode_id(self, episode_id: str) -> Lead | None: ...
    async def get_by_lead_id(self, lead_id: str) -> Lead | None: ...
    async def list_by_episode_ids(self, episode_ids: Sequence[str]) -> list[Lead]: ...
    async def update_outreach_status(
        self,
        *,
        lead_id: str,
        outreach_status: OutreachStatus,
        now: datetime,
    ) -> Lead | None: ...
    async def update_email_draft(
        self,
        *,
        lead_id: str,
        email_subject: str,
        email_body: str,
        now: datetime,
    ) -> Lead | None: ...
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


class SourceResolverProtocol(Protocol):
    async def resolve_source(
        self,
        *,
        source_url: str,
        source_kind: SourceKind,
        max_results: int,
    ) -> list[ParsedEpisode]: ...


class UserRepositoryProtocol(Protocol):
    async def ensure_indexes(self) -> None: ...
    async def create(self, user: User) -> User: ...
    async def get_by_email(self, email: str) -> User | None: ...
    async def get_by_user_id(self, user_id: str) -> User | None: ...
    async def bump_token_version(self, *, user_id: str, now: datetime) -> User | None: ...


class PasswordHasherProtocol(Protocol):
    def hash_password(self, password: str) -> tuple[str, str]: ...
    def verify_password(
        self,
        password: str,
        *,
        password_hash: str,
        password_salt: str,
    ) -> bool: ...


class TokenManagerProtocol(Protocol):
    def issue_token(self, user: User) -> str: ...
    def decode_token(self, token: str) -> TokenClaims: ...


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
    async def rewrite_email_draft(
        self,
        *,
        transcript_text: str,
        current_email_subject: str,
        current_email_body: str,
        user_instruction: str,
    ) -> LeadEmailDraft: ...
