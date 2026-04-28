import pytest
from httpx import AsyncClient

from app.application.container import AppContainer
from app.domain.enums import OutreachStatus
from tests.integration.test_dashboard_api import seed_dashboard_state


@pytest.mark.asyncio
async def test_list_records_returns_joined_rows_and_supports_filters(
    authenticated_client: AsyncClient,
    app_container: AppContainer,
) -> None:
    await seed_dashboard_state(app_container)

    response = await authenticated_client.get("/api/records", params={"page": 1, "limit": 10})

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 3
    assert len(payload["data"]) == 3

    first_row = payload["data"][0]
    assert first_row["submitted_by"] == "Bob"
    assert first_row["source_url"] == "https://example.com/partial.xml"
    assert first_row["source_kind"] == "rss_feed"

    outreach_filtered = await authenticated_client.get(
        "/api/records",
        params={"page": 1, "limit": 10, "outreach_status": OutreachStatus.NOT_CONTACTED.value},
    )
    assert outreach_filtered.status_code == 200
    outreach_payload = outreach_filtered.json()
    assert outreach_payload["total"] == 2
    assert all(
        row["outreach_status"] == OutreachStatus.NOT_CONTACTED.value
        for row in outreach_payload["data"]
    )

    submitter_filtered = await authenticated_client.get(
        "/api/records",
        params={"page": 1, "limit": 10, "submitted_by_email": "bob@example.com"},
    )
    assert submitter_filtered.status_code == 200
    submitter_payload = submitter_filtered.json()
    assert submitter_payload["total"] == 2
    assert {row["submitted_by_email"] for row in submitter_payload["data"]} == {"bob@example.com"}
    assert any(row["lead_id"] is None for row in submitter_payload["data"])


@pytest.mark.asyncio
async def test_patch_lead_outreach_updates_record_rows(
    authenticated_client: AsyncClient,
    app_container: AppContainer,
) -> None:
    seeded = await seed_dashboard_state(app_container)

    response = await authenticated_client.patch(
        f"/api/leads/{seeded['leads']['one'].lead_id}/outreach",
        json={"outreach_status": OutreachStatus.CONTACTED.value},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["lead_id"] == seeded["leads"]["one"].lead_id
    assert payload["outreach_status"] == OutreachStatus.CONTACTED.value

    updated_detail = await authenticated_client.get(f"/api/leads/{seeded['leads']['one'].lead_id}")
    assert updated_detail.status_code == 200
    assert updated_detail.json()["outreach_status"] == OutreachStatus.CONTACTED.value

    filtered = await authenticated_client.get(
        "/api/records",
        params={"page": 1, "limit": 10, "outreach_status": OutreachStatus.CONTACTED.value},
    )
    assert filtered.status_code == 200
    filtered_payload = filtered.json()
    assert filtered_payload["total"] == 1
    assert filtered_payload["data"][0]["lead_id"] == seeded["leads"]["one"].lead_id


@pytest.mark.asyncio
async def test_export_records_returns_csv_for_current_filter(
    authenticated_client: AsyncClient,
    app_container: AppContainer,
) -> None:
    await seed_dashboard_state(app_container)

    response = await authenticated_client.get(
        "/api/records/export",
        params={"submitted_by_email": "alice@example.com"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "attachment; filename=" in response.headers["content-disposition"]
    assert "submitted_by,submitted_by_email,submitted_at,source_url,source_kind" in response.text
    assert "Alice" in response.text
    assert "alice@example.com" in response.text
    assert "https://example.com/completed.xml" in response.text
    assert "Dr. Sarah Chen" in response.text


@pytest.mark.asyncio
async def test_patch_lead_outreach_returns_404_for_missing_lead(
    authenticated_client: AsyncClient,
) -> None:
    response = await authenticated_client.patch(
        "/api/leads/missing-lead/outreach",
        json={"outreach_status": OutreachStatus.CONTACTED.value},
    )

    assert response.status_code == 404
