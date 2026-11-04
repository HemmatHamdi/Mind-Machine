"""Explicit opt-in transport. Importing this module never connects to a Space."""

import asyncio
from collections.abc import Callable
from threading import Event

from dispatch_auth import ID_HEADER, TAG_HEADER, TIME_HEADER, Dispatch
from zerogpu import GenerationUnavailable, MAX_NEW_TOKENS

SPACE_ID = "Mohanad06/mind-machine-chat"


def _client_factory(**kwargs):
    # Import only on a separately approved request, never at startup/health check.
    from gradio_client import Client

    return Client(**kwargs)


class PrivateSpaceClient:
    """One submit, no inference retry, no fallback, no credential-as-chat input."""

    def __init__(
        self, *, token: str, execution_approved: bool = False,
        client_factory: Callable = _client_factory,
    ):
        # The shared signing key never reaches the transport or the network.
        if execution_approved is not True or not token:
            raise GenerationUnavailable()
        self._token = token
        self._factory = client_factory

    async def generate(
        self, message: str, *, max_new_tokens: int, dispatch: Dispatch
    ) -> str:
        if (
            not isinstance(message, str) or not message.strip()
            or len(message) > 4_000 or type(max_new_tokens) is not int
            or not 1 <= max_new_tokens <= MAX_NEW_TOKENS
            or not isinstance(dispatch, Dispatch)
        ):
            raise GenerationUnavailable()

        abandoned = Event()

        def submit_once():
            client = self._factory(
                src=SPACE_ID, token=self._token, verbose=False,
                max_workers=1, download_files=False, analytics_enabled=False,
                ssl_verify=True, httpx_kwargs={"timeout": 15.0},
                headers={
                    ID_HEADER: dispatch.id,
                    TIME_HEADER: str(dispatch.issued_at),
                    TAG_HEADER: dispatch.tag,
                },
            )
            # Cancellation during metadata discovery must not cause a late submit.
            if abandoned.is_set():
                raise GenerationUnavailable()
            # Metadata/heartbeat reconnection is not an inference retry.
            # Never call predict(), resubmit(), or retry this submit.
            job = client.submit(message, max_new_tokens, api_name="/generate")
            return job.result(timeout=55)

        try:
            return await asyncio.to_thread(submit_once)
        except asyncio.CancelledError:
            abandoned.set()
            # A thread/remote job may still be running. Adapter retains quarantine.
            raise
        except Exception:
            raise GenerationUnavailable() from None
