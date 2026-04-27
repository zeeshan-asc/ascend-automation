from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.dependencies import (
    get_dashboard_service,
    get_lead_rewrite_service,
    get_records_service,
)
from app.application.dashboard import DashboardQueryService, LeadDetail, PaginatedLeads
from app.application.lead_rewrite import (
    LeadRewriteRequest,
    LeadRewriteResult,
    LeadRewriteService,
)
from app.application.records import LeadOutreachState, LeadOutreachUpdate, RecordsWorkspaceService
from app.domain.errors import InvalidOperationError, OpenAIRefusalError, ResourceNotFoundError

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


@router.patch("/{lead_id}/outreach", response_model=LeadOutreachState)
async def update_lead_outreach(
    lead_id: str,
    payload: LeadOutreachUpdate,
    service: Annotated[RecordsWorkspaceService, Depends(get_records_service)],
) -> LeadOutreachState:
    try:
        return await service.update_outreach_status(
            lead_id=lead_id,
            outreach_status=payload.outreach_status,
        )
    except ResourceNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/{lead_id}/rewrite", response_model=LeadRewriteResult)
async def rewrite_lead_email(
    lead_id: str,
    payload: LeadRewriteRequest,
    service: Annotated[LeadRewriteService, Depends(get_lead_rewrite_service)],
) -> LeadRewriteResult:
    try:
        return await service.rewrite_email(lead_id=lead_id, instruction=payload.instruction)
    except ResourceNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except InvalidOperationError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except OpenAIRefusalError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
