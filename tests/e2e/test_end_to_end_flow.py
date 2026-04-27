import asyncio
from datetime import UTC, datetime

import pytest
from httpx import AsyncClient

from app.application.container import AppContainer
from app.config import Settings
from app.domain.enums import TranscriptStatus
from app.domain.models import LeadDraft, ParsedEpisode, TranscriptResult
from app.worker.orchestrator import PipelineOrchestrator
from app.worker.service import WorkerService


class FakeRSSProvider:
    def __init__(self, feeds: dict[str, list[ParsedEpisode]]) -> None:
        self._feeds = feeds

    async def fetch_episodes(self, rss_url: str, max_results: int) -> list[ParsedEpisode]:
        return self._feeds[rss_url][:max_results]


class CountingAssemblyAIProvider:
    def __init__(self) -> None:
        self.submit_calls = 0
        self.poll_calls = 0

    async def submit_transcription(self, audio_url: str) -> str:
        self.submit_calls += 1
        await asyncio.sleep(0)
        return f"job:{audio_url}"

    async def poll_transcription(self, job_id: str) -> TranscriptResult:
        self.poll_calls += 1
        return TranscriptResult(
            assemblyai_job_id=job_id,
            status=TranscriptStatus.COMPLETED,
            text=f"Transcript for {job_id}",
            provider_metadata={"job_id": job_id},
        )


class CountingOpenAIProvider:
    def __init__(self) -> None:
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
        return LeadDraft(
            guest_name="Dr. Jane Doe",
            guest_company="Northwind Health",
            role="CMO",
            pain_point="Fragmented patient flow",
            memorable_quote="We still see the chart through four keyholes.",
            email_subject="The four keyholes you mentioned",
            email_body=f"Tone={tone_instructions or 'default'} | Source={transcript_text[:24]}",
        )


def build_episode(feed_url: str, number: int) -> ParsedEpisode:
    return ParsedEpisode(
        guid=f"{feed_url}-guid-{number}",
        title=f"Episode {number}",
        episode_url=f"https://podcasts.example.com/{number}",
        audio_url=f"https://cdn.example.com/{number}.mp3",
        published_at="2026-04-01",
        feed_url=feed_url,
        dedupe_key=f"{feed_url}-guid-{number}",
    )


def build_worker(
    test_settings: Settings,
    app_container: AppContainer,
    *,
    feeds: dict[str, list[ParsedEpisode]],
    assembly_provider: CountingAssemblyAIProvider,
    openai_provider: CountingOpenAIProvider,
) -> WorkerService:
    orchestrator = PipelineOrchestrator(
        settings=test_settings,
        run_repository=app_container.run_repository,
        episode_repository=app_container.episode_repository,
        run_item_repository=app_container.run_item_repository,
        transcript_repository=app_container.transcript_repository,
        lead_repository=app_container.lead_repository,
        rss_provider=FakeRSSProvider(feeds),
        assemblyai_provider=assembly_provider,
        openai_provider=openai_provider,
    )
    return WorkerService(
        settings=test_settings,
        worker_id="worker-e2e",
        run_repository=app_container.run_repository,
        orchestrator=orchestrator,
    )


@pytest.mark.asyncio
async def test_submission_to_dashboard_end_to_end(
    client: AsyncClient,
    app_container: AppContainer,
    test_settings: Settings,
) -> None:
    feed_url = "https://example.com/e2e-feed.xml"
    assembly_provider = CountingAssemblyAIProvider()
    openai_provider = CountingOpenAIProvider()
    worker = build_worker(
        test_settings,
        app_container,
        feeds={feed_url: [build_episode(feed_url, 1)]},
        assembly_provider=assembly_provider,
        openai_provider=openai_provider,
    )

    submission = await client.post(
        "/api/submissions",
        json={
            "user_name": "Ava",
            "user_email": "ava@example.com",
            "rss_url": feed_url,
            "tone_instructions": "Keep it direct and peer-like.",
            "submitted_at": datetime.now(UTC).isoformat(),
        },
    )
    assert submission.status_code == 202
    run_id = submission.json()["run_id"]

    processed = await worker.process_next_available()
    assert processed is not None
    assert assembly_provider.submit_calls == 1
    assert openai_provider.generate_calls == 1

    run_response = await client.get(f"/api/runs/{run_id}")
    assert run_response.status_code == 200
    run_payload = run_response.json()
    assert run_payload["status"] == "completed"
    assert len(run_payload["items"]) == 1

    lead_id = run_payload["items"][0]["lead"]["lead_id"]
    lead_response = await client.get(f"/api/leads/{lead_id}")
    assert lead_response.status_code == 200
    assert lead_response.json()["guest_name"] == "Dr. Jane Doe"

    episode_id = run_payload["items"][0]["episode_id"]
    episode_response = await client.get(f"/api/episodes/{episode_id}")
    assert episode_response.status_code == 200
    assert episode_response.json()["transcript_status"] == "completed"

    transcript_response = await client.get(f"/api/episodes/{episode_id}/transcript")
    assert transcript_response.status_code == 200
    assert "Transcript for job:" in transcript_response.json()["transcript_text"]


@pytest.mark.asyncio
async def test_duplicate_submissions_share_canonical_processing(
    client: AsyncClient,
    app_container: AppContainer,
    test_settings: Settings,
) -> None:
    feed_url = "https://example.com/e2e-duplicate.xml"
    shared_episode = build_episode(feed_url, 1)
    assembly_provider = CountingAssemblyAIProvider()
    openai_provider = CountingOpenAIProvider()
    worker_one = build_worker(
        test_settings,
        app_container,
        feeds={feed_url: [shared_episode]},
        assembly_provider=assembly_provider,
        openai_provider=openai_provider,
    )
    worker_two = build_worker(
        test_settings,
        app_container,
        feeds={feed_url: [shared_episode]},
        assembly_provider=assembly_provider,
        openai_provider=openai_provider,
    )

    for name in ("Ava", "Ben"):
        response = await client.post(
            "/api/submissions",
            json={
                "user_name": name,
                "user_email": f"{name.lower()}@example.com",
                "rss_url": feed_url,
                "tone_instructions": None,
                "submitted_at": datetime.now(UTC).isoformat(),
            },
        )
        assert response.status_code == 202

    await asyncio.gather(
        worker_one.run_until_empty(idle_cycles=2),
        worker_two.run_until_empty(idle_cycles=2),
    )

    leads_response = await client.get("/api/leads")
    runs_response = await client.get("/api/runs")

    assert leads_response.status_code == 200
    assert runs_response.status_code == 200
    assert leads_response.json()["total"] == 1
    assert runs_response.json()["total"] == 2
    assert assembly_provider.submit_calls == 1
    assert openai_provider.generate_calls == 1
