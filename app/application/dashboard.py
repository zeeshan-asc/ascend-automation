from __future__ import annotations

import asyncio
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.domain.enums import LeadStatus, RunStatus
from app.domain.errors import ResourceNotFoundError
from app.domain.interfaces import (
    EpisodeRepositoryProtocol,
    LeadRepositoryProtocol,
    RunItemRepositoryProtocol,
    RunRepositoryProtocol,
    TranscriptRepositoryProtocol,
)
from app.domain.models import Lead, Run, RunItem


class ApiModel(BaseModel):
    model_config = ConfigDict(use_enum_values=True)


class RunSummary(ApiModel):
    run_id: str
    rss_url: str
    submitted_by: str
    submitted_by_email: str
    submitted_at: datetime
    status: str
    total_items: int
    completed_items: int
    failed_items: int
    error: str | None
    started_at: datetime | None
    completed_at: datetime | None


class LeadSummary(ApiModel):
    lead_id: str
    guest_name: str
    guest_company: str
    role: str
    status: str


class RunItemDetail(ApiModel):
    run_item_id: str
    episode_id: str
    title: str
    status: str
    error: str | None
    episode_url: str | None
    audio_url: str | None
    published_at: str | None
    transcript_ready: bool
    lead: LeadSummary | None


class RunDetail(RunSummary):
    items: list[RunItemDetail]


class EpisodeDetail(ApiModel):
    episode_id: str
    title: str
    episode_url: str | None
    audio_url: str
    published_at: str | None
    feed_url: str
    transcript_text: str | None
    transcript_status: str | None
    lead: LeadSummary | None


class LeadDetail(ApiModel):
    lead_id: str
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
    status: str
    created_at: datetime
    updated_at: datetime


class PaginatedRuns(ApiModel):
    total: int
    page: int
    limit: int
    data: list[RunSummary]


class PaginatedRunItems(ApiModel):
    total: int
    page: int
    limit: int
    data: list[RunItemDetail]


class PaginatedLeads(ApiModel):
    total: int
    page: int
    limit: int
    data: list[LeadDetail]


class SubmitterFilterOption(ApiModel):
    submitted_by: str
    submitted_by_email: str
    run_count: int


class DashboardSubmitters(ApiModel):
    data: list[SubmitterFilterOption]


class DashboardStats(ApiModel):
    total_runs: int
    runs_by_status: dict[str, int]
    total_episodes: int
    total_leads: int
    leads_by_status: dict[str, int]
    recent_runs: list[RunSummary]


class DashboardQueryService:
    def __init__(
        self,
        *,
        run_repository: RunRepositoryProtocol,
        episode_repository: EpisodeRepositoryProtocol,
        run_item_repository: RunItemRepositoryProtocol,
        transcript_repository: TranscriptRepositoryProtocol,
        lead_repository: LeadRepositoryProtocol,
    ) -> None:
        self._run_repository = run_repository
        self._episode_repository = episode_repository
        self._run_item_repository = run_item_repository
        self._transcript_repository = transcript_repository
        self._lead_repository = lead_repository

    async def list_runs(
        self,
        *,
        page: int,
        limit: int,
        status: str | None = None,
        submitted_by_email: str | None = None,
    ) -> PaginatedRuns:
        runs, total = await self._run_repository.list_runs(
            page=page,
            limit=limit,
            status=status,
            submitted_by_email=submitted_by_email,
        )
        return PaginatedRuns(
            total=total,
            page=page,
            limit=limit,
            data=[self._build_run_summary(run) for run in runs],
        )

    async def get_run_detail(self, *, run_id: str) -> RunDetail:
        run = await self._run_repository.get_by_run_id(run_id)
        if run is None:
            raise ResourceNotFoundError(f"Run {run_id} was not found.")
        run_items = await self._run_item_repository.list_all_by_run_id(run_id)
        item_details = await asyncio.gather(
            *(self._build_run_item_detail(run_item) for run_item in run_items),
        )
        return RunDetail(**self._build_run_summary(run).model_dump(), items=item_details)

    async def get_run_items(
        self,
        *,
        run_id: str,
        page: int,
        limit: int,
    ) -> PaginatedRunItems:
        run = await self._run_repository.get_by_run_id(run_id)
        if run is None:
            raise ResourceNotFoundError(f"Run {run_id} was not found.")
        items, total = await self._run_item_repository.list_by_run_id(
            run_id=run_id,
            page=page,
            limit=limit,
        )
        return PaginatedRunItems(
            total=total,
            page=page,
            limit=limit,
            data=await asyncio.gather(*(self._build_run_item_detail(item) for item in items)),
        )

    async def get_episode_detail(self, *, episode_id: str) -> EpisodeDetail:
        episode = await self._episode_repository.get_by_episode_id(episode_id)
        if episode is None:
            raise ResourceNotFoundError(f"Episode {episode_id} was not found.")
        transcript = await self._transcript_repository.get_by_episode_id(episode_id)
        lead = await self._lead_repository.get_by_episode_id(episode_id)
        return EpisodeDetail(
            episode_id=episode.episode_id,
            title=episode.title,
            episode_url=episode.episode_url,
            audio_url=episode.audio_url,
            published_at=episode.published_at,
            feed_url=episode.feed_url,
            transcript_text=transcript.text if transcript else None,
            transcript_status=str(transcript.status) if transcript else None,
            lead=self._build_lead_summary(lead) if lead else None,
        )

    async def list_leads(
        self,
        *,
        page: int,
        limit: int,
        status: str | None = None,
        search: str | None = None,
    ) -> PaginatedLeads:
        leads, total = await self._lead_repository.list_leads(
            page=page,
            limit=limit,
            status=status,
            search=search,
        )
        return PaginatedLeads(
            total=total,
            page=page,
            limit=limit,
            data=[self._build_lead_detail(lead) for lead in leads],
        )

    async def list_submitters(self) -> DashboardSubmitters:
        submitters = await self._run_repository.list_submitters()
        return DashboardSubmitters(
            data=[
                SubmitterFilterOption(
                    submitted_by=submitter.submitted_by,
                    submitted_by_email=str(submitter.submitted_by_email),
                    run_count=submitter.run_count,
                )
                for submitter in submitters
            ]
        )

    async def get_lead_detail(self, *, lead_id: str) -> LeadDetail:
        lead = await self._lead_repository.get_by_lead_id(lead_id)
        if lead is None:
            raise ResourceNotFoundError(f"Lead {lead_id} was not found.")
        return self._build_lead_detail(lead)

    async def get_stats(self) -> DashboardStats:
        total_runs, total_episodes, total_leads = await asyncio.gather(
            self._run_repository.count_all(),
            self._episode_repository.count_all(),
            self._lead_repository.count_all(),
        )
        runs_by_status = {status.value: 0 for status in RunStatus}
        runs_by_status.update(await self._run_repository.get_status_counts())
        leads_by_status = {status.value: 0 for status in LeadStatus}
        leads_by_status.update(await self._lead_repository.get_status_counts())
        recent_runs, _ = await self._run_repository.list_runs(page=1, limit=5)
        return DashboardStats(
            total_runs=total_runs,
            runs_by_status=runs_by_status,
            total_episodes=total_episodes,
            total_leads=total_leads,
            leads_by_status=leads_by_status,
            recent_runs=[self._build_run_summary(run) for run in recent_runs],
        )

    def _build_run_summary(self, run: Run) -> RunSummary:
        return RunSummary(
            run_id=run.run_id,
            rss_url=run.rss_url,
            submitted_by=run.submitted_by,
            submitted_by_email=run.submitted_by_email,
            submitted_at=run.submitted_at,
            status=str(run.status),
            total_items=run.total_items,
            completed_items=run.completed_items,
            failed_items=run.failed_items,
            error=run.error,
            started_at=run.started_at,
            completed_at=run.completed_at,
        )

    async def _build_run_item_detail(self, run_item: RunItem) -> RunItemDetail:
        episode, transcript, lead = await asyncio.gather(
            self._episode_repository.get_by_episode_id(run_item.episode_id),
            self._transcript_repository.get_by_episode_id(run_item.episode_id),
            self._lead_repository.get_by_episode_id(run_item.episode_id),
        )
        return RunItemDetail(
            run_item_id=run_item.run_item_id,
            episode_id=run_item.episode_id,
            title=run_item.title,
            status=str(run_item.status),
            error=run_item.error,
            episode_url=episode.episode_url if episode else None,
            audio_url=episode.audio_url if episode else None,
            published_at=episode.published_at if episode else None,
            transcript_ready=transcript is not None,
            lead=self._build_lead_summary(lead) if lead else None,
        )

    def _build_lead_summary(self, lead: Lead) -> LeadSummary:
        return LeadSummary(
            lead_id=lead.lead_id,
            guest_name=lead.guest_name,
            guest_company=lead.guest_company,
            role=lead.role,
            status=str(lead.status),
        )

    def _build_lead_detail(self, lead: Lead) -> LeadDetail:
        return LeadDetail(
            lead_id=lead.lead_id,
            run_id=lead.run_id,
            episode_id=lead.episode_id,
            guest_name=lead.guest_name,
            guest_company=lead.guest_company,
            role=lead.role,
            pain_point=lead.pain_point,
            memorable_quote=lead.memorable_quote,
            email_subject=lead.email_subject,
            email_body=lead.email_body,
            prompt_version=lead.prompt_version,
            model_name=lead.model_name,
            status=str(lead.status),
            created_at=lead.created_at,
            updated_at=lead.updated_at,
        )
