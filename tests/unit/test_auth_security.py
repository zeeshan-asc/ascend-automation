import pytest

from app.domain.errors import AuthenticationError
from app.domain.models import User
from app.infrastructure.jwt_tokens import JWTTokenManager
from app.infrastructure.passwords import PasswordHasher


def test_password_hasher_round_trips_password() -> None:
    hasher = PasswordHasher(iterations=1000)

    password_hash, password_salt = hasher.hash_password("Password123!")

    assert hasher.verify_password(
        "Password123!",
        password_hash=password_hash,
        password_salt=password_salt,
    ) is True
    assert hasher.verify_password(
        "wrong-password",
        password_hash=password_hash,
        password_salt=password_salt,
    ) is False


def test_jwt_token_manager_round_trips_claims() -> None:
    manager = JWTTokenManager(secret_key="auth-test-secret")
    user = User(
        name="Test User",
        email="tester@ascendanalytics.co",
        password_hash="hash",
        password_salt="salt",
        token_version=3,
    )

    token = manager.issue_token(user)
    claims = manager.decode_token(token)

    assert claims.sub == user.user_id
    assert claims.email == user.email
    assert claims.ver == 3


def test_jwt_token_manager_rejects_tampered_token() -> None:
    manager = JWTTokenManager(secret_key="auth-test-secret")
    user = User(
        name="Test User",
        email="tester@ascendanalytics.co",
        password_hash="hash",
        password_salt="salt",
    )

    token = manager.issue_token(user)
    tampered = f"{token[:-1]}x"

    with pytest.raises(AuthenticationError):
        manager.decode_token(tampered)
