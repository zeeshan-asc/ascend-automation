from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, EmailStr, Field

from app.domain.enums import (
    LeadStatus,
    OutreachStatus,
    RunItemStatus,
    RunStatus,
    TranscriptStatus,
)


def utcnow() -> datetime:
    return datetime.now(UTC)


class DomainModel(BaseModel):
    model_config = ConfigDict(use_enum_values=True)


class SubmissionRequest(DomainModel):
    rss_url: AnyHttpUrl
    tone_instructions: str | None = Field(default=None, max_length=5000)
    submitted_at: datetime


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
    rss_url: str
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
    feed_url: str
    dedupe_key: str


class Episode(DomainModel):
    episode_id: str = Field(default_factory=lambda: str(uuid4()))
    dedupe_key: str
    title: str
    episode_url: str | None = None
    audio_url: str
    published_at: str | None = None
    feed_url: str
    processing_owner: str | None = None
    processing_started_at: datetime | None = None
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


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
