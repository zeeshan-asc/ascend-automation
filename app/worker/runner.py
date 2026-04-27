from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import signal
import socket

from app.application.container import AppContainer
from app.config import Settings, get_settings
from app.database import MongoManager, bootstrap_mongo
from app.infrastructure.providers.assemblyai import AssemblyAIProvider
from app.infrastructure.providers.openai_client import OpenAIProvider
from app.infrastructure.providers.rss import RSSProvider
from app.logging import configure_logging
from app.worker.orchestrator import PipelineOrchestrator
from app.worker.service import WorkerService

logger = logging.getLogger(__name__)


def build_orchestrator(
    *,
    settings: Settings,
    container: AppContainer,
) -> PipelineOrchestrator:
    rss_provider = RSSProvider(timeout_seconds=settings.rss_fetch_timeout_seconds)
    assemblyai_provider = AssemblyAIProvider(
        api_key=settings.assemblyai_api_key.get_secret_value(),
        base_url=settings.assemblyai_base_url,
        poll_interval_seconds=settings.assemblyai_poll_interval_seconds,
        timeout_seconds=settings.assemblyai_timeout_seconds,
        max_inflight=settings.assemblyai_max_inflight,
    )
    openai_provider = OpenAIProvider(
        api_key=settings.openai_api_key.get_secret_value(),
        model=settings.openai_model,
        prompt_version=settings.openai_prompt_version,
        max_inflight=settings.openai_max_inflight,
    )
    return PipelineOrchestrator(
        settings=settings,
        run_repository=container.run_repository,
        episode_repository=container.episode_repository,
        run_item_repository=container.run_item_repository,
        transcript_repository=container.transcript_repository,
        lead_repository=container.lead_repository,
        rss_provider=rss_provider,
        assemblyai_provider=assemblyai_provider,
        openai_provider=openai_provider,
    )


def build_worker_services(
    *,
    settings: Settings,
    container: AppContainer,
    orchestrator: PipelineOrchestrator,
) -> list[WorkerService]:
    hostname = socket.gethostname()
    pid = os.getpid()
    return [
        WorkerService(
            settings=settings,
            worker_id=f"{hostname}-{pid}-slot-{index}",
            run_repository=container.run_repository,
            orchestrator=orchestrator,
        )
        for index in range(settings.run_worker_concurrency)
    ]


async def run_worker(
    *,
    settings: Settings | None = None,
    mongo_manager: MongoManager | None = None,
    container: AppContainer | None = None,
    stop_event: asyncio.Event | None = None,
    configure_runtime_logging: bool = True,
    service_name: str = "worker",
    register_signals: bool = True,
) -> None:
    runtime_settings = settings or get_settings()
    if configure_runtime_logging:
        configure_logging(
            runtime_settings.log_level,
            [
                runtime_settings.openai_api_key.get_secret_value(),
                runtime_settings.assemblyai_api_key.get_secret_value(),
            ],
            service_name=service_name,
            log_directory=runtime_settings.resolved_log_dir,
        )

    owns_mongo_manager = mongo_manager is None
    manager = mongo_manager or await bootstrap_mongo(runtime_settings)
    app_container = container or await AppContainer.build(
        settings=runtime_settings,
        mongo_manager=manager,
    )
    orchestrator = build_orchestrator(settings=runtime_settings, container=app_container)
    workers = build_worker_services(
        settings=runtime_settings,
        container=app_container,
        orchestrator=orchestrator,
    )
    runtime_stop_event = stop_event or asyncio.Event()
    if register_signals:
        _register_shutdown_handlers(runtime_stop_event)
    logger.info(
        "worker.runner.started concurrency=%s mongodb_db=%s",
        runtime_settings.run_worker_concurrency,
        runtime_settings.mongodb_db_name,
    )

    stale_task = asyncio.create_task(
        _stale_reclaimer(runtime_stop_event, workers[0], runtime_settings),
    )
    worker_tasks = [
        asyncio.create_task(_worker_slot(runtime_stop_event, worker, runtime_settings))
        for worker in workers
    ]

    try:
        await asyncio.gather(*worker_tasks)
    finally:
        runtime_stop_event.set()
        stale_task.cancel()
        for task in worker_tasks:
            task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await stale_task
        with contextlib.suppress(asyncio.CancelledError):
            await asyncio.gather(*worker_tasks)
        if owns_mongo_manager:
            await manager.close()
        logger.info("worker.runner.stopped")


async def _worker_slot(
    stop_event: asyncio.Event,
    worker: WorkerService,
    settings: Settings,
) -> None:
    while not stop_event.is_set():
        processed = await worker.process_next_available()
        if processed is None:
            try:
                await asyncio.wait_for(
                    stop_event.wait(),
                    timeout=settings.queue_poll_interval_seconds,
                )
            except TimeoutError:
                continue


async def _stale_reclaimer(
    stop_event: asyncio.Event,
    worker: WorkerService,
    settings: Settings,
) -> None:
    interval = max(settings.queue_poll_interval_seconds, 5)
    while not stop_event.is_set():
        await worker.reclaim_stale_runs()
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval)
        except TimeoutError:
            continue


def _register_shutdown_handlers(stop_event: asyncio.Event) -> None:
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(sig, stop_event.set)


def main() -> None:
    asyncio.run(run_worker())


if __name__ == "__main__":
    main()
