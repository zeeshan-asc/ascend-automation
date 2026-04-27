from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.dependencies import get_container, get_current_user
from app.application.container import AppContainer
from app.application.submissions import SubmissionService
from app.domain.errors import FeedFetchError
from app.domain.models import AuthenticatedUser, SubmissionRequest

router = APIRouter(
    prefix="/api/submissions",
    tags=["submissions"],
    dependencies=[Depends(get_current_user)],
)
ContainerDep = Annotated[AppContainer, Depends(get_container)]
CurrentUserDep = Annotated[AuthenticatedUser, Depends(get_current_user)]


@router.post("", status_code=status.HTTP_202_ACCEPTED)
async def create_submission(
    payload: SubmissionRequest,
    container: ContainerDep,
    current_user: CurrentUserDep,
) -> dict[str, str]:
    service = SubmissionService(
        container.settings,
        container.run_repository,
        container.rss_provider,
    )
    try:
        run = await service.create_submission(payload, current_user=current_user)
    except FeedFetchError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "code": exc.reason_code,
                "message": str(exc),
            },
        ) from exc
    return {
        "run_id": run.run_id,
        "status": run.status.value,
        "dashboard_url": service.build_dashboard_url(run.run_id),
    }
