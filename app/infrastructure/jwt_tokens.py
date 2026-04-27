from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
from time import time
from typing import Any

from pydantic import ValidationError

from app.domain.errors import AuthenticationError
from app.domain.models import TokenClaims, User


def _encode_segment(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _decode_segment(value: str) -> dict[str, Any]:
    padding = "=" * (-len(value) % 4)
    decoded = base64.urlsafe_b64decode(f"{value}{padding}".encode("ascii"))
    payload = json.loads(decoded.decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("JWT segment must decode to an object.")
    return payload


class JWTTokenManager:
    def __init__(self, *, secret_key: str) -> None:
        self._secret_key = secret_key.encode("utf-8")

    def issue_token(self, user: User) -> str:
        header = {"alg": "HS256", "typ": "JWT"}
        payload = {
            "sub": user.user_id,
            "email": user.email,
            "name": user.name,
            "ver": user.token_version,
            "iat": int(time()),
        }
        encoded_header = _encode_segment(header)
        encoded_payload = _encode_segment(payload)
        signing_input = f"{encoded_header}.{encoded_payload}".encode("ascii")
        signature = hmac.new(self._secret_key, signing_input, hashlib.sha256).digest()
        encoded_signature = base64.urlsafe_b64encode(signature).decode("ascii").rstrip("=")
        return f"{encoded_header}.{encoded_payload}.{encoded_signature}"

    def decode_token(self, token: str) -> TokenClaims:
        parts = token.split(".")
        if len(parts) != 3:
            raise AuthenticationError("Authentication failed.")

        encoded_header, encoded_payload, encoded_signature = parts
        try:
            header = _decode_segment(encoded_header)
            payload = _decode_segment(encoded_payload)
        except (ValueError, TypeError, binascii.Error, json.JSONDecodeError):
            raise AuthenticationError("Authentication failed.") from None

        if header.get("alg") != "HS256" or header.get("typ") != "JWT":
            raise AuthenticationError("Authentication failed.")

        signing_input = f"{encoded_header}.{encoded_payload}".encode("ascii")
        expected_signature = hmac.new(self._secret_key, signing_input, hashlib.sha256).digest()
        expected_signature_encoded = (
            base64.urlsafe_b64encode(expected_signature).decode("ascii").rstrip("=")
        )
        if not hmac.compare_digest(expected_signature_encoded, encoded_signature):
            raise AuthenticationError("Authentication failed.")

        try:
            return TokenClaims.model_validate(payload)
        except ValidationError as exc:
            raise AuthenticationError("Authentication failed.") from exc
