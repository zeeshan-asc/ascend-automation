from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.dependencies import get_dashboard_service
from app.application.dashboard import DashboardQueryService, LeadDetail, PaginatedLeads
from app.domain.errors import ResourceNotFoundError

router = APIRouter(prefix="/api/leads", tags=["leads"])


@router.get("", response_model=PaginatedLeads)
async def list_leads(
    service: Annotated[DashboardQueryService, Depends(get_dashboard_service)],
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    status_filter: str | None = Query(default=None, alias="status"),
    search: str | None = Query(default=None, min_length=1),
) -> PaginatedLeads:
    return await service.list_leads(page=page, limit=limit, status=status_filter, search=search)


@router.get("/{lead_id}", response_model=LeadDetail)
async def get_lead_detail(
    lead_id: str,
    service: Annotated[DashboardQueryService, Depends(get_dashboard_service)],
) -> LeadDetail:
    try:
        return await service.get_lead_detail(lead_id=lead_id)
    except ResourceNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
