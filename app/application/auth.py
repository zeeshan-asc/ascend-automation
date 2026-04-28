from __future__ import annotations

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.domain.errors import (
    AuthenticationError,
    AuthorizationError,
    DuplicateResourceError,
)
from app.domain.interfaces import (
    PasswordHasherProtocol,
    TokenManagerProtocol,
    UserRepositoryProtocol,
)
from app.domain.models import AuthenticatedUser, User, utcnow


def _normalize_email(value: str) -> str:
    return value.strip().lower()


class CredentialsPayload(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: EmailStr) -> str:
        return _normalize_email(str(value))

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Password cannot be blank.")
        return value


class SignUpRequest(CredentialsPayload):
    name: str = Field(min_length=1, max_length=200)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Name cannot be blank.")
        return stripped


class SignInRequest(CredentialsPayload):
    pass


class AuthUserResponse(BaseModel):
    user_id: str
    name: str
    email: EmailStr


class AuthSuccessResponse(BaseModel):
    token: str
    token_type: str = "bearer"
    user: AuthUserResponse


class AuthSessionResponse(BaseModel):
    user: AuthUserResponse


class AuthService:
    def __init__(
        self,
        *,
        user_repository: UserRepositoryProtocol,
        password_hasher: PasswordHasherProtocol,
        token_manager: TokenManagerProtocol,
        allowed_email_domain: str,
    ) -> None:
        self._user_repository = user_repository
        self._password_hasher = password_hasher
        self._token_manager = token_manager
        self._allowed_email_domain = allowed_email_domain.strip().lower()

    async def sign_up(self, payload: SignUpRequest) -> AuthSuccessResponse:
        self._ensure_allowed_email_domain(payload.email)
        existing_user = await self._user_repository.get_by_email(payload.email)
        if existing_user is not None:
            raise DuplicateResourceError("An account with that email already exists.")

        password_hash, password_salt = self._password_hasher.hash_password(payload.password)
        user = User(
            name=payload.name,
            email=payload.email,
            password_hash=password_hash,
            password_salt=password_salt,
            created_at=utcnow(),
            updated_at=utcnow(),
        )
        created_user = await self._user_repository.create(user)
        return self._build_auth_success(created_user)

    async def sign_in(self, payload: SignInRequest) -> AuthSuccessResponse:
        self._ensure_allowed_email_domain(payload.email)
        user = await self._user_repository.get_by_email(payload.email)
        if user is None:
            raise AuthenticationError("Invalid email or password.")

        password_ok = self._password_hasher.verify_password(
            payload.password,
            password_hash=user.password_hash,
            password_salt=user.password_salt,
        )
        if not password_ok:
            raise AuthenticationError("Invalid email or password.")
        return self._build_auth_success(user)

    async def authenticate_token(self, token: str) -> AuthenticatedUser:
        claims = self._token_manager.decode_token(token)
        user = await self._user_repository.get_by_user_id(claims.sub)
        if user is None:
            raise AuthenticationError("Authentication failed.")
        if user.token_version != claims.ver:
            raise AuthenticationError("Session is no longer valid. Sign in again.")
        return user.to_authenticated_user()

    async def sign_out(self, *, user_id: str) -> None:
        await self._user_repository.bump_token_version(user_id=user_id, now=utcnow())

    def _ensure_allowed_email_domain(self, email: str) -> None:
        _, _, domain = email.rpartition("@")
        if domain.lower() != self._allowed_email_domain:
            raise AuthorizationError(
                "This email address is not allowed.",
            )

    def _build_auth_success(self, user: User) -> AuthSuccessResponse:
        return AuthSuccessResponse(
            token=self._token_manager.issue_token(user),
            user=AuthUserResponse(
                user_id=user.user_id,
                name=user.name,
                email=user.email,
            ),
        )
