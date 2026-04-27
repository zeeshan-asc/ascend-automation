from __future__ import annotations

import base64
import binascii
import hashlib
import secrets


class PasswordHasher:
    _algorithm = "pbkdf2_sha256"

    def __init__(self, *, iterations: int, salt_bytes: int = 16) -> None:
        self._iterations = iterations
        self._salt_bytes = salt_bytes

    def hash_password(self, password: str) -> tuple[str, str]:
        salt = secrets.token_bytes(self._salt_bytes)
        digest = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt,
            self._iterations,
        )
        encoded_digest = base64.b64encode(digest).decode("ascii")
        encoded_salt = base64.b64encode(salt).decode("ascii")
        return f"{self._algorithm}${self._iterations}${encoded_digest}", encoded_salt

    def verify_password(
        self,
        password: str,
        *,
        password_hash: str,
        password_salt: str,
    ) -> bool:
        try:
            algorithm, iterations_raw, encoded_digest = password_hash.split("$", 2)
            if algorithm != self._algorithm:
                return False
            iterations = int(iterations_raw)
            expected_digest = base64.b64decode(encoded_digest.encode("ascii"))
            salt = base64.b64decode(password_salt.encode("ascii"))
        except (ValueError, binascii.Error):
            return False

        candidate_digest = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt,
            iterations,
        )
        return secrets.compare_digest(candidate_digest, expected_digest)
