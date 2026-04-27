from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.dependencies import get_dashboard_service
from app.application.dashboard import DashboardQueryService, EpisodeDetail
from app.domain.errors import ResourceNotFoundError

router = APIRouter(prefix="/api/episodes", tags=["episodes"])


@router.get("/{episode_id}", response_model=EpisodeDetail)
async def get_episode_detail(
    episode_id: str,
    service: Annotated[DashboardQueryService, Depends(get_dashboard_service)],
) -> EpisodeDetail:
    try:
        return await service.get_episode_detail(episode_id=episode_id)
    except ResourceNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
