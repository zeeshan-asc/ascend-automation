from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.dependencies import get_dashboard_service
from app.application.dashboard import (
    DashboardQueryService,
    DashboardStats,
    DashboardSubmitters,
)

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/stats", response_model=DashboardStats)
async def get_dashboard_stats(
    service: Annotated[DashboardQueryService, Depends(get_dashboard_service)],
) -> DashboardStats:
    return await service.get_stats()


@router.get("/submitters", response_model=DashboardSubmitters)
async def get_dashboard_submitters(
    service: Annotated[DashboardQueryService, Depends(get_dashboard_service)],
) -> DashboardSubmitters:
    return await service.list_submitters()
