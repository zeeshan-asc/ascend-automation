from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.api.dependencies import get_container
from app.application.container import AppContainer
from app.application.submissions import SubmissionService
from app.domain.models import SubmissionRequest

router = APIRouter(prefix="/api/submissions", tags=["submissions"])
ContainerDep = Annotated[AppContainer, Depends(get_container)]


@router.post("", status_code=status.HTTP_202_ACCEPTED)
async def create_submission(
    payload: SubmissionRequest,
    container: ContainerDep,
) -> dict[str, str]:
    service = SubmissionService(container.settings, container.run_repository)
    run = await service.create_submission(payload)
    return {
        "run_id": run.run_id,
        "status": run.status.value,
        "dashboard_url": service.build_dashboard_url(run.run_id),
    }
