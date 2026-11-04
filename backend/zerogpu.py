"""Offline ZeroGPU integration contract; deliberately no live network transport.

Only tests inject a Space client. There is no environment-variable activation,
token lookup, automatic quota refresh, billing operation, or model fallback.
"""

import asyncio
import math
import os
from pathlib import Path
import sqlite3
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Protocol
from uuid import uuid4


GPU_SECONDS_PER_ATTEMPT = 30
MAX_ATTEMPTS = 6
GPU_RESERVE_SECONDS = 60
RUN_RESERVE = 2
MAX_NEW_TOKENS = 128
MAX_REPLY_CHARACTERS = 8_000
WINDOW_SECONDS = 86_400


class GenerationUnavailable(Exception):
    """Content-free application error; upstream error text must never escape."""


class ChatGenerator(Protocol):
    async def generate(self, message: str) -> str: ...


class SpaceClient(Protocol):
    """Port for a future approved, authenticated private Gradio Space client.

    Its implementation must target one operator-approved Space, expose only
    /generate, submit exactly one GPU invocation, and perform no automatic retry.
    The Space itself must enforce the 30-second GPU deadline. Passing a duration
    from FastAPI would not enforce a server-side GPU limit.
    """

    async def generate(self, message: str, *, max_new_tokens: int) -> str: ...


@dataclass(frozen=True)
class ManualQuotaSnapshot:
    """Operator evidence, not an authoritative API read or a billing guarantee."""

    observed_at: float
    gpu_seconds_remaining: int
    runs_remaining: int
    overquota_used: int
    personal_free_account_confirmed: bool
    paid_usage_disabled_confirmed: bool


class QuotaBudget:
    """Persistent, atomic attempt reservations containing no user/chat data.

    No automatic replenishment. An uncertain job remains active across restarts
    and blocks re-arming even after expiry; recovery requires operator review.
    This counter cannot observe other account usage or enforce HF billing policy.
    """

    def __init__(self, path: Path, *, clock: Callable[[], float] = time.time):
        self.path = Path(path)
        self.clock = clock
        # The parent must already exist. Refuse symlinks and restrict a new file.
        flags = os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(self.path, flags, 0o600)
        os.close(descriptor)
        with self._connect() as db:
            db.execute(
                """CREATE TABLE IF NOT EXISTS budget (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    expires_at REAL NOT NULL,
                    attempts_left INTEGER NOT NULL CHECK (attempts_left >= 0),
                    gpu_seconds_left INTEGER NOT NULL CHECK (gpu_seconds_left >= 0),
                    active_job TEXT
                )"""
            )

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(self.path, timeout=5)
        try:
            with db:
                yield db
        finally:
            db.close()

    def arm(self, snapshot: ManualQuotaSnapshot) -> None:
        """Explicit offline/operator action; never called by the production app.

        Accept only a snapshot observed within the last minute. Expiry stops work
        after 24 hours; it does NOT assert that either HF counter has reset.
        A later arm still requires fresh manual evidence for both counters.
        """
        now = self.clock()
        if (
            not isinstance(snapshot, ManualQuotaSnapshot)
            or not math.isfinite(now)
            or type(snapshot.observed_at) not in (int, float)
            or not math.isfinite(snapshot.observed_at)
            or not 0 <= now - snapshot.observed_at <= 60
            or snapshot.personal_free_account_confirmed is not True
            or snapshot.paid_usage_disabled_confirmed is not True
            or type(snapshot.overquota_used) is not int
            or snapshot.overquota_used != 0
            or type(snapshot.gpu_seconds_remaining) is not int
            or type(snapshot.runs_remaining) is not int
            or not 0 <= snapshot.gpu_seconds_remaining <= 300
            or not 0 <= snapshot.runs_remaining <= 8
        ):
            raise GenerationUnavailable() from None
        attempts = min(
            MAX_ATTEMPTS,
            max(0, snapshot.runs_remaining - RUN_RESERVE),
            max(0, (snapshot.gpu_seconds_remaining - GPU_RESERVE_SECONDS)
                // GPU_SECONDS_PER_ATTEMPT),
        )
        if attempts == 0:
            raise GenerationUnavailable() from None
        try:
            with self._connect() as db:
                db.execute("BEGIN IMMEDIATE")
                previous = db.execute(
                    "SELECT expires_at, active_job FROM budget WHERE id = 1"
                ).fetchone()
                if previous and (previous[0] > now or previous[1] is not None):
                    raise GenerationUnavailable()
                db.execute(
                    """INSERT OR REPLACE INTO budget
                       VALUES (1, ?, ?, ?, NULL)""",
                    (snapshot.observed_at + WINDOW_SECONDS, attempts,
                     attempts * GPU_SECONDS_PER_ATTEMPT),
                )
        except sqlite3.Error:
            raise GenerationUnavailable() from None

    def reserve(self) -> str:
        """Charge before dispatch; errors/cancellation never refund the attempt."""
        now = self.clock()
        if not math.isfinite(now):
            raise GenerationUnavailable()
        try:
            with self._connect() as db:
                db.execute("BEGIN IMMEDIATE")
                row = db.execute(
                    """SELECT expires_at, attempts_left, gpu_seconds_left, active_job
                       FROM budget WHERE id = 1"""
                ).fetchone()
                if (
                    row is None or row[0] <= now or row[1] <= 0
                    or row[2] < GPU_SECONDS_PER_ATTEMPT or row[3] is not None
                ):
                    raise GenerationUnavailable()
                reservation = uuid4().hex
                db.execute(
                    """UPDATE budget SET attempts_left = attempts_left - 1,
                       gpu_seconds_left = gpu_seconds_left - ?, active_job = ?
                       WHERE id = 1""",
                    (GPU_SECONDS_PER_ATTEMPT, reservation),
                )
                return reservation
        except sqlite3.Error:
            raise GenerationUnavailable() from None

    def finish(self, reservation: str) -> None:
        """Release concurrency only after a valid completion, without a refund."""
        try:
            with self._connect() as db:
                result = db.execute(
                    "UPDATE budget SET active_job = NULL WHERE id = 1 AND active_job = ?",
                    (reservation,),
                )
                if result.rowcount != 1:
                    raise GenerationUnavailable()
        except sqlite3.Error:
            raise GenerationUnavailable() from None


class ZeroGPUAdapter:
    """Exercise the approved integration offline via an injected fake client.

    Production main:app never constructs this adapter or a Space client.
    A future real transport requires separate approval and access verification.
    """

    def __init__(
        self, client: SpaceClient, budget: QuotaBudget, *, wait_timeout_seconds: float = 60
    ):
        if (
            isinstance(wait_timeout_seconds, bool)
            or not isinstance(wait_timeout_seconds, (int, float))
            or not math.isfinite(wait_timeout_seconds)
            or not 0 < wait_timeout_seconds <= 120
        ):
            raise ValueError("Invalid wait timeout.")
        self.client = client
        self.budget = budget
        self.wait_timeout_seconds = wait_timeout_seconds

    async def generate(self, message: str) -> str:
        if not isinstance(message, str) or not message.strip() or len(message) > 4_000:
            raise GenerationUnavailable()
        reservation = self.budget.reserve()
        try:
            reply = await asyncio.wait_for(
                self.client.generate(message, max_new_tokens=MAX_NEW_TOKENS),
                timeout=self.wait_timeout_seconds,
            )
            if (
                not isinstance(reply, str) or not reply.strip()
                or len(reply) > MAX_REPLY_CHARACTERS
            ):
                raise GenerationUnavailable()
        except asyncio.CancelledError:
            # Do not clear active_job: remote cancellation cannot be assumed.
            raise
        except Exception:
            # No retry, raw error/logging, refund, or automatic unlock.
            raise GenerationUnavailable() from None
        self.budget.finish(reservation)
        return reply
