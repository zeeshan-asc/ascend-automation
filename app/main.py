import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from time import perf_counter
from uuid import uuid4

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from app.api.dashboard import router as dashboard_router
from app.api.episodes import router as episodes_router
from app.api.health import router as health_router
from app.api.leads import router as leads_router
from app.api.runs import router as runs_router
from app.api.submissions import router as submissions_router
from app.application.container import AppContainer
from app.config import Settings, get_settings
from app.database import MongoManager, bootstrap_mongo
from app.logging import configure_logging
from app.worker.runner import run_worker

logger = logging.getLogger(__name__)


def _configure_logging(settings: Settings) -> None:
    configure_logging(
        settings.log_level,
        [
            settings.openai_api_key.get_secret_value(),
            settings.assemblyai_api_key.get_secret_value(),
        ],
        service_name="web",
        log_directory=settings.resolved_log_dir,
    )


def create_app(
    settings: Settings | None = None,
    mongo_manager: MongoManager | None = None,
    container: AppContainer | None = None,
    *,
    configure_runtime_logging: bool = True,
) -> FastAPI:
    app_settings = settings or get_settings()
    if configure_runtime_logging:
        _configure_logging(app_settings)
    project_root = app_settings.project_root

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        manager = mongo_manager
        app_container = container
        if app_container is None:
            manager = manager or await bootstrap_mongo(app_settings)
            app_container = await AppContainer.build(settings=app_settings, mongo_manager=manager)
        app.state.settings = app_settings
        app.state.mongo_manager = manager
        app.state.container = app_container
        yield
        if container is None and manager is not None:
            await manager.close()

    app = FastAPI(title="RSS Automation", lifespan=lifespan)

    @app.middleware("http")
    async def request_logging_middleware(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        request_id = uuid4().hex[:8]
        start = perf_counter()
        logger.info(
            "request.started request_id=%s method=%s path=%s",
            request_id,
            request.method,
            request.url.path,
        )
        try:
            response = await call_next(request)
        except Exception:
            duration_ms = (perf_counter() - start) * 1000
            logger.exception(
                "request.failed request_id=%s path=%s duration_ms=%.2f",
                request_id,
                request.url.path,
                duration_ms,
            )
            raise
        duration_ms = (perf_counter() - start) * 1000
        logger.info(
            "request.completed request_id=%s method=%s path=%s status=%s duration_ms=%.2f",
            request_id,
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
        )
        return response

    app.include_router(dashboard_router)
    app.include_router(episodes_router)
    app.include_router(health_router)
    app.include_router(leads_router)
    app.include_router(runs_router)
    app.include_router(submissions_router)

    static_path = project_root / "app" / "static"
    static_path.mkdir(parents=True, exist_ok=True)
    app.mount("/static", StaticFiles(directory=static_path), name="static")

    @app.get("/", include_in_schema=False)
    async def landing_page() -> FileResponse:
        index_path = project_root / "index.html"
        return FileResponse(index_path)

    @app.get("/dashboard", include_in_schema=False)
    async def dashboard_page() -> FileResponse:
        dashboard_path = project_root / "app" / "static" / "dashboard.html"
        return FileResponse(dashboard_path)

    return app


app = create_app(configure_runtime_logging=False) if __name__ == "__main__" else create_app()


async def run_stack(settings: Settings | None = None) -> None:
    runtime_settings = settings or get_settings()
    configure_logging(
        runtime_settings.log_level,
        [
            runtime_settings.openai_api_key.get_secret_value(),
            runtime_settings.assemblyai_api_key.get_secret_value(),
        ],
        service_name="app",
        log_directory=runtime_settings.resolved_log_dir,
    )
    mongo_manager = await bootstrap_mongo(runtime_settings)
    container = await AppContainer.build(settings=runtime_settings, mongo_manager=mongo_manager)
    combined_app = create_app(
        settings=runtime_settings,
        mongo_manager=mongo_manager,
        container=container,
        configure_runtime_logging=False,
    )
    server = uvicorn.Server(
        uvicorn.Config(
            combined_app,
            host=runtime_settings.app_host,
            port=runtime_settings.app_port,
            log_config=None,
        ),
    )
    stop_event = asyncio.Event()

    logger.info(
        "runtime.started mode=combined host=%s port=%s",
        runtime_settings.app_host,
        runtime_settings.app_port,
    )
    worker_task = asyncio.create_task(
        run_worker(
            settings=runtime_settings,
            mongo_manager=mongo_manager,
            container=container,
            stop_event=stop_event,
            configure_runtime_logging=False,
            service_name="app",
            register_signals=False,
        ),
    )
    web_task = asyncio.create_task(server.serve())

    try:
        done, pending = await asyncio.wait(
            {web_task, worker_task},
            return_when=asyncio.FIRST_COMPLETED,
        )
        if web_task in done:
            stop_event.set()
        if worker_task in done:
            server.should_exit = True
        for task in pending:
            task.cancel()
        for task in pending:
            with contextlib.suppress(asyncio.CancelledError):
                await task
        for task in done:
            task.result()
    finally:
        stop_event.set()
        server.should_exit = True
        with contextlib.suppress(asyncio.CancelledError):
            await worker_task
        with contextlib.suppress(asyncio.CancelledError):
            await web_task
        await mongo_manager.close()
        logger.info("runtime.stopped mode=combined")


def main() -> None:
    asyncio.run(run_stack())


if __name__ == "__main__":
    main()
