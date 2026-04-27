import asyncio
from datetime import UTC, datetime

import pytest

from app.application.container import AppContainer
from app.domain.errors import FeedFetchError
from app.domain.models import ParsedEpisode


class FakeSubmissionRSSProvider:
    def __init__(self, *, failing_urls: dict[str, FeedFetchError] | None = None) -> None:
        self._failing_urls = failing_urls or {}

    async def fetch_episodes(self, rss_url: str, max_results: int) -> list[ParsedEpisode]:
        if rss_url in self._failing_urls:
            raise self._failing_urls[rss_url]
        return [
            ParsedEpisode(
                guid=f"{rss_url}-guid-1",
                title="Episode 1",
                episode_url=f"{rss_url}/episode-1",
                audio_url=f"{rss_url}/episode-1.mp3",
                published_at="2026-04-27",
                feed_url=rss_url,
                dedupe_key=f"{rss_url}-guid-1",
            ),
        ][:max_results]


@pytest.mark.asyncio
async def test_create_submission_returns_accepted_and_persists_run(
    authenticated_client,
    app_container: AppContainer,
    auth_credentials: dict[str, str],
) -> None:
    app_container.rss_provider = FakeSubmissionRSSProvider()
    payload = {
        "rss_url": "https://example.com/feed.xml",
        "tone_instructions": "Keep it concise",
        "submitted_at": datetime.now(UTC).isoformat(),
    }

    response = await authenticated_client.post("/api/submissions", json=payload)

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "queued"
    run = await app_container.run_repository.get_by_run_id(body["run_id"])
    assert run is not None
    assert run.submitted_by_email == auth_credentials["email"]
    assert run.submitted_by == auth_credentials["name"]


@pytest.mark.asyncio
async def test_create_submission_requires_authentication(client) -> None:
    payload = {
        "rss_url": "https://example.com/feed.xml",
        "submitted_at": datetime.now(UTC).isoformat(),
    }

    response = await client.post("/api/submissions", json=payload)

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_create_submission_rejects_invalid_rss_url(authenticated_client) -> None:
    payload = {
        "rss_url": "not-a-valid-url",
        "submitted_at": datetime.now(UTC).isoformat(),
    }

    response = await authenticated_client.post("/api/submissions", json=payload)

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_submission_rejects_missing_fields(authenticated_client) -> None:
    response = await authenticated_client.post("/api/submissions", json={})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_submission_rejects_missing_feed_before_queueing(
    authenticated_client,
    app_container: AppContainer,
) -> None:
    feed_url = "https://example.com/missing-feed.xml"
    app_container.rss_provider = FakeSubmissionRSSProvider(
        failing_urls={
            feed_url: FeedFetchError(
                "The RSS feed URL returned 404 Not Found.",
                reason_code="feed_not_found",
            ),
        },
    )
    payload = {
        "rss_url": feed_url,
        "submitted_at": datetime.now(UTC).isoformat(),
    }

    response = await authenticated_client.post("/api/submissions", json=payload)

    assert response.status_code == 422
    assert response.json() == {
        "detail": {
            "code": "feed_not_found",
            "message": "The RSS feed URL returned 404 Not Found.",
        },
    }
    runs, total = await app_container.run_repository.list_runs(page=1, limit=20)
    assert total == 0
    assert runs == []


@pytest.mark.asyncio
async def test_create_submission_rejects_invalid_feed_document_before_queueing(
    authenticated_client,
    app_container: AppContainer,
) -> None:
    feed_url = "https://example.com/not-a-feed.xml"
    app_container.rss_provider = FakeSubmissionRSSProvider(
        failing_urls={
            feed_url: FeedFetchError(
                "The URL did not return a valid RSS or Atom feed.",
                reason_code="feed_invalid",
            ),
        },
    )
    payload = {
        "rss_url": feed_url,
        "submitted_at": datetime.now(UTC).isoformat(),
    }

    response = await authenticated_client.post("/api/submissions", json=payload)

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "feed_invalid"
    runs, total = await app_container.run_repository.list_runs(page=1, limit=20)
    assert total == 0


@pytest.mark.asyncio
async def test_create_submission_rejects_feed_with_no_audio_items_before_queueing(
    authenticated_client,
    app_container: AppContainer,
) -> None:
    feed_url = "https://example.com/no-audio.xml"
    app_container.rss_provider = FakeSubmissionRSSProvider(
        failing_urls={
            feed_url: FeedFetchError(
                "The feed did not contain any usable audio items in the latest 5 episodes.",
                reason_code="feed_has_no_audio_items",
            ),
        },
    )
    payload = {
        "rss_url": feed_url,
        "submitted_at": datetime.now(UTC).isoformat(),
    }

    response = await authenticated_client.post("/api/submissions", json=payload)

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "feed_has_no_audio_items"
    _, total = await app_container.run_repository.list_runs(page=1, limit=20)
    assert total == 0


@pytest.mark.asyncio
async def test_parallel_submissions_are_isolated(
    authenticated_client,
    app_container: AppContainer,
) -> None:
    bad_feed_url = "https://example.com/feed-bad.xml"
    app_container.rss_provider = FakeSubmissionRSSProvider(
        failing_urls={
            bad_feed_url: FeedFetchError(
                "The RSS feed could not be reached. Check the URL and try again.",
                reason_code="feed_unreachable",
            ),
        },
    )

    async def submit(index: int) -> str:
        feed_url = bad_feed_url if index == 7 else f"https://example.com/feed-{index}.xml"
        payload = {
            "rss_url": feed_url,
            "submitted_at": datetime.now(UTC).isoformat(),
        }
        response = await authenticated_client.post("/api/submissions", json=payload)
        if feed_url == bad_feed_url:
            assert response.status_code == 422
            assert response.json()["detail"]["code"] == "feed_unreachable"
            return "rejected"
        assert response.status_code == 202
        return response.json()["run_id"]

    run_ids = await asyncio.gather(*(submit(index) for index in range(8)))

    accepted_run_ids = [run_id for run_id in run_ids if run_id != "rejected"]
    assert len(set(accepted_run_ids)) == 7
    runs, total = await app_container.run_repository.list_runs(page=1, limit=20)
    assert total == 7
    assert len(runs) == 7
