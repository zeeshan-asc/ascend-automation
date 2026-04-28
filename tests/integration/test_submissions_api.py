import asyncio
from datetime import UTC, datetime

import pytest

from app.application.container import AppContainer
from app.domain.enums import SourceKind
from app.domain.errors import FeedFetchError, SourceFetchError
from app.domain.models import ParsedEpisode


class FakeSubmissionSourceResolver:
    def __init__(self, *, failing_urls: dict[str, SourceFetchError] | None = None) -> None:
        self._failing_urls = failing_urls or {}

    async def resolve_source(
        self,
        *,
        source_url: str,
        source_kind: SourceKind,
        max_results: int,
    ) -> list[ParsedEpisode]:
        if source_url in self._failing_urls:
            raise self._failing_urls[source_url]

        if source_url.endswith(".mp3") or source_kind == SourceKind.AUDIO_FILE:
            return [
                ParsedEpisode(
                    title="Direct audio episode",
                    episode_url=None,
                    audio_url=source_url,
                    published_at=None,
                    source_url=source_url,
                    source_kind=SourceKind.AUDIO_FILE,
                    dedupe_key=f"audio:{source_url}",
                )
            ]

        if "episode" in source_url or source_kind == SourceKind.EPISODE_PAGE:
            return [
                ParsedEpisode(
                    title="Single podcast episode",
                    episode_url=source_url,
                    audio_url=f"{source_url.rstrip('/')}/audio.mp3",
                    published_at="2026-04-27",
                    source_url=source_url,
                    source_kind=SourceKind.EPISODE_PAGE,
                    dedupe_key=f"audio:{source_url.rstrip('/')}/audio.mp3",
                )
            ]

        return [
            ParsedEpisode(
                guid=f"{source_url}-guid-1",
                title="Episode 1",
                episode_url=f"{source_url}/episode-1",
                audio_url=f"{source_url}/episode-1.mp3",
                published_at="2026-04-27",
                source_url=source_url,
                source_kind=SourceKind.RSS_FEED,
                dedupe_key=f"{source_url}-guid-1",
            ),
        ][:max_results]


@pytest.mark.asyncio
async def test_create_submission_returns_accepted_and_persists_run(
    authenticated_client,
    app_container: AppContainer,
    auth_credentials: dict[str, str],
) -> None:
    app_container.source_resolver = FakeSubmissionSourceResolver()
    payload = {
        "source_url": "https://example.com/feed.xml",
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
    assert run.source_url == payload["source_url"]
    assert run.source_kind == SourceKind.RSS_FEED


@pytest.mark.asyncio
async def test_create_submission_accepts_legacy_rss_url_payload(
    authenticated_client,
    app_container: AppContainer,
) -> None:
    app_container.source_resolver = FakeSubmissionSourceResolver()

    response = await authenticated_client.post(
        "/api/submissions",
        json={
            "rss_url": "https://example.com/feed.xml",
            "submitted_at": datetime.now(UTC).isoformat(),
        },
    )

    assert response.status_code == 202
    run = await app_container.run_repository.get_by_run_id(response.json()["run_id"])
    assert run is not None
    assert run.source_url == "https://example.com/feed.xml"


@pytest.mark.asyncio
async def test_create_submission_accepts_direct_audio_source(
    authenticated_client,
    app_container: AppContainer,
) -> None:
    app_container.source_resolver = FakeSubmissionSourceResolver()
    payload = {
        "source_url": "https://cdn.example.com/podcast-1.mp3",
        "submitted_at": datetime.now(UTC).isoformat(),
    }

    response = await authenticated_client.post("/api/submissions", json=payload)

    assert response.status_code == 202
    run = await app_container.run_repository.get_by_run_id(response.json()["run_id"])
    assert run is not None
    assert run.source_kind == SourceKind.AUDIO_FILE


@pytest.mark.asyncio
async def test_create_submission_accepts_single_episode_page_source(
    authenticated_client,
    app_container: AppContainer,
) -> None:
    app_container.source_resolver = FakeSubmissionSourceResolver()
    payload = {
        "source_url": "https://podcast.show/1461261/episode/153801033/",
        "submitted_at": datetime.now(UTC).isoformat(),
    }

    response = await authenticated_client.post("/api/submissions", json=payload)

    assert response.status_code == 202
    run = await app_container.run_repository.get_by_run_id(response.json()["run_id"])
    assert run is not None
    assert run.source_kind == SourceKind.EPISODE_PAGE


@pytest.mark.asyncio
async def test_create_submission_requires_authentication(client) -> None:
    payload = {
        "source_url": "https://example.com/feed.xml",
        "submitted_at": datetime.now(UTC).isoformat(),
    }

    response = await client.post("/api/submissions", json=payload)

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_create_submission_rejects_invalid_source_url(authenticated_client) -> None:
    payload = {
        "source_url": "not-a-valid-url",
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
    app_container.source_resolver = FakeSubmissionSourceResolver(
        failing_urls={
            feed_url: FeedFetchError(
                "The RSS feed URL returned 404 Not Found.",
                reason_code="feed_not_found",
            ),
        },
    )
    payload = {
        "source_url": feed_url,
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
async def test_create_submission_rejects_invalid_episode_page_before_queueing(
    authenticated_client,
    app_container: AppContainer,
) -> None:
    page_url = "https://example.com/not-a-podcast-page"
    app_container.source_resolver = FakeSubmissionSourceResolver(
        failing_urls={
            page_url: SourceFetchError(
                "The URL did not return a podcast episode page.",
                reason_code="source_invalid",
            ),
        },
    )

    response = await authenticated_client.post(
        "/api/submissions",
        json={"source_url": page_url, "submitted_at": datetime.now(UTC).isoformat()},
    )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "source_invalid"
    runs, total = await app_container.run_repository.list_runs(page=1, limit=20)
    assert total == 0
    assert runs == []


@pytest.mark.asyncio
async def test_create_submission_rejects_episode_page_with_no_audio_before_queueing(
    authenticated_client,
    app_container: AppContainer,
) -> None:
    page_url = "https://example.com/no-audio-episode"
    app_container.source_resolver = FakeSubmissionSourceResolver(
        failing_urls={
            page_url: SourceFetchError(
                "The episode page did not expose a usable audio file.",
                reason_code="episode_audio_not_found",
            ),
        },
    )

    response = await authenticated_client.post(
        "/api/submissions",
        json={"source_url": page_url, "submitted_at": datetime.now(UTC).isoformat()},
    )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "episode_audio_not_found"
    _, total = await app_container.run_repository.list_runs(page=1, limit=20)
    assert total == 0


@pytest.mark.asyncio
async def test_parallel_submissions_are_isolated(
    authenticated_client,
    app_container: AppContainer,
) -> None:
    bad_source_url = "https://example.com/episode-bad"
    app_container.source_resolver = FakeSubmissionSourceResolver(
        failing_urls={
            bad_source_url: SourceFetchError(
                "The source URL could not be reached. Check the URL and try again.",
                reason_code="source_unreachable",
            ),
        },
    )

    async def submit(index: int) -> str:
        source_url = (
            bad_source_url
            if index == 7
            else f"https://example.com/feed-{index}.xml"
        )
        payload = {
            "source_url": source_url,
            "submitted_at": datetime.now(UTC).isoformat(),
        }
        response = await authenticated_client.post("/api/submissions", json=payload)
        if source_url == bad_source_url:
            assert response.status_code == 422
            assert response.json()["detail"]["code"] == "source_unreachable"
            return "rejected"
        assert response.status_code == 202
        return response.json()["run_id"]

    run_ids = await asyncio.gather(*(submit(index) for index in range(8)))

    accepted_run_ids = [run_id for run_id in run_ids if run_id != "rejected"]
    assert len(set(accepted_run_ids)) == 7
    runs, total = await app_container.run_repository.list_runs(page=1, limit=20)
    assert total == 7
    assert len(runs) == 7
