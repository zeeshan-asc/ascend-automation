from __future__ import annotations

import csv
from datetime import UTC, datetime
from io import StringIO

from pydantic import BaseModel, ConfigDict

from app.domain.enums import OutreachStatus
from app.domain.errors import ResourceNotFoundError
from app.domain.interfaces import (
    EpisodeRepositoryProtocol,
    LeadRepositoryProtocol,
    RunItemRepositoryProtocol,
    RunRepositoryProtocol,
)
from app.domain.models import Episode, Lead, Run, RunItem


class ApiModel(BaseModel):
    model_config = ConfigDict(use_enum_values=True)


class LeadRecordRow(ApiModel):
    run_item_id: str
    run_id: str
    run_status: str
    run_item_status: str
    submitted_by: str
    submitted_by_email: str
    submitted_at: datetime
    rss_url: str
    episode_id: str
    episode_title: str
    episode_url: str | None
    audio_url: str | None
    published_at: str | None
    lead_id: str | None
    lead_status: str | None
    outreach_status: str | None
    guest_name: str | None
    guest_company: str | None
    role: str | None
    pain_point: str | None
    memorable_quote: str | None
    email_subject: str | None
    email_body: str | None
    error: str | None


class PaginatedLeadRecords(ApiModel):
    total: int
    page: int
    limit: int
    data: list[LeadRecordRow]


class LeadOutreachUpdate(BaseModel):
    outreach_status: OutreachStatus


class LeadOutreachState(ApiModel):
    lead_id: str
    outreach_status: str
    updated_at: datetime


class RecordsWorkspaceService:
    def __init__(
        self,
        *,
        run_repository: RunRepositoryProtocol,
        episode_repository: EpisodeRepositoryProtocol,
        run_item_repository: RunItemRepositoryProtocol,
        lead_repository: LeadRepositoryProtocol,
    ) -> None:
        self._run_repository = run_repository
        self._episode_repository = episode_repository
        self._run_item_repository = run_item_repository
        self._lead_repository = lead_repository

    async def list_records(
        self,
        *,
        page: int,
        limit: int,
        submitted_by_email: str | None = None,
        outreach_status: str | None = None,
        search: str | None = None,
    ) -> PaginatedLeadRecords:
        rows = await self._load_filtered_rows(
            submitted_by_email=submitted_by_email,
            outreach_status=outreach_status,
            search=search,
        )
        total = len(rows)
        start = (page - 1) * limit
        end = start + limit
        return PaginatedLeadRecords(
            total=total,
            page=page,
            limit=limit,
            data=rows[start:end],
        )

    async def update_outreach_status(
        self,
        *,
        lead_id: str,
        outreach_status: OutreachStatus,
    ) -> LeadOutreachState:
        updated = await self._lead_repository.update_outreach_status(
            lead_id=lead_id,
            outreach_status=outreach_status,
            now=datetime.now(UTC),
        )
        if updated is None:
            raise ResourceNotFoundError(f"Lead {lead_id} was not found.")
        return LeadOutreachState(
            lead_id=updated.lead_id,
            outreach_status=str(updated.outreach_status),
            updated_at=updated.updated_at,
        )

    async def export_records_csv(
        self,
        *,
        submitted_by_email: str | None = None,
        outreach_status: str | None = None,
        search: str | None = None,
    ) -> str:
        rows = await self._load_filtered_rows(
            submitted_by_email=submitted_by_email,
            outreach_status=outreach_status,
            search=search,
        )
        buffer = StringIO()
        writer = csv.writer(buffer)
        writer.writerow(
            [
                "submitted_by",
                "submitted_by_email",
                "submitted_at",
                "rss_url",
                "run_id",
                "run_status",
                "run_item_status",
                "episode_title",
                "episode_url",
                "audio_url",
                "published_at",
                "lead_id",
                "lead_status",
                "outreach_status",
                "guest_name",
                "guest_company",
                "role",
                "pain_point",
                "memorable_quote",
                "email_subject",
                "email_body",
                "error",
            ]
        )
        for row in rows:
            writer.writerow(
                [
                    row.submitted_by,
                    row.submitted_by_email,
                    row.submitted_at.isoformat(),
                    row.rss_url,
                    row.run_id,
                    row.run_status,
                    row.run_item_status,
                    row.episode_title,
                    row.episode_url or "",
                    row.audio_url or "",
                    row.published_at or "",
                    row.lead_id or "",
                    row.lead_status or "",
                    row.outreach_status or "",
                    row.guest_name or "",
                    row.guest_company or "",
                    row.role or "",
                    row.pain_point or "",
                    row.memorable_quote or "",
                    row.email_subject or "",
                    row.email_body or "",
                    row.error or "",
                ]
            )
        return buffer.getvalue()

    async def _load_filtered_rows(
        self,
        *,
        submitted_by_email: str | None,
        outreach_status: str | None,
        search: str | None,
    ) -> list[LeadRecordRow]:
        run_items = await self._run_item_repository.list_all()
        if not run_items:
            return []

        run_ids = sorted({item.run_id for item in run_items})
        episode_ids = sorted({item.episode_id for item in run_items})
        runs = await self._run_repository.list_by_run_ids(run_ids)
        episodes = await self._episode_repository.list_by_episode_ids(episode_ids)
        leads = await self._lead_repository.list_by_episode_ids(episode_ids)

        runs_by_id = {run.run_id: run for run in runs}
        episodes_by_id = {episode.episode_id: episode for episode in episodes}
        leads_by_episode_id = {lead.episode_id: lead for lead in leads}

        rows: list[LeadRecordRow] = []
        for run_item in run_items:
            run = runs_by_id.get(run_item.run_id)
            episode = episodes_by_id.get(run_item.episode_id)
            if run is None or episode is None:
                continue
            lead = leads_by_episode_id.get(run_item.episode_id)
            rows.append(self._build_row(run=run, lead=lead, run_item=run_item, episode=episode))

        filtered_rows = self._apply_filters(
            rows,
            submitted_by_email=submitted_by_email,
            outreach_status=outreach_status,
            search=search,
        )
        return sorted(filtered_rows, key=lambda row: row.submitted_at, reverse=True)

    def _build_row(
        self,
        *,
        run: Run,
        lead: Lead | None,
        run_item: RunItem,
        episode: Episode,
    ) -> LeadRecordRow:
        return LeadRecordRow(
            run_item_id=run_item.run_item_id,
            run_id=run.run_id,
            run_status=str(run.status),
            run_item_status=str(run_item.status),
            submitted_by=run.submitted_by,
            submitted_by_email=str(run.submitted_by_email),
            submitted_at=run.submitted_at,
            rss_url=run.rss_url,
            episode_id=episode.episode_id,
            episode_title=episode.title,
            episode_url=episode.episode_url,
            audio_url=episode.audio_url,
            published_at=episode.published_at,
            lead_id=lead.lead_id if lead else None,
            lead_status=str(lead.status) if lead else None,
            outreach_status=str(lead.outreach_status) if lead else None,
            guest_name=lead.guest_name if lead else None,
            guest_company=lead.guest_company if lead else None,
            role=lead.role if lead else None,
            pain_point=lead.pain_point if lead else None,
            memorable_quote=lead.memorable_quote if lead else None,
            email_subject=lead.email_subject if lead else None,
            email_body=lead.email_body if lead else None,
            error=run_item.error,
        )

    def _apply_filters(
        self,
        rows: list[LeadRecordRow],
        *,
        submitted_by_email: str | None,
        outreach_status: str | None,
        search: str | None,
    ) -> list[LeadRecordRow]:
        filtered = rows
        if submitted_by_email:
            filtered = [
                row
                for row in filtered
                if row.submitted_by_email.casefold() == submitted_by_email.casefold()
            ]
        if outreach_status:
            filtered = [
                row
                for row in filtered
                if row.outreach_status == outreach_status
            ]
        if search:
            needle = search.casefold()
            filtered = [
                row
                for row in filtered
                if any(
                    needle in (value or "").casefold()
                    for value in (
                        row.submitted_by,
                        row.submitted_by_email,
                        row.rss_url,
                        row.episode_title,
                        row.episode_url,
                        row.audio_url,
                        row.guest_name,
                        row.guest_company,
                        row.role,
                        row.email_subject,
                    )
                )
            ]
        return filtered
