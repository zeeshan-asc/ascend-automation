import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_landing_page_serves_fastapi_submission_flow(client: AsyncClient) -> None:
    response = await client.get("/")

    assert response.status_code == 200
    assert "Queue outreach run" in response.text
    assert "Open shared dashboard" in response.text
    assert 'href="/dashboard"' in response.text
    assert "/api/submissions" in response.text
    assert "Shared RSS queue + lead drafting" in response.text
    assert "hook.eu1.make.com" not in response.text
    assert "Make.com" not in response.text


@pytest.mark.asyncio
async def test_dashboard_page_serves_shared_board_ui(client: AsyncClient) -> None:
    response = await client.get("/dashboard")

    assert response.status_code == 200
    assert "Shared run board" in response.text
    assert "/api/dashboard/stats" in response.text
    assert "/api/dashboard/submitters" in response.text
    assert "/api/runs/" in response.text
    assert "Lead inspector" in response.text
    assert "expand the transcript preview" in response.text
    assert "transcript-shell" in response.text
    assert 'id="detailLoader"' in response.text
    assert "Loading episode" in response.text
    assert 'id="submitterFilter"' in response.text
    assert "repeat(auto-fit, minmax(200px, 1fr))" in response.text
    assert "overflow-wrap: anywhere" in response.text
