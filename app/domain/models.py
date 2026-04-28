from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, EmailStr, Field, model_validator

from app.domain.enums import (
    LeadStatus,
    OutreachStatus,
    RunItemStatus,
    RunStatus,
    SourceKind,
    TranscriptStatus,
)


def utcnow() -> datetime:
    return datetime.now(UTC)


class DomainModel(BaseModel):
    model_config = ConfigDict(use_enum_values=True)


class SubmissionRequest(DomainModel):
    source_url: AnyHttpUrl
    source_kind: SourceKind = SourceKind.AUTO
    tone_instructions: str | None = Field(default=None, max_length=5000)
    submitted_at: datetime

    @model_validator(mode="before")
    @classmethod
    def normalize_legacy_rss_url(cls, values: Any) -> Any:
        if not isinstance(values, dict):
            return values
        normalized = dict(values)
        if not normalized.get("source_url") and normalized.get("rss_url"):
            normalized["source_url"] = normalized["rss_url"]
        return normalized

    @property
    def rss_url(self) -> AnyHttpUrl:
        return self.source_url


class User(DomainModel):
    user_id: str = Field(default_factory=lambda: str(uuid4()))
    name: str = Field(min_length=1, max_length=200)
    email: EmailStr
    password_hash: str = Field(min_length=1)
    password_salt: str = Field(min_length=1)
    token_version: int = Field(default=1, ge=1)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)

    def to_authenticated_user(self) -> AuthenticatedUser:
        return AuthenticatedUser(
            user_id=self.user_id,
            name=self.name,
            email=self.email,
            created_at=self.created_at,
            updated_at=self.updated_at,
        )


class AuthenticatedUser(DomainModel):
    user_id: str
    name: str
    email: EmailStr
    created_at: datetime
    updated_at: datetime


class TokenClaims(DomainModel):
    sub: str
    email: EmailStr
    name: str
    ver: int = Field(ge=1)
    iat: int = Field(ge=0)


class Run(DomainModel):
    run_id: str = Field(default_factory=lambda: str(uuid4()))
    source_url: str
    source_kind: SourceKind = SourceKind.RSS_FEED
    submitted_by: str
    submitted_by_email: EmailStr
    tone_instructions: str | None = None
    submitted_at: datetime
    status: RunStatus = RunStatus.QUEUED
    worker_id: str | None = None
    heartbeat_at: datetime | None = None
    total_items: int = 0
    completed_items: int = 0
    failed_items: int = 0
    error: str | None = None
    retry_run_item_ids: list[str] | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)

    @model_validator(mode="before")
    @classmethod
    def normalize_legacy_source_fields(cls, values: Any) -> Any:
        if not isinstance(values, dict):
            return values
        normalized = dict(values)
        if not normalized.get("source_url") and normalized.get("rss_url"):
            normalized["source_url"] = normalized["rss_url"]
        normalized.setdefault("source_kind", SourceKind.RSS_FEED.value)
        return normalized

    @property
    def rss_url(self) -> str:
        return self.source_url


class RunSubmitter(DomainModel):
    submitted_by: str
    submitted_by_email: EmailStr
    run_count: int


class ParsedEpisode(DomainModel):
    guid: str | None = None
    title: str
    episode_url: str | None = None
    audio_url: str
    published_at: str | None = None
    source_url: str
    source_kind: SourceKind = SourceKind.RSS_FEED
    dedupe_key: str

    @model_validator(mode="before")
    @classmethod
    def normalize_legacy_feed_url(cls, values: Any) -> Any:
        if not isinstance(values, dict):
            return values
        normalized = dict(values)
        if not normalized.get("source_url") and normalized.get("feed_url"):
            normalized["source_url"] = normalized["feed_url"]
        normalized.setdefault("source_kind", SourceKind.RSS_FEED.value)
        return normalized

    @property
    def feed_url(self) -> str | None:
        if self.source_kind == SourceKind.RSS_FEED:
            return self.source_url
        return None


class Episode(DomainModel):
    episode_id: str = Field(default_factory=lambda: str(uuid4()))
    dedupe_key: str
    title: str
    episode_url: str | None = None
    audio_url: str
    published_at: str | None = None
    source_url: str
    source_kind: SourceKind = SourceKind.RSS_FEED
    processing_owner: str | None = None
    processing_started_at: datetime | None = None
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)

    @model_validator(mode="before")
    @classmethod
    def normalize_legacy_feed_url(cls, values: Any) -> Any:
        if not isinstance(values, dict):
            return values
        normalized = dict(values)
        if not normalized.get("source_url") and normalized.get("feed_url"):
            normalized["source_url"] = normalized["feed_url"]
        normalized.setdefault("source_kind", SourceKind.RSS_FEED.value)
        return normalized

    @property
    def feed_url(self) -> str | None:
        if self.source_kind == SourceKind.RSS_FEED:
            return self.source_url
        return None


class RunItem(DomainModel):
    run_item_id: str = Field(default_factory=lambda: str(uuid4()))
    run_id: str
    episode_id: str
    title: str
    status: RunItemStatus = RunItemStatus.PENDING
    error: str | None = None
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class Transcript(DomainModel):
    transcript_id: str = Field(default_factory=lambda: str(uuid4()))
    episode_id: str
    assemblyai_job_id: str
    status: TranscriptStatus
    text: str | None = None
    provider_metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class TranscriptResult(DomainModel):
    assemblyai_job_id: str
    status: TranscriptStatus
    text: str | None = None
    provider_metadata: dict[str, Any] = Field(default_factory=dict)


class LeadDraft(DomainModel):
    guest_name: str
    guest_company: str
    role: str
    pain_point: str
    memorable_quote: str
    email_subject: str
    email_body: str


class LeadEmailDraft(DomainModel):
    email_subject: str
    email_body: str


class Lead(DomainModel):
    lead_id: str = Field(default_factory=lambda: str(uuid4()))
    run_id: str
    episode_id: str
    guest_name: str
    guest_company: str
    role: str
    pain_point: str
    memorable_quote: str
    email_subject: str
    email_body: str
    prompt_version: str
    model_name: str
    status: LeadStatus = LeadStatus.GENERATED
    outreach_status: OutreachStatus = OutreachStatus.NOT_CONTACTED
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
