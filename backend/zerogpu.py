"""Network-free ZeroGPU contracts, dispatch flow and response guard.

Durable reservations/admissions live in ledger_store.CentralLedger (one database).

Default main:app is disabled. The separate operator-selected entrypoint may
inject the approved private transport only after future execution authorization.
This module has no token lookup, quota refresh, billing operation or fallback.
"""

import asyncio
import math
from dataclasses import dataclass
from typing import Protocol
from uuid import uuid4

from dispatch_auth import Dispatch, sign_dispatch


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

    async def generate(
        self, message: str, *, max_new_tokens: int, dispatch: Dispatch
    ) -> str: ...


@dataclass(frozen=True)
class ManualQuotaSnapshot:
    """Operator evidence, not an authoritative API read or a billing guarantee."""

    observed_at: float
    gpu_seconds_remaining: int
    runs_remaining: int
    overquota_used: int
    personal_free_account_confirmed: bool
    paid_usage_disabled_confirmed: bool


class ZeroGPUAdapter:
    """Guard the injected Space client; offline tests use fakes exclusively.

    Production main:app never constructs this adapter or a Space client.
    Running the prepared real transport requires separate execution approval.
    """

    def __init__(
        self, client: SpaceClient, ledger, *, dispatch_key,
        wait_timeout_seconds: float = 60,
    ):
        if (
            isinstance(wait_timeout_seconds, bool)
            or not isinstance(wait_timeout_seconds, (int, float))
            or not math.isfinite(wait_timeout_seconds)
            or not 0 < wait_timeout_seconds <= 120
        ):
            raise ValueError("Invalid wait timeout.")
        self.client = client
        self.ledger = ledger
        self.dispatch_key = dispatch_key
        self.wait_timeout_seconds = wait_timeout_seconds

    async def generate(self, message: str) -> str:
        if not isinstance(message, str) or not message.strip() or len(message) > 4_000:
            raise GenerationUnavailable()
        message = message.strip()
        issued_at = int(self.ledger.clock())
        dispatch_id = uuid4().hex
        try:
            tag = sign_dispatch(
                self.dispatch_key, dispatch_id, issued_at, MAX_NEW_TOKENS, message
            )
        except Exception:
            raise GenerationUnavailable() from None
        dispatch = Dispatch(dispatch_id, issued_at, tag)
        # Reserve (charge + single-job lock) BEFORE anything leaves the backend.
        self.ledger.reserve(dispatch.id, dispatch.tag)
        try:
            reply = await asyncio.wait_for(
                self.client.generate(
                    message, max_new_tokens=MAX_NEW_TOKENS, dispatch=dispatch
                ),
                timeout=self.wait_timeout_seconds,
            )
            if (
                not isinstance(reply, str) or not reply.strip()
                or len(reply) > MAX_REPLY_CHARACTERS
            ):
                raise GenerationUnavailable()
        except asyncio.CancelledError:
            # Keep the reservation active: remote cancellation cannot be assumed.
            raise
        except Exception:
            # No retry, raw error/logging, refund, or automatic unlock.
            raise GenerationUnavailable() from None
        self.ledger.finish(dispatch.id)
        return reply
