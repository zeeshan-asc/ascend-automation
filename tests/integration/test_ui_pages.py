import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_auth_page_serves_signup_and_signin_flow(client: AsyncClient) -> None:
    response = await client.get("/auth")

    assert response.status_code == 200
    assert "Ascend Outreach Engine" in response.text
    assert "Create account" in response.text
    assert "Sign in" in response.text
    assert "@ascendanalytics.co" in response.text
    assert "/api/auth/signup" in response.text
    assert "/api/auth/signin" in response.text
    assert "hook.eu1.make.com" not in response.text
    assert "Make.com" not in response.text


@pytest.mark.asyncio
async def test_landing_page_requires_authentication(client: AsyncClient) -> None:
    response = await client.get("/", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/auth?next=%2F"


@pytest.mark.asyncio
async def test_landing_page_serves_fastapi_submission_flow(
    authenticated_client: AsyncClient,
) -> None:
    response = await authenticated_client.get("/")

    assert response.status_code == 200
    assert "Queue outreach run" in response.text
    assert "Ascend Outreach Engine" in response.text
    assert "Shared dashboard" in response.text
    assert "Records workspace" in response.text
    assert 'href="/dashboard"' in response.text
    assert 'href="/records"' in response.text
    assert 'aria-current="page" href="/"' in response.text
    assert "/api/submissions" in response.text
    assert "/api/auth/session" in response.text
    assert "/api/auth/signout" in response.text
    assert 'id="rssFieldError"' in response.text
    assert 'id="sessionNameValue"' in response.text
    assert 'id="sessionEmailValue"' in response.text
    assert "Authenticated operator" in response.text
    assert "@ascendanalytics.co only" in response.text
    assert "hook.eu1.make.com" not in response.text
    assert "Make.com" not in response.text


@pytest.mark.asyncio
async def test_dashboard_page_serves_shared_board_ui(authenticated_client: AsyncClient) -> None:
    response = await authenticated_client.get("/dashboard")

    assert response.status_code == 200
    assert "Ascend Outreach Engine" in response.text
    assert "Queue run" in response.text
    assert 'aria-current="page" href="/dashboard"' in response.text
    assert "Shared run board" in response.text
    assert "/api/dashboard/stats" in response.text
    assert "/api/dashboard/submitters" in response.text
    assert "/api/runs/" in response.text
    assert "/api/runs/items/" in response.text
    assert "/transcript" in response.text
    assert "/rewrite" in response.text
    assert 'id="previousRunsPageButton"' in response.text
    assert 'id="nextRunsPageButton"' in response.text
    assert 'id="runsPageLabel"' in response.text
    assert "const RUNS_PER_PAGE = 5;" in response.text
    assert "Lead inspector" in response.text
    assert "expand the transcript preview" in response.text
    assert "transcript-shell" in response.text
    assert "Rewrite draft" in response.text
    assert "rewriteInstruction" in response.text
    assert "Queue must be idle before retrying this episode." in response.text
    assert "Retrying..." in response.text
    assert 'id="detailLoader"' in response.text
    assert "Loading episode" in response.text
    assert 'id="submitterFilter"' in response.text
    assert 'id="signOutButton"' in response.text
    assert 'id="sessionBadge"' in response.text
    assert "/api/auth/session" in response.text
    assert "/api/auth/signout" in response.text
    assert "repeat(auto-fit, minmax(200px, 1fr))" in response.text
    assert "overflow-wrap: anywhere" in response.text
    assert "Records workspace" in response.text


@pytest.mark.asyncio
async def test_records_page_serves_workspace_ui(authenticated_client: AsyncClient) -> None:
    response = await authenticated_client.get("/records")

    assert response.status_code == 200
    assert "Ascend Outreach Engine" in response.text
    assert "Shared dashboard" in response.text
    assert 'aria-current="page" href="/records"' in response.text
    assert "Lead records workspace" in response.text
    assert "/api/records?" in response.text
    assert "/api/records/export" in response.text
    assert "/api/leads/" in response.text
    assert 'id="submitterFilter"' in response.text
    assert 'id="outreachFilter"' in response.text
    assert "Export CSV" in response.text
    assert 'id="signOutButton"' in response.text
    assert 'id="sessionBadge"' in response.text
    assert "/api/auth/session" in response.text
    assert "/api/auth/signout" in response.text
