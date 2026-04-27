from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response

from app.api.dependencies import get_current_user, get_records_service
from app.application.records import PaginatedLeadRecords, RecordsWorkspaceService

router = APIRouter(
    prefix="/api/records",
    tags=["records"],
    dependencies=[Depends(get_current_user)],
)


@router.get("", response_model=PaginatedLeadRecords)
async def list_records(
    service: Annotated[RecordsWorkspaceService, Depends(get_records_service)],
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=50, ge=1, le=500),
    submitted_by_email: str | None = Query(default=None),
    outreach_status: str | None = Query(default=None),
    search: str | None = Query(default=None, min_length=1),
) -> PaginatedLeadRecords:
    return await service.list_records(
        page=page,
        limit=limit,
        submitted_by_email=submitted_by_email,
        outreach_status=outreach_status,
        search=search,
    )


@router.get("/export")
async def export_records_csv(
    service: Annotated[RecordsWorkspaceService, Depends(get_records_service)],
    submitted_by_email: str | None = Query(default=None),
    outreach_status: str | None = Query(default=None),
    search: str | None = Query(default=None, min_length=1),
) -> Response:
    payload = await service.export_records_csv(
        submitted_by_email=submitted_by_email,
        outreach_status=outreach_status,
        search=search,
    )
    timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    return Response(
        content=payload,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="lead-records-{timestamp}.csv"',
        },
    )
