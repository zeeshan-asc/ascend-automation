from typing import cast

from fastapi import Request

from app.application.container import AppContainer
from app.application.dashboard import DashboardQueryService


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
