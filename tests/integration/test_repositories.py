import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from app.application.container import AppContainer
from app.config import Settings
from app.domain.enums import RunItemStatus, RunStatus, TranscriptStatus
from app.domain.models import Episode, Lead, Run, RunItem, Transcript
from tests.helpers.async_mongomock import FakeMongoManager


@pytest.fixture
async def container(test_settings: Settings) -> AppContainer:
    manager = FakeMongoManager()
    return await AppContainer.build(settings=test_settings, mongo_manager=manager)


@pytest.mark.asyncio
async def test_run_repository_create_and_claim(container: AppContainer) -> None:
    run = Run(
        rss_url="https://example.com/feed.xml",
        submitted_by="Jane",
        submitted_by_email="jane@example.com",
        submitted_at=datetime.now(UTC),
    )
    await container.run_repository.create(run)

    claimed = await container.run_repository.claim_next(worker_id="worker-1", now=datetime.now(UTC))

    assert claimed is not None
    assert claimed.run_id == run.run_id
    assert claimed.status == RunStatus.CLAIMED


@pytest.mark.asyncio
async def test_concurrent_claim_allows_exactly_one_worker(container: AppContainer) -> None:
    run = Run(
        rss_url="https://example.com/feed.xml",
        submitted_by="Jane",
        submitted_by_email="jane@example.com",
        submitted_at=datetime.now(UTC),
    )
    await container.run_repository.create(run)

    async def claim(worker_id: str) -> Run | None:
        return await container.run_repository.claim_next(worker_id=worker_id, now=datetime.now(UTC))

    first, second = await asyncio.gather(claim("worker-a"), claim("worker-b"))
    claimed = [item for item in (first, second) if item is not None]
    assert len(claimed) == 1


@pytest.mark.asyncio
async def test_episode_upsert_creates_single_canonical_episode(container: AppContainer) -> None:
    episode = Episode(
        dedupe_key="guid-1",
        title="Episode 1",
        episode_url="https://example.com/ep1",
        audio_url="https://cdn.example.com/ep1.mp3",
        published_at="2026-04-01",
        feed_url="https://example.com/feed.xml",
    )

    created, reused = await asyncio.gather(
        container.episode_repository.upsert(episode),
        container.episode_repository.upsert(episode),
    )

    assert created.episode_id == reused.episode_id
    episodes, total = await container.episode_repository.list_episodes(page=1, limit=10)
    assert total == 1
    assert episodes[0].dedupe_key == "guid-1"


@pytest.mark.asyncio
async def test_run_item_and_transcript_and_lead_uniqueness(container: AppContainer) -> None:
    run = Run(
        rss_url="https://example.com/feed.xml",
        submitted_by="Jane",
        submitted_by_email="jane@example.com",
        submitted_at=datetime.now(UTC),
    )
    await container.run_repository.create(run)
    episode = await container.episode_repository.upsert(
        Episode(
            dedupe_key="guid-2",
            title="Episode 2",
            episode_url="https://example.com/ep2",
            audio_url="https://cdn.example.com/ep2.mp3",
            published_at="2026-04-02",
            feed_url="https://example.com/feed.xml",
        ),
    )
    items = await container.run_item_repository.create_many(
        [
            RunItem(run_id=run.run_id, episode_id=episode.episode_id, title=episode.title),
        ],
    )
    assert len(items) == 1

    transcript = Transcript(
        episode_id=episode.episode_id,
        assemblyai_job_id="job-1",
        status=TranscriptStatus.COMPLETED,
        text="Transcript text",
    )
    await container.transcript_repository.create(transcript)

    lead = Lead(
        run_id=run.run_id,
        episode_id=episode.episode_id,
        guest_name="Dr. A",
        guest_company="Ascend",
        role="CMO",
        pain_point="Broken data",
        memorable_quote="Four keyholes",
        email_subject="Four keyholes",
        email_body="Email body",
        prompt_version="v1.0",
        model_name="gpt-4.1-2025-04-14",
    )
    await container.lead_repository.create(lead)

    stored_transcript = await container.transcript_repository.get_by_episode_id(episode.episode_id)
    stored_lead = await container.lead_repository.get_by_episode_id(episode.episode_id)
    assert stored_transcript is not None
    assert stored_transcript.text == "Transcript text"
    assert stored_lead is not None
    assert stored_lead.guest_name == "Dr. A"


@pytest.mark.asyncio
async def test_reclaim_stale_runs(container: AppContainer) -> None:
    stale_time = datetime.now(UTC) - timedelta(minutes=10)
    run = Run(
        rss_url="https://example.com/feed.xml",
        submitted_by="Jane",
        submitted_by_email="jane@example.com",
        submitted_at=stale_time,
        status=RunStatus.RUNNING,
        worker_id="worker-1",
        heartbeat_at=stale_time,
    )
    await container.run_repository.create(run)

    reclaimed = await container.run_repository.reclaim_stale(
        threshold=datetime.now(UTC) - timedelta(minutes=5),
        now=datetime.now(UTC),
    )
    updated = await container.run_repository.get_by_run_id(run.run_id)

    assert run.run_id in reclaimed
    assert updated is not None
    assert updated.status == RunStatus.QUEUED


@pytest.mark.asyncio
async def test_run_item_status_update(container: AppContainer) -> None:
    run = Run(
        rss_url="https://example.com/feed.xml",
        submitted_by="Jane",
        submitted_by_email="jane@example.com",
        submitted_at=datetime.now(UTC),
    )
    await container.run_repository.create(run)
    episode = await container.episode_repository.upsert(
        Episode(
            dedupe_key="guid-3",
            title="Episode 3",
            episode_url="https://example.com/ep3",
            audio_url="https://cdn.example.com/ep3.mp3",
            published_at="2026-04-03",
            feed_url="https://example.com/feed.xml",
        ),
    )
    item = RunItem(run_id=run.run_id, episode_id=episode.episode_id, title=episode.title)
    await container.run_item_repository.create_many([item])

    updated = await container.run_item_repository.update_status(
        run_item_id=item.run_item_id,
        status=RunItemStatus.TRANSCRIBING,
        now=datetime.now(UTC),
    )

    assert updated is not None
    assert updated.status == RunItemStatus.TRANSCRIBING
