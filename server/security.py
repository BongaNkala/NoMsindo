from __future__ import annotations

import secrets
import time
from collections import defaultdict

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from fastapi import HTTPException, Request

_ph = PasswordHasher()
MIN_PASSWORD = 10


def hash_password(pw: str) -> str:
    return _ph.hash(pw)


def verify_password(pw: str, hashed: str) -> bool:
    try:
        return _ph.verify(hashed, pw)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def password_problem(pw: str) -> str | None:
    if len(pw) < MIN_PASSWORD:
        return f"Password must be at least {MIN_PASSWORD} characters."
    return None


def csrf_token(request: Request) -> str:
    tok = request.session.get("csrf")
    if not tok:
        tok = secrets.token_urlsafe(24)
        request.session["csrf"] = tok
    return tok


def check_csrf(request: Request, submitted: str) -> None:
    good = request.session.get("csrf")
    if not good or not submitted or not secrets.compare_digest(good, submitted):
        raise HTTPException(403, "Invalid or missing form token. Reload the page and try again.")


class RateLimiter:
    """Simple in-memory limiter: max `limit` failures per `window` seconds per key."""

    def __init__(self, limit: int = 8, window: int = 900):
        self.limit, self.window = limit, window
        self.hits: dict[str, list[float]] = defaultdict(list)

    def _prune(self, key: str) -> list[float]:
        now = time.time()
        self.hits[key] = [t for t in self.hits[key] if now - t < self.window]
        return self.hits[key]

    def blocked(self, key: str) -> bool:
        return len(self._prune(key)) >= self.limit

    def fail(self, key: str) -> None:
        self._prune(key).append(time.time())

    def reset(self, key: str) -> None:
        self.hits.pop(key, None)
