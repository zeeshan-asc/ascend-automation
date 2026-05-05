import pytest
from httpx import AsyncClient

from app.application.container import AppContainer


@pytest.mark.asyncio
async def test_signup_creates_account_sets_cookie_and_returns_token(
    client: AsyncClient,
    app_container: AppContainer,
    auth_credentials: dict[str, str],
) -> None:
    response = await client.post("/api/auth/signup", json=auth_credentials)

    assert response.status_code == 201
    payload = response.json()
    assert payload["token"]
    assert payload["token_type"] == "bearer"
    assert payload["user"]["name"] == auth_credentials["name"]
    assert payload["user"]["email"] == auth_credentials["email"]
    assert "ascend_access_token=" in response.headers["set-cookie"]
    assert "HttpOnly" in response.headers["set-cookie"]
    assert "Max-Age=315360000" in response.headers["set-cookie"]

    stored_user = await app_container.user_repository.get_by_email(auth_credentials["email"])
    assert stored_user is not None
    assert stored_user.name == auth_credentials["name"]


@pytest.mark.asyncio
async def test_signup_rejects_non_ascend_domain(client: AsyncClient) -> None:
    response = await client.post(
        "/api/auth/signup",
        json={
            "name": "Outside User",
            "email": "outside@example.com",
            "password": "Password123!",
        },
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "This email address is not allowed."


@pytest.mark.asyncio
async def test_signup_rejects_duplicate_email(
    client: AsyncClient,
    auth_credentials: dict[str, str],
) -> None:
    first = await client.post("/api/auth/signup", json=auth_credentials)
    second = await client.post("/api/auth/signup", json=auth_credentials)

    assert first.status_code == 201
    assert second.status_code == 409
    assert second.json()["detail"] == "An account with that email already exists."


@pytest.mark.asyncio
async def test_signin_rejects_invalid_password(
    client: AsyncClient,
    auth_credentials: dict[str, str],
) -> None:
    await client.post("/api/auth/signup", json=auth_credentials)
    await client.post("/api/auth/signout")

    response = await client.post(
        "/api/auth/signin",
        json={
            "email": auth_credentials["email"],
            "password": "wrong-password",
        },
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid email or password."


@pytest.mark.asyncio
async def test_signin_and_session_support_cookie_and_bearer_token(
    client: AsyncClient,
    auth_credentials: dict[str, str],
) -> None:
    signup = await client.post("/api/auth/signup", json=auth_credentials)
    signup_token = signup.json()["token"]

    cookie_session = await client.get("/api/auth/session")
    assert cookie_session.status_code == 200
    assert cookie_session.json()["user"]["email"] == auth_credentials["email"]

    client.cookies.clear()
    bearer_session = await client.get(
        "/api/auth/session",
        headers={"Authorization": f"Bearer {signup_token}"},
    )
    assert bearer_session.status_code == 200
    assert bearer_session.json()["user"]["name"] == auth_credentials["name"]

    signin = await client.post(
        "/api/auth/signin",
        json={
            "email": auth_credentials["email"],
            "password": auth_credentials["password"],
        },
    )
    assert signin.status_code == 200
    assert signin.json()["user"]["email"] == auth_credentials["email"]


@pytest.mark.asyncio
async def test_signout_revokes_existing_token(
    client: AsyncClient,
    auth_credentials: dict[str, str],
) -> None:
    signup = await client.post("/api/auth/signup", json=auth_credentials)
    token = signup.json()["token"]

    signout = await client.post("/api/auth/signout")
    assert signout.status_code == 204

    revoked = await client.get(
        "/api/auth/session",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert revoked.status_code == 401
    assert revoked.json()["detail"] == "Session is no longer valid. Sign in again."


@pytest.mark.asyncio
async def test_protected_pages_and_apis_require_authentication(client: AsyncClient) -> None:
    api_response = await client.get("/api/runs")
    health_response = await client.get("/health")
    landing_response = await client.get("/", follow_redirects=False)
    dashboard_response = await client.get("/dashboard", follow_redirects=False)
    auth_page_response = await client.get("/auth")

    assert api_response.status_code == 401
    assert health_response.status_code == 401
    assert landing_response.status_code == 303
    assert landing_response.headers["location"] == "/auth?next=%2F"
    assert dashboard_response.status_code == 303
    assert dashboard_response.headers["location"] == "/auth?next=%2Fdashboard"
    assert auth_page_response.status_code == 200
    assert "<!doctype html" in auth_page_response.text.lower()


@pytest.mark.asyncio
async def test_authenticated_user_is_redirected_away_from_auth_page(
    authenticated_client: AsyncClient,
) -> None:
    response = await authenticated_client.get("/auth", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/"
