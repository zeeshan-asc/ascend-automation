from __future__ import annotations

import logging

from pydantic import BaseModel, ConfigDict

from app.domain.enums import RunItemStatus
from app.domain.errors import InvalidOperationError, ResourceNotFoundError
from app.domain.interfaces import RunItemRepositoryProtocol, RunRepositoryProtocol
from app.domain.models import utcnow

logger = logging.getLogger(__name__)


class RunItemRetryAccepted(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    run_id: str
    run_item_id: str
    status: str
    message: str


class RunItemRetryService:
    def __init__(
        self,
        *,
        run_repository: RunRepositoryProtocol,
        run_item_repository: RunItemRepositoryProtocol,
    ) -> None:
        self._run_repository = run_repository
        self._run_item_repository = run_item_repository

    async def queue_retry(self, *, run_item_id: str) -> RunItemRetryAccepted:
        run_item = await self._run_item_repository.get_by_run_item_id(run_item_id)
        if run_item is None:
            raise ResourceNotFoundError(f"Run item {run_item_id} was not found.")
        if str(run_item.status) != RunItemStatus.FAILED.value:
            raise InvalidOperationError("Only failed episodes can be retried.")
        if await self._run_repository.has_active_runs():
            raise InvalidOperationError(
                "The queue must be idle before retrying a failed episode.",
            )

        run = await self._run_repository.get_by_run_id(run_item.run_id)
        if run is None:
            raise ResourceNotFoundError(f"Run {run_item.run_id} was not found.")

        now = utcnow()
        await self._run_item_repository.reset_for_retry(run_item_id=run_item_id, now=now)
        queued_run = await self._run_repository.queue_retry(
            run_id=run.run_id,
            retry_run_item_ids=[run_item_id],
            now=now,
        )
        if queued_run is None:
            raise ResourceNotFoundError(f"Run {run.run_id} was not found.")

        logger.info(
            "run_item.retry.queued run_id=%s run_item_id=%s episode_id=%s",
            run.run_id,
            run_item_id,
            run_item.episode_id,
        )
        return RunItemRetryAccepted(
            run_id=run.run_id,
            run_item_id=run_item_id,
            status="queued",
            message="The failed episode has been requeued for retry.",
        )
