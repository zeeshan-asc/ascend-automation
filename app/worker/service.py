from __future__ import annotations

import asyncio
import contextlib
import logging
from datetime import timedelta

from app.config import Settings
from app.domain.interfaces import RunRepositoryProtocol
from app.domain.models import Run, utcnow
from app.worker.orchestrator import PipelineOrchestrator

logger = logging.getLogger(__name__)


class WorkerService:
    def __init__(
        self,
        *,
        settings: Settings,
        worker_id: str,
        run_repository: RunRepositoryProtocol,
        orchestrator: PipelineOrchestrator,
    ) -> None:
        self._settings = settings
        self._worker_id = worker_id
        self._run_repository = run_repository
        self._orchestrator = orchestrator

    async def process_next_available(self) -> Run | None:
        claimed = await self._run_repository.claim_next(worker_id=self._worker_id, now=utcnow())
        if claimed is None:
            return None
        logger.info("worker.claimed worker_id=%s run_id=%s", self._worker_id, claimed.run_id)
        heartbeat_task = asyncio.create_task(self._heartbeat_loop(claimed.run_id))
        try:
            processed = await self._orchestrator.process_run(
                run_id=claimed.run_id,
                worker_id=self._worker_id,
            )
            if processed is not None:
                logger.info(
                    "worker.completed worker_id=%s run_id=%s status=%s completed=%s failed=%s",
                    self._worker_id,
                    processed.run_id,
                    processed.status,
                    processed.completed_items,
                    processed.failed_items,
                )
            return processed
        finally:
            heartbeat_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await heartbeat_task

    async def reclaim_stale_runs(self) -> list[str]:
        threshold = utcnow() - timedelta(seconds=self._settings.stale_run_seconds)
        reclaimed = await self._run_repository.reclaim_stale(threshold=threshold, now=utcnow())
        if reclaimed:
            logger.warning("worker.reclaimed_stale run_ids=%s", ",".join(reclaimed))
        return reclaimed

    async def run_until_empty(self, *, idle_cycles: int = 1) -> None:
        empty_cycles = 0
        while empty_cycles < idle_cycles:
            await self.reclaim_stale_runs()
            processed = await self.process_next_available()
            if processed is None:
                empty_cycles += 1
                await asyncio.sleep(self._settings.queue_poll_interval_seconds)
            else:
                empty_cycles = 0

    async def _heartbeat_loop(self, run_id: str) -> None:
        while True:
            await asyncio.sleep(self._settings.run_heartbeat_seconds)
            await self._run_repository.update_heartbeat(
                run_id=run_id,
                worker_id=self._worker_id,
                now=utcnow(),
            )
            logger.info("worker.heartbeat worker_id=%s run_id=%s", self._worker_id, run_id)
