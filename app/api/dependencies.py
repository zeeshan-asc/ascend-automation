from typing import cast

from fastapi import HTTPException, Request, status

from app.application.auth import AuthService
from app.application.container import AppContainer
from app.application.dashboard import DashboardQueryService
from app.application.lead_rewrite import LeadRewriteService
from app.application.records import RecordsWorkspaceService
from app.application.run_item_retry import RunItemRetryService
from app.config import Settings
from app.domain.errors import AuthenticationError
from app.domain.models import AuthenticatedUser


def get_container(request: Request) -> AppContainer:
    return cast(AppContainer, request.app.state.container)


def get_settings_from_request(request: Request) -> Settings:
    return cast(Settings, request.app.state.settings)


def get_auth_service(request: Request) -> AuthService:
    container = get_container(request)
    return AuthService(
        user_repository=container.user_repository,
        password_hasher=container.password_hasher,
        token_manager=container.token_manager,
        allowed_email_domain=container.settings.auth_allowed_email_domain,
    )


def extract_auth_token(request: Request) -> str | None:
    authorization_header = request.headers.get("Authorization")
    if authorization_header:
        scheme, _, credentials = authorization_header.partition(" ")
        if scheme.lower() == "bearer" and credentials.strip():
            return credentials.strip()

    settings = get_settings_from_request(request)
    cookie_token = request.cookies.get(settings.auth_cookie_name)
    if cookie_token:
        return cookie_token
    return None


async def authenticate_request_user(request: Request) -> AuthenticatedUser:
    cached_user = getattr(request.state, "current_user", None)
    if isinstance(cached_user, AuthenticatedUser):
        return cached_user

    token = extract_auth_token(request)
    if token is None:
        raise AuthenticationError("Not authenticated.")

    service = get_auth_service(request)
    current_user = await service.authenticate_token(token)
    request.state.current_user = current_user
    return current_user


async def get_current_user(request: Request) -> AuthenticatedUser:
    try:
        return await authenticate_request_user(request)
    except AuthenticationError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


def get_dashboard_service(request: Request) -> DashboardQueryService:
    container = get_container(request)
    return DashboardQueryService(
        run_repository=container.run_repository,
        episode_repository=container.episode_repository,
        run_item_repository=container.run_item_repository,
        transcript_repository=container.transcript_repository,
        lead_repository=container.lead_repository,
    )


def get_records_service(request: Request) -> RecordsWorkspaceService:
    container = get_container(request)
    return RecordsWorkspaceService(
        run_repository=container.run_repository,
        episode_repository=container.episode_repository,
        run_item_repository=container.run_item_repository,
        lead_repository=container.lead_repository,
    )


def get_lead_rewrite_service(request: Request) -> LeadRewriteService:
    container = get_container(request)
    return LeadRewriteService(
        lead_repository=container.lead_repository,
        transcript_repository=container.transcript_repository,
        openai_provider=container.openai_provider,
    )


def get_run_item_retry_service(request: Request) -> RunItemRetryService:
    container = get_container(request)
    return RunItemRetryService(
        run_repository=container.run_repository,
        run_item_repository=container.run_item_repository,
    )
