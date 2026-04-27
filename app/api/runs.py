from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.dependencies import get_dashboard_service
from app.application.dashboard import (
    DashboardQueryService,
    PaginatedRunItems,
    PaginatedRuns,
    RunDetail,
)
from app.domain.errors import ResourceNotFoundError

router = APIRouter(prefix="/api/runs", tags=["runs"])


@router.get("", response_model=PaginatedRuns)
async def list_runs(
    service: Annotated[DashboardQueryService, Depends(get_dashboard_service)],
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    status_filter: str | None = Query(default=None, alias="status"),
    submitted_by_email: str | None = Query(default=None),
) -> PaginatedRuns:
    return await service.list_runs(
        page=page,
        limit=limit,
        status=status_filter,
        submitted_by_email=submitted_by_email,
    )


@router.get("/{run_id}", response_model=RunDetail)
async def get_run_detail(
    run_id: str,
    service: Annotated[DashboardQueryService, Depends(get_dashboard_service)],
) -> RunDetail:
    try:
        return await service.get_run_detail(run_id=run_id)
    except ResourceNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/{run_id}/items", response_model=PaginatedRunItems)
async def get_run_items(
    run_id: str,
    service: Annotated[DashboardQueryService, Depends(get_dashboard_service)],
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
) -> PaginatedRunItems:
    try:
        return await service.get_run_items(run_id=run_id, page=page, limit=limit)
    except ResourceNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
