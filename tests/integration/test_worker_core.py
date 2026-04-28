import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from app.application.container import AppContainer
from app.config import Settings
from app.domain.enums import RunItemStatus, RunStatus, SourceKind, TranscriptStatus
from app.domain.errors import FeedFetchError
from app.domain.models import LeadDraft, ParsedEpisode, Run, TranscriptResult
from app.worker.orchestrator import PipelineOrchestrator
from app.worker.service import WorkerService
from tests.helpers.async_mongomock import FakeMongoManager


class FakeRSSProvider:
    def __init__(
        self,
        feeds: dict[str, list[ParsedEpisode]],
        *,
        failing_urls: dict[str, FeedFetchError] | None = None,
    ) -> None:
        self._feeds = feeds
        self._failing_urls = failing_urls or {}

    async def fetch_episodes(self, rss_url: str, max_results: int) -> list[ParsedEpisode]:
        if rss_url in self._failing_urls:
            raise self._failing_urls[rss_url]
        return self._feeds[rss_url][:max_results]

    async def resolve_source(
        self,
        *,
        source_url: str,
        source_kind: SourceKind,
        max_results: int,
    ) -> list[ParsedEpisode]:
        return await self.fetch_episodes(source_url, max_results)


class FakeAssemblyAIProvider:
    def __init__(self, *, fail_on_audio: set[str] | None = None) -> None:
        self.fail_on_audio = fail_on_audio or set()
        self.submit_calls = 0
        self.poll_calls = 0

    async def submit_transcription(self, audio_url: str) -> str:
        self.submit_calls += 1
        if audio_url in self.fail_on_audio:
            raise RuntimeError("assembly submit failed")
        await asyncio.sleep(0)
        return f"job:{audio_url}"

    async def poll_transcription(self, job_id: str) -> TranscriptResult:
        self.poll_calls += 1
        audio_url = job_id.split("job:", 1)[1]
        return TranscriptResult(
            assemblyai_job_id=job_id,
            status=TranscriptStatus.COMPLETED,
            text=f"Transcript for {audio_url}",
            provider_metadata={"job_id": job_id},
        )


class FakeOpenAIProvider:
    def __init__(self, *, fail_on_text: set[str] | None = None) -> None:
        self.fail_on_text = fail_on_text or set()
        self.generate_calls = 0
        self.prompt_version = "v1.0-test"
        self.model = "gpt-4.1-2025-04-14"

    async def generate_lead_draft(
        self,
        *,
        transcript_text: str,
        tone_instructions: str | None,
    ) -> LeadDraft:
        self.generate_calls += 1
        if transcript_text in self.fail_on_text:
            raise RuntimeError("openai failed")
        return LeadDraft(
            guest_name="Dr. Jane Doe",
            guest_company="Health System",
            role="CMO",
            pain_point="Operational silos",
            memorable_quote="Four keyholes",
            email_subject="The four keyholes you mentioned",
            email_body=f"Tone: {tone_instructions or 'none'} | Transcript: {transcript_text[:30]}",
        )


def build_episode(feed_url: str, number: int) -> ParsedEpisode:
    return ParsedEpisode(
        guid=f"{feed_url}-guid-{number}",
        title=f"Episode {number}",
        episode_url=f"https://example.com/{number}",
        audio_url=f"https://cdn.example.com/{feed_url.rsplit('/', 1)[-1]}-{number}.mp3",
        published_at="2026-04-01",
        source_url=feed_url,
        source_kind=SourceKind.RSS_FEED,
        dedupe_key=f"{feed_url}-guid-{number}",
    )


async def build_worker(
    test_settings: Settings,
    *,
    feeds: dict[str, list[ParsedEpisode]],
    failing_urls: dict[str, FeedFetchError] | None = None,
    assembly_provider: FakeAssemblyAIProvider | None = None,
    openai_provider: FakeOpenAIProvider | None = None,
) -> tuple[AppContainer, WorkerService]:
    container = await AppContainer.build(settings=test_settings, mongo_manager=FakeMongoManager())
    orchestrator = PipelineOrchestrator(
        settings=test_settings,
        run_repository=container.run_repository,
        episode_repository=container.episode_repository,
        run_item_repository=container.run_item_repository,
        transcript_repository=container.transcript_repository,
        lead_repository=container.lead_repository,
        source_resolver=FakeRSSProvider(feeds, failing_urls=failing_urls),
        assemblyai_provider=assembly_provider or FakeAssemblyAIProvider(),
        openai_provider=openai_provider or FakeOpenAIProvider(),
    )
    worker = WorkerService(
        settings=test_settings,
        worker_id="worker-1",
        run_repository=container.run_repository,
        orchestrator=orchestrator,
    )
    return container, worker


@pytest.mark.asyncio
async def test_worker_processes_run_successfully(test_settings: Settings) -> None:
    feed_url = "https://example.com/feed-success.xml"
    container, worker = await build_worker(
        test_settings,
        feeds={feed_url: [build_episode(feed_url, 1), build_episode(feed_url, 2)]},
    )
    run = Run(
        rss_url=feed_url,
        submitted_by="Jane",
        submitted_by_email="jane@example.com",
        submitted_at=datetime.now(UTC),
    )
    await container.run_repository.create(run)

    processed = await worker.process_next_available()
    items = await container.run_item_repository.list_all_by_run_id(run.run_id)

    assert processed is not None
    assert processed.status == RunStatus.COMPLETED
    assert len(items) == 2
    assert all(item.status in {"done", "reused"} for item in items)


@pytest.mark.asyncio
async def test_worker_marks_partial_failure_when_one_episode_fails(test_settings: Settings) -> None:
    feed_url = "https://example.com/feed-partial.xml"
    bad_episode = build_episode(feed_url, 2)
    assembly = FakeAssemblyAIProvider(fail_on_audio={bad_episode.audio_url})
    container, worker = await build_worker(
        test_settings,
        feeds={feed_url: [build_episode(feed_url, 1), bad_episode]},
        assembly_provider=assembly,
    )
    run = Run(
        rss_url=feed_url,
        submitted_by="Jane",
        submitted_by_email="jane@example.com",
        submitted_at=datetime.now(UTC),
    )
    await container.run_repository.create(run)

    processed = await worker.process_next_available()

    assert processed is not None
    assert processed.status == RunStatus.PARTIAL_FAILED
    assert processed.failed_items == 1


@pytest.mark.asyncio
async def test_worker_retry_processes_only_target_failed_item(test_settings: Settings) -> None:
    feed_url = "https://example.com/feed-retry.xml"
    episode_one = build_episode(feed_url, 1)
    episode_two = build_episode(feed_url, 2)
    failing_openai = FakeOpenAIProvider(
        fail_on_text={f"Transcript for {episode_two.audio_url}"},
    )
    container, failing_worker = await build_worker(
        test_settings,
        feeds={feed_url: [episode_one, episode_two]},
        openai_provider=failing_openai,
    )
    run = Run(
        rss_url=feed_url,
        submitted_by="Jane",
        submitted_by_email="jane@example.com",
        submitted_at=datetime.now(UTC),
    )
    await container.run_repository.create(run)

    initial_result = await failing_worker.process_next_available()

    assert initial_result is not None
    assert initial_result.status == RunStatus.PARTIAL_FAILED
    initial_items = await container.run_item_repository.list_all_by_run_id(run.run_id)
    failed_item = next(item for item in initial_items if item.status == RunItemStatus.FAILED)

    await container.run_item_repository.reset_for_retry(
        run_item_id=failed_item.run_item_id,
        now=datetime.now(UTC),
    )
    await container.run_repository.queue_retry(
        run_id=run.run_id,
        retry_run_item_ids=[failed_item.run_item_id],
        now=datetime.now(UTC),
    )

    retry_assembly = FakeAssemblyAIProvider()
    retry_openai = FakeOpenAIProvider()
    retry_orchestrator = PipelineOrchestrator(
        settings=test_settings,
        run_repository=container.run_repository,
        episode_repository=container.episode_repository,
        run_item_repository=container.run_item_repository,
        transcript_repository=container.transcript_repository,
        lead_repository=container.lead_repository,
        source_resolver=FakeRSSProvider({feed_url: [episode_one, episode_two]}),
        assemblyai_provider=retry_assembly,
        openai_provider=retry_openai,
    )
    retry_worker = WorkerService(
        settings=test_settings,
        worker_id="worker-retry",
        run_repository=container.run_repository,
        orchestrator=retry_orchestrator,
    )

    retried_run = await retry_worker.process_next_available()

    assert retried_run is not None
    assert retried_run.status == RunStatus.COMPLETED
    assert retried_run.total_items == 2
    assert retried_run.completed_items == 2
    assert retried_run.failed_items == 0
    assert retry_assembly.submit_calls == 0
    assert retry_openai.generate_calls == 1
    final_items = await container.run_item_repository.list_all_by_run_id(run.run_id)
    retried_item = next(item for item in final_items if item.run_item_id == failed_item.run_item_id)
    untouched_item = next(
        item for item in final_items if item.run_item_id != failed_item.run_item_id
    )
    assert retried_item.status in {RunItemStatus.DONE, RunItemStatus.REUSED}
    assert untouched_item.status == RunItemStatus.DONE


@pytest.mark.asyncio
async def test_worker_marks_failed_when_all_items_fail(test_settings: Settings) -> None:
    feed_url = "https://example.com/feed-failed.xml"
    episode_one = build_episode(feed_url, 1)
    episode_two = build_episode(feed_url, 2)
    assembly = FakeAssemblyAIProvider(fail_on_audio={episode_one.audio_url, episode_two.audio_url})
    container, worker = await build_worker(
        test_settings,
        feeds={feed_url: [episode_one, episode_two]},
        assembly_provider=assembly,
    )
    run = Run(
        rss_url=feed_url,
        submitted_by="Jane",
        submitted_by_email="jane@example.com",
        submitted_at=datetime.now(UTC),
    )
    await container.run_repository.create(run)

    processed = await worker.process_next_available()

    assert processed is not None
    assert processed.status == RunStatus.FAILED
    assert processed.completed_items == 0


@pytest.mark.asyncio
async def test_worker_still_fails_cleanly_when_feed_disappears_after_submission(
    test_settings: Settings,
) -> None:
    feed_url = "https://example.com/feed-disappeared.xml"
    container, worker = await build_worker(
        test_settings,
        feeds={},
        failing_urls={
            feed_url: FeedFetchError(
                "The RSS feed could not be reached. Check the URL and try again.",
                reason_code="feed_unreachable",
            ),
        },
    )
    run = Run(
        rss_url=feed_url,
        submitted_by="Jane",
        submitted_by_email="jane@example.com",
        submitted_at=datetime.now(UTC),
    )
    await container.run_repository.create(run)

    processed = await worker.process_next_available()

    assert processed is not None
    assert processed.status == RunStatus.FAILED
    assert processed.error == "The RSS feed could not be reached. Check the URL and try again."


@pytest.mark.asyncio
async def test_duplicate_runs_reuse_canonical_episode_processing(test_settings: Settings) -> None:
    feed_url = "https://example.com/feed-duplicate.xml"
    shared_episode = build_episode(feed_url, 1)
    assembly = FakeAssemblyAIProvider()
    openai_provider = FakeOpenAIProvider()
    container = await AppContainer.build(settings=test_settings, mongo_manager=FakeMongoManager())
    orchestrator_one = PipelineOrchestrator(
        settings=test_settings,
        run_repository=container.run_repository,
        episode_repository=container.episode_repository,
        run_item_repository=container.run_item_repository,
        transcript_repository=container.transcript_repository,
        lead_repository=container.lead_repository,
        source_resolver=FakeRSSProvider({feed_url: [shared_episode]}),
        assemblyai_provider=assembly,
        openai_provider=openai_provider,
    )
    orchestrator_two = PipelineOrchestrator(
        settings=test_settings,
        run_repository=container.run_repository,
        episode_repository=container.episode_repository,
        run_item_repository=container.run_item_repository,
        transcript_repository=container.transcript_repository,
        lead_repository=container.lead_repository,
        source_resolver=FakeRSSProvider({feed_url: [shared_episode]}),
        assemblyai_provider=assembly,
        openai_provider=openai_provider,
    )
    worker_one = WorkerService(
        settings=test_settings,
        worker_id="worker-1",
        run_repository=container.run_repository,
        orchestrator=orchestrator_one,
    )
    worker_two = WorkerService(
        settings=test_settings,
        worker_id="worker-2",
        run_repository=container.run_repository,
        orchestrator=orchestrator_two,
    )
    runs = [
        Run(
            rss_url=feed_url,
            submitted_by=f"User {index}",
            submitted_by_email=f"user{index}@example.com",
            submitted_at=datetime.now(UTC),
        )
        for index in range(2)
    ]
    for run in runs:
        await container.run_repository.create(run)

    await asyncio.gather(worker_one.process_next_available(), worker_two.process_next_available())

    assert assembly.submit_calls == 1
    assert openai_provider.generate_calls == 1
    stored_lead = await container.lead_repository.list_leads(page=1, limit=10)
    assert stored_lead[1] == 1


@pytest.mark.asyncio
async def test_worker_reclaims_stale_runs_and_completes_them(test_settings: Settings) -> None:
    feed_url = "https://example.com/feed-stale.xml"
    container, worker = await build_worker(
        test_settings,
        feeds={feed_url: [build_episode(feed_url, 1)]},
    )
    stale_run = Run(
        rss_url=feed_url,
        submitted_by="Jane",
        submitted_by_email="jane@example.com",
        submitted_at=datetime.now(UTC) - timedelta(minutes=10),
        status=RunStatus.RUNNING,
        worker_id="worker-old",
        heartbeat_at=datetime.now(UTC) - timedelta(minutes=10),
    )
    await container.run_repository.create(stale_run)

    reclaimed = await worker.reclaim_stale_runs()
    processed = await worker.process_next_available()

    assert stale_run.run_id in reclaimed
    assert processed is not None
    assert processed.status == RunStatus.COMPLETED


@pytest.mark.asyncio
async def test_worker_handles_eight_simultaneous_runs(test_settings: Settings) -> None:
    feeds = {
        f"https://example.com/feed-{index}.xml": [
            build_episode(f"https://example.com/feed-{index}.xml", 1),
        ]
        for index in range(8)
    }
    container = await AppContainer.build(settings=test_settings, mongo_manager=FakeMongoManager())
    assembly = FakeAssemblyAIProvider()
    openai_provider = FakeOpenAIProvider()
    workers = []
    for index in range(3):
        orchestrator = PipelineOrchestrator(
            settings=test_settings,
            run_repository=container.run_repository,
            episode_repository=container.episode_repository,
            run_item_repository=container.run_item_repository,
            transcript_repository=container.transcript_repository,
            lead_repository=container.lead_repository,
            source_resolver=FakeRSSProvider(feeds),
            assemblyai_provider=assembly,
            openai_provider=openai_provider,
        )
        workers.append(
            WorkerService(
                settings=test_settings,
                worker_id=f"worker-{index}",
                run_repository=container.run_repository,
                orchestrator=orchestrator,
            ),
        )

    for index, feed_url in enumerate(feeds):
        await container.run_repository.create(
            Run(
                rss_url=feed_url,
                submitted_by=f"User {index}",
                submitted_by_email=f"user{index}@example.com",
                submitted_at=datetime.now(UTC),
            ),
        )

    await asyncio.gather(*(worker.run_until_empty(idle_cycles=2) for worker in workers))
    runs, total = await container.run_repository.list_runs(page=1, limit=20)

    assert total == 8
    assert all(run.status == RunStatus.COMPLETED for run in runs)
