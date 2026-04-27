from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient

from app.application.container import AppContainer
from app.domain.enums import LeadStatus, RunItemStatus, RunStatus, TranscriptStatus
from app.domain.models import Episode, Lead, Run, RunItem, Transcript


async def seed_dashboard_state(container: AppContainer) -> dict[str, object]:
    now = datetime.now(UTC)
    run_completed = Run(
        rss_url="https://example.com/completed.xml",
        submitted_by="Alice",
        submitted_by_email="alice@example.com",
        submitted_at=now - timedelta(hours=3),
        status=RunStatus.COMPLETED,
        total_items=1,
        completed_items=1,
        failed_items=0,
        completed_at=now - timedelta(hours=2, minutes=45),
    )
    run_partial = Run(
        rss_url="https://example.com/partial.xml",
        submitted_by="Bob",
        submitted_by_email="bob@example.com",
        submitted_at=now - timedelta(hours=2),
        status=RunStatus.PARTIAL_FAILED,
        total_items=2,
        completed_items=1,
        failed_items=1,
        error="One or more episodes failed.",
        completed_at=now - timedelta(hours=1, minutes=30),
    )
    run_queued = Run(
        rss_url="https://example.com/queued.xml",
        submitted_by="Cara",
        submitted_by_email="cara@example.com",
        submitted_at=now - timedelta(hours=1),
        status=RunStatus.QUEUED,
    )
    for run in (run_completed, run_partial, run_queued):
        await container.run_repository.create(run)

    episode_one = Episode(
        dedupe_key="guid-1",
        title="Fixing Patient Flow",
        episode_url="https://podcasts.example.com/1",
        audio_url="https://cdn.example.com/1.mp3",
        published_at="2026-04-01",
        feed_url=run_completed.rss_url,
    )
    episode_two = Episode(
        dedupe_key="guid-2",
        title="The Four Keyholes",
        episode_url="https://podcasts.example.com/2",
        audio_url="https://cdn.example.com/2.mp3",
        published_at="2026-04-02",
        feed_url=run_partial.rss_url,
    )
    episode_three = Episode(
        dedupe_key="guid-3",
        title="When Systems Drift",
        episode_url="https://podcasts.example.com/3",
        audio_url="https://cdn.example.com/3.mp3",
        published_at="2026-04-03",
        feed_url=run_partial.rss_url,
    )
    for episode in (episode_one, episode_two, episode_three):
        await container.episode_repository.upsert(episode)

    items = [
        RunItem(
            run_id=run_completed.run_id,
            episode_id=episode_one.episode_id,
            title=episode_one.title,
            status=RunItemStatus.DONE,
        ),
        RunItem(
            run_id=run_partial.run_id,
            episode_id=episode_two.episode_id,
            title=episode_two.title,
            status=RunItemStatus.REUSED,
        ),
        RunItem(
            run_id=run_partial.run_id,
            episode_id=episode_three.episode_id,
            title=episode_three.title,
            status=RunItemStatus.FAILED,
            error="AssemblyAI timeout",
        ),
    ]
    await container.run_item_repository.create_many(items)

    transcript_one = Transcript(
        episode_id=episode_one.episode_id,
        assemblyai_job_id="job-1",
        status=TranscriptStatus.COMPLETED,
        text="Transcript one",
        provider_metadata={"provider": "assemblyai"},
    )
    transcript_two = Transcript(
        episode_id=episode_two.episode_id,
        assemblyai_job_id="job-2",
        status=TranscriptStatus.COMPLETED,
        text="Transcript two",
        provider_metadata={"provider": "assemblyai"},
    )
    await container.transcript_repository.create(transcript_one)
    await container.transcript_repository.create(transcript_two)

    lead_one = Lead(
        run_id=run_completed.run_id,
        episode_id=episode_one.episode_id,
        guest_name="Dr. Sarah Chen",
        guest_company="St. Mary's Health System",
        role="Chief Medical Officer",
        pain_point="Patient throughput keeps breaking at handoff points",
        memorable_quote="We're reading the chart through four keyholes.",
        email_subject="The four keyholes you mentioned",
        email_body="Draft one",
        prompt_version="v1.0",
        model_name="gpt-4.1-2025-04-14",
        status=LeadStatus.GENERATED,
    )
    lead_two = Lead(
        run_id=run_partial.run_id,
        episode_id=episode_two.episode_id,
        guest_name="Maya Lewis",
        guest_company="Northwind Analytics",
        role="VP Operations",
        pain_point="Every service line is optimizing a different metric",
        memorable_quote="We built dashboards before we agreed on the race.",
        email_subject="The race you described",
        email_body="Draft two",
        prompt_version="v1.0",
        model_name="gpt-4.1-2025-04-14",
        status=LeadStatus.REVIEW_NEEDED,
    )
    await container.lead_repository.create(lead_one)
    await container.lead_repository.create(lead_two)

    return {
        "runs": {
            "completed": run_completed,
            "partial": run_partial,
            "queued": run_queued,
        },
        "episodes": {
            "one": episode_one,
            "two": episode_two,
            "three": episode_three,
        },
        "leads": {
            "one": lead_one,
            "two": lead_two,
        },
    }


@pytest.mark.asyncio
async def test_list_runs_supports_pagination_and_filtering(
    client: AsyncClient,
    app_container: AppContainer,
) -> None:
    seeded = await seed_dashboard_state(app_container)

    response = await client.get("/api/runs", params={"page": 1, "limit": 2})

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 3
    assert payload["page"] == 1
    assert len(payload["data"]) == 2
    assert payload["data"][0]["run_id"] == seeded["runs"]["queued"].run_id

    filtered = await client.get(
        "/api/runs",
        params={"submitted_by_email": "alice@example.com"},
    )
    assert filtered.status_code == 200
    filtered_payload = filtered.json()
    assert filtered_payload["total"] == 1
    assert filtered_payload["data"][0]["submitted_by"] == "Alice"


@pytest.mark.asyncio
async def test_dashboard_submitters_returns_distinct_users_with_run_counts(
    client: AsyncClient,
    app_container: AppContainer,
) -> None:
    await seed_dashboard_state(app_container)

    duplicate_submitter_run = Run(
        rss_url="https://example.com/completed-follow-up.xml",
        submitted_by="Alice",
        submitted_by_email="alice@example.com",
        submitted_at=datetime.now(UTC),
        status=RunStatus.COMPLETED,
    )
    await app_container.run_repository.create(duplicate_submitter_run)

    response = await client.get("/api/dashboard/submitters")

    assert response.status_code == 200
    payload = response.json()
    assert payload["data"][0]["submitted_by_email"] == "alice@example.com"
    assert payload["data"][0]["run_count"] == 2
    assert {submitter["submitted_by_email"] for submitter in payload["data"]} == {
        "alice@example.com",
        "bob@example.com",
        "cara@example.com",
    }


@pytest.mark.asyncio
async def test_get_run_detail_includes_joined_item_state(
    client: AsyncClient,
    app_container: AppContainer,
) -> None:
    seeded = await seed_dashboard_state(app_container)

    response = await client.get(f"/api/runs/{seeded['runs']['partial'].run_id}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == RunStatus.PARTIAL_FAILED.value
    assert len(payload["items"]) == 2
    reused_item = next(
        item for item in payload["items"] if item["status"] == RunItemStatus.REUSED.value
    )
    failed_item = next(
        item for item in payload["items"] if item["status"] == RunItemStatus.FAILED.value
    )
    assert reused_item["lead"]["guest_name"] == "Maya Lewis"
    assert reused_item["transcript_ready"] is True
    assert failed_item["lead"] is None
    assert failed_item["error"] == "AssemblyAI timeout"


@pytest.mark.asyncio
async def test_get_run_items_returns_paginated_data(
    client: AsyncClient,
    app_container: AppContainer,
) -> None:
    seeded = await seed_dashboard_state(app_container)

    response = await client.get(
        f"/api/runs/{seeded['runs']['partial'].run_id}/items",
        params={"page": 1, "limit": 1},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 2
    assert len(payload["data"]) == 1


@pytest.mark.asyncio
async def test_get_episode_detail_returns_transcript_and_lead_summary(
    client: AsyncClient,
    app_container: AppContainer,
) -> None:
    seeded = await seed_dashboard_state(app_container)

    response = await client.get(f"/api/episodes/{seeded['episodes']['one'].episode_id}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["title"] == "Fixing Patient Flow"
    assert payload["transcript_text"] == "Transcript one"
    assert payload["lead"]["guest_company"] == "St. Mary's Health System"


@pytest.mark.asyncio
async def test_list_and_get_leads_support_filters_and_search(
    client: AsyncClient,
    app_container: AppContainer,
) -> None:
    seeded = await seed_dashboard_state(app_container)

    filtered = await client.get(
        "/api/leads",
        params={"status": LeadStatus.REVIEW_NEEDED.value},
    )
    assert filtered.status_code == 200
    filtered_payload = filtered.json()
    assert filtered_payload["total"] == 1
    assert filtered_payload["data"][0]["guest_name"] == "Maya Lewis"

    searched = await client.get("/api/leads", params={"search": "Northwind"})
    assert searched.status_code == 200
    search_payload = searched.json()
    assert search_payload["total"] == 1
    assert search_payload["data"][0]["lead_id"] == seeded["leads"]["two"].lead_id

    detail = await client.get(f"/api/leads/{seeded['leads']['one'].lead_id}")
    assert detail.status_code == 200
    detail_payload = detail.json()
    assert detail_payload["email_subject"] == "The four keyholes you mentioned"


@pytest.mark.asyncio
async def test_dashboard_stats_return_mixed_status_counts(
    client: AsyncClient,
    app_container: AppContainer,
) -> None:
    await seed_dashboard_state(app_container)

    response = await client.get("/api/dashboard/stats")

    assert response.status_code == 200
    payload = response.json()
    assert payload["total_runs"] == 3
    assert payload["runs_by_status"][RunStatus.COMPLETED.value] == 1
    assert payload["runs_by_status"][RunStatus.PARTIAL_FAILED.value] == 1
    assert payload["runs_by_status"][RunStatus.QUEUED.value] == 1
    assert payload["total_episodes"] == 3
    assert payload["total_leads"] == 2
    assert payload["leads_by_status"][LeadStatus.GENERATED.value] == 1
    assert payload["leads_by_status"][LeadStatus.REVIEW_NEEDED.value] == 1
    assert len(payload["recent_runs"]) == 3


@pytest.mark.asyncio
async def test_detail_endpoints_return_404_for_missing_records(
    client: AsyncClient,
) -> None:
    run_response = await client.get("/api/runs/missing-run")
    episode_response = await client.get("/api/episodes/missing-episode")
    lead_response = await client.get("/api/leads/missing-lead")

    assert run_response.status_code == 404
    assert episode_response.status_code == 404
    assert lead_response.status_code == 404
