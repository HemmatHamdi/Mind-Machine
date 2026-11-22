"""Local HTTP Basic authentication and single-process per-user throttling."""

import hashlib
import hmac
import json
import math
import os
import re
import secrets
import threading
import time
from collections import deque
from collections.abc import Callable

from fastapi import HTTPException, Request
from fastapi.security import HTTPBasic
from starlette.concurrency import run_in_threadpool

PASSWORD_ITERATIONS = 600_000
USERNAME_PATTERN = re.compile(r"[A-Za-z0-9_.-]{1,64}")
HASH_PATTERN = re.compile(r"pbkdf2_sha256\$600000\$[0-9a-f]{32}\$[0-9a-f]{64}")


def hash_password(password: str) -> str:
    """Hash a new local password; never log the password or resulting hash."""
    if not password.isascii() or not 12 <= len(password) <= 256:
        raise ValueError("Use an ASCII password containing 12–256 characters.")
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("ascii"), salt, PASSWORD_ITERATIONS
    )
    return f"pbkdf2_sha256${PASSWORD_ITERATIONS}${salt.hex()}${digest.hex()}"


def parse_users(value: str) -> dict[str, str]:
    """Reject malformed configuration without including any supplied values."""
    try:
        users = json.loads(value)
        if not isinstance(users, dict) or not 1 <= len(users) <= 1_000:
            raise ValueError
        for name, encoded in users.items():
            if (
                not isinstance(name, str)
                or not USERNAME_PATTERN.fullmatch(name)
                or not isinstance(encoded, str)
                or not HASH_PATTERN.fullmatch(encoded)
            ):
                raise ValueError
    except (TypeError, ValueError):
        raise ValueError("Invalid chat authentication configuration.") from None
    return users


def verify_password(password: str, encoded: str) -> bool:
    # HTTP Basic's FastAPI parser accepts ASCII credentials. Reject oversized
    # inputs before hashing; never use a supplied exception string in a log.
    if not password.isascii() or len(password) > 256:
        return False
    _, iterations, salt, expected = encoded.split("$")
    actual = hashlib.pbkdf2_hmac(
        "sha256", password.encode("ascii"), bytes.fromhex(salt), int(iterations)
    )
    return hmac.compare_digest(actual, bytes.fromhex(expected))


class UserRateLimiter:
    """Atomic sliding window, scoped to this process and authenticated user."""

    def __init__(
        self, requests: int, window_seconds: int, clock: Callable[[], float]
    ) -> None:
        self.requests = requests
        self.window_seconds = window_seconds
        self.clock = clock
        self._events: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def check(self, username: str) -> None:
        with self._lock:
            now = self.clock()
            events = self._events.setdefault(username, deque())
            cutoff = now - self.window_seconds
            while events and events[0] <= cutoff:
                events.popleft()
            if len(events) >= self.requests:
                retry_after = max(1, math.ceil(events[0] + self.window_seconds - now))
                raise HTTPException(
                    status_code=429,
                    detail="Your request limit has been reached. Please try again later.",
                    headers={"Retry-After": str(retry_after), "Cache-Control": "no-store"},
                )
            events.append(now)


class ChatSecurity:
    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self.scheme = HTTPBasic(auto_error=False, realm="Masari chat")
        self.users: dict[str, str] = {}
        self.limiter: UserRateLimiter | None = None
        try:
            users = parse_users(os.getenv("CHAT_AUTH_USERS", ""))
            requests = int(os.getenv("CHAT_RATE_LIMIT_REQUESTS", "10"))
            window = int(os.getenv("CHAT_RATE_LIMIT_WINDOW_SECONDS", "60"))
            if not 1 <= requests <= 10_000 or not 1 <= window <= 86_400:
                raise ValueError
            self.users = users
            self.limiter = UserRateLimiter(requests, window, clock)
        except (TypeError, ValueError):
            # Fail closed, without printing JSON, usernames, or hash values.
            pass

    async def check_request(self, request: Request) -> None:
        if getattr(request.state, "chat_security_checked", False):
            return
        if self.limiter is None:
            raise HTTPException(
                status_code=503,
                detail="Chat security is not configured. Contact the administrator.",
            )
        credentials = await self.scheme(request)
        if credentials is None:
            self.reject_credentials()
        # Unknown usernames still perform a real hash comparison. The result is
        # never accepted unless the username is a configured account.
        encoded = self.users.get(credentials.username, next(iter(self.users.values())))
        valid = await run_in_threadpool(verify_password, credentials.password, encoded)
        if not valid or credentials.username not in self.users:
            self.reject_credentials()
        self.limiter.check(credentials.username)
        request.state.chat_security_checked = True

    @staticmethod
    def reject_credentials() -> None:
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing credentials.",
            headers={"WWW-Authenticate": 'Basic realm="Masari chat"'},
        )
