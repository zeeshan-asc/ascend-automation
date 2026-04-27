from __future__ import annotations

import asyncio
from dataclasses import dataclass

import pytest

import app.main as main_module
from app.config import Settings


@dataclass
class FakeMongoManager:
    closed: bool = False

    async def close(self) -> None:
        self.closed = True


class FakeServer:
    def __init__(self, config) -> None:
        self.config = config
        self.should_exit = False

    async def serve(self) -> None:
        await asyncio.sleep(0)


@pytest.mark.asyncio
async def test_run_stack_starts_web_and_worker_in_one_runtime(
    test_settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_manager = FakeMongoManager()
    fake_container = object()
    fake_app = object()
    captured: dict[str, object] = {}

    async def fake_bootstrap(settings: Settings) -> FakeMongoManager:
        captured["bootstrapped_with"] = settings
        return fake_manager

    async def fake_build(*, settings: Settings, mongo_manager: FakeMongoManager) -> object:
        captured["built_with"] = (settings, mongo_manager)
        return fake_container

    def fake_create_app(**kwargs) -> object:
        captured["create_app_kwargs"] = kwargs
        return fake_app

    class FakeConfig:
        def __init__(self, app, *, host: str, port: int, log_config) -> None:
            captured["uvicorn_config"] = {
                "app": app,
                "host": host,
                "port": port,
                "log_config": log_config,
            }

    async def fake_run_worker(**kwargs) -> None:
        captured["run_worker_kwargs"] = kwargs
        await kwargs["stop_event"].wait()

    monkeypatch.setattr(main_module, "bootstrap_mongo", fake_bootstrap)
    monkeypatch.setattr(main_module.AppContainer, "build", fake_build)
    monkeypatch.setattr(main_module, "create_app", fake_create_app)
    monkeypatch.setattr(main_module.uvicorn, "Config", FakeConfig)
    monkeypatch.setattr(main_module.uvicorn, "Server", FakeServer)
    monkeypatch.setattr(main_module, "run_worker", fake_run_worker)
    monkeypatch.setattr(main_module, "configure_logging", lambda *args, **kwargs: None)

    await main_module.run_stack(test_settings)

    assert captured["bootstrapped_with"] is test_settings
    assert captured["built_with"] == (test_settings, fake_manager)
    assert captured["create_app_kwargs"]["container"] is fake_container
    assert captured["create_app_kwargs"]["mongo_manager"] is fake_manager
    assert captured["create_app_kwargs"]["configure_runtime_logging"] is False
    assert captured["uvicorn_config"]["app"] is fake_app
    assert captured["uvicorn_config"]["host"] == test_settings.app_host
    assert captured["uvicorn_config"]["port"] == test_settings.app_port
    assert captured["run_worker_kwargs"]["mongo_manager"] is fake_manager
    assert captured["run_worker_kwargs"]["container"] is fake_container
    assert captured["run_worker_kwargs"]["configure_runtime_logging"] is False
    assert captured["run_worker_kwargs"]["register_signals"] is False
    assert fake_manager.closed is True
