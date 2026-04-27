from fastapi import APIRouter, Depends

from app.api.dependencies import get_current_user

router = APIRouter(tags=["health"], dependencies=[Depends(get_current_user)])


@router.get("/health")
async def healthcheck() -> dict[str, str]:
    return {"status": "ok"}
