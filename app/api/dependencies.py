from typing import cast

from fastapi import Request

from app.application.container import AppContainer
from app.application.dashboard import DashboardQueryService
from app.application.lead_rewrite import LeadRewriteService
from app.application.records import RecordsWorkspaceService


def get_container(request: Request) -> AppContainer:
    return cast(AppContainer, request.app.state.container)


def get_dashboard_service(request: Request) -> DashboardQueryService:
    container = get_container(request)
    return DashboardQueryService(
        run_repository=container.run_repository,
        episode_repository=container.episode_repository,
        run_item_repository=container.run_item_repository,
        transcript_repository=container.transcript_repository,
        lead_repository=container.lead_repository,
    )


def get_records_service(request: Request) -> RecordsWorkspaceService:
    container = get_container(request)
    return RecordsWorkspaceService(
        run_repository=container.run_repository,
        episode_repository=container.episode_repository,
        run_item_repository=container.run_item_repository,
        lead_repository=container.lead_repository,
    )


def get_lead_rewrite_service(request: Request) -> LeadRewriteService:
    container = get_container(request)
    return LeadRewriteService(
        lead_repository=container.lead_repository,
        transcript_repository=container.transcript_repository,
        openai_provider=container.openai_provider,
    )
