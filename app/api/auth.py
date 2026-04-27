from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from app.api.dependencies import get_auth_service, get_current_user, get_settings_from_request
from app.application.auth import (
    AuthService,
    AuthSessionResponse,
    AuthSuccessResponse,
    AuthUserResponse,
    SignInRequest,
    SignUpRequest,
)
from app.domain.errors import AuthenticationError, AuthorizationError, DuplicateResourceError
from app.domain.models import AuthenticatedUser

router = APIRouter(prefix="/api/auth", tags=["auth"])
AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]


def _set_auth_cookie(response: Response, request: Request, *, token: str) -> None:
    settings = get_settings_from_request(request)
    response.set_cookie(
        key=settings.auth_cookie_name,
        value=token,
        max_age=settings.auth_cookie_max_age_seconds,
        httponly=True,
        samesite="lax",
        secure=settings.auth_cookie_secure,
        path="/",
    )


def _clear_auth_cookie(response: Response, request: Request) -> None:
    settings = get_settings_from_request(request)
    response.delete_cookie(
        key=settings.auth_cookie_name,
        httponly=True,
        samesite="lax",
        secure=settings.auth_cookie_secure,
        path="/",
    )


def _build_session_response(user: AuthenticatedUser) -> AuthSessionResponse:
    return AuthSessionResponse(
        user=AuthUserResponse(
            user_id=user.user_id,
            name=user.name,
            email=user.email,
        ),
    )


@router.post("/signup", response_model=AuthSuccessResponse, status_code=status.HTTP_201_CREATED)
async def sign_up(
    payload: SignUpRequest,
    request: Request,
    response: Response,
    service: AuthServiceDep,
) -> AuthSuccessResponse:
    try:
        auth_result = await service.sign_up(payload)
    except DuplicateResourceError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except AuthorizationError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc

    _set_auth_cookie(response, request, token=auth_result.token)
    return auth_result


@router.post("/signin", response_model=AuthSuccessResponse)
async def sign_in(
    payload: SignInRequest,
    request: Request,
    response: Response,
    service: AuthServiceDep,
) -> AuthSuccessResponse:
    try:
        auth_result = await service.sign_in(payload)
    except AuthorizationError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except AuthenticationError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    _set_auth_cookie(response, request, token=auth_result.token)
    return auth_result


@router.post("/signout", status_code=status.HTTP_204_NO_CONTENT)
async def sign_out(
    request: Request,
    response: Response,
    service: AuthServiceDep,
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
) -> Response:
    await service.sign_out(user_id=current_user.user_id)
    _clear_auth_cookie(response, request)
    return response


@router.get("/session", response_model=AuthSessionResponse)
async def get_session(
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
) -> AuthSessionResponse:
    return _build_session_response(current_user)
