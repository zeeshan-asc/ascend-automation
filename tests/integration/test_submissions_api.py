import asyncio
from datetime import UTC, datetime

import pytest

from app.application.container import AppContainer


@pytest.mark.asyncio
async def test_create_submission_returns_accepted_and_persists_run(
    client,
    app_container: AppContainer,
) -> None:
    payload = {
        "user_name": "Jane",
        "user_email": "jane@example.com",
        "rss_url": "https://example.com/feed.xml",
        "tone_instructions": "Keep it concise",
        "submitted_at": datetime.now(UTC).isoformat(),
    }

    response = await client.post("/api/submissions", json=payload)

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "queued"
    run = await app_container.run_repository.get_by_run_id(body["run_id"])
    assert run is not None
    assert run.submitted_by_email == "jane@example.com"


@pytest.mark.asyncio
async def test_create_submission_rejects_invalid_email(client) -> None:
    payload = {
        "user_name": "Jane",
        "user_email": "not-an-email",
        "rss_url": "https://example.com/feed.xml",
        "submitted_at": datetime.now(UTC).isoformat(),
    }

    response = await client.post("/api/submissions", json=payload)

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_submission_rejects_invalid_rss_url(client) -> None:
    payload = {
        "user_name": "Jane",
        "user_email": "jane@example.com",
        "rss_url": "not-a-valid-url",
        "submitted_at": datetime.now(UTC).isoformat(),
    }

    response = await client.post("/api/submissions", json=payload)

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_submission_rejects_missing_fields(client) -> None:
    response = await client.post("/api/submissions", json={"user_name": "Jane"})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_parallel_submissions_are_isolated(client, app_container: AppContainer) -> None:
    async def submit(index: int) -> str:
        payload = {
            "user_name": f"User {index}",
            "user_email": f"user{index}@example.com",
            "rss_url": f"https://example.com/feed-{index}.xml",
            "submitted_at": datetime.now(UTC).isoformat(),
        }
        response = await client.post("/api/submissions", json=payload)
        assert response.status_code == 202
        return response.json()["run_id"]

    run_ids = await asyncio.gather(*(submit(index) for index in range(8)))

    assert len(set(run_ids)) == 8
    runs, total = await app_container.run_repository.list_runs(page=1, limit=20)
    assert total == 8
    assert len(runs) == 8
