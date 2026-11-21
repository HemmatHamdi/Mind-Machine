"""Minimal, one-request Gemini adapter. No retries, storage, or fallback."""

import asyncio
import threading
from collections.abc import Callable

MODEL_ID = "gemini-3.5-flash-lite"
MAX_OUTPUT_TOKENS = 512
MAX_REPLY_CHARACTERS = 8_000

SYSTEM_INSTRUCTION = """\
You are Masari, a concise and supportive educational guide for Egyptian students.
Answer in Arabic unless the user writes in another language. This integration does
not yet provide verified Baccalaureate source material. Do not state current
pathways, regulations, exam rules, or admissions details as verified facts. If
asked about them, say that source-backed information is not connected yet and
recommend checking an official Ministry source or school counselor. Do not choose
a pathway for the student, predict ability or success, or request personal data.
"""


class GeminiUnavailable(Exception):
    """Content-free provider error; never expose provider responses or credentials."""


def _client_factory(api_key: str):
    from google import genai, types

    return genai.Client(
        api_key=api_key,
        http_options=types.HttpOptions(
            retry_options=types.HttpRetryOptions(attempts=1),
        ),
    )


class GeminiAdapter:
    def __init__(
        self, *, api_key: str, client_factory: Callable = _client_factory,
    ):
        if not isinstance(api_key, str) or not api_key.strip():
            raise GeminiUnavailable()
        self._api_key = api_key
        self._client_factory = client_factory
        self._client = None
        self._client_lock = threading.Lock()

    def _get_client(self):
        if self._client is None:
            with self._client_lock:
                if self._client is None:
                    self._client = self._client_factory(self._api_key)
        return self._client

    def _generate_sync(self, message: str) -> str:
        response = self._get_client().interactions.create(
            model=MODEL_ID,
            input=message,
            system_instruction=SYSTEM_INSTRUCTION,
            generation_config={"max_output_tokens": MAX_OUTPUT_TOKENS},
            store=False,
        )
        reply = getattr(response, "output_text", None)
        if (
            not isinstance(reply, str) or not reply.strip()
            or len(reply) > MAX_REPLY_CHARACTERS
        ):
            raise GeminiUnavailable()
        return reply.strip()

    async def generate(self, message: str) -> str:
        if not isinstance(message, str) or not message.strip() or len(message) > 4_000:
            raise GeminiUnavailable()
        try:
            return await asyncio.to_thread(self._generate_sync, message.strip())
        except Exception:
            raise GeminiUnavailable() from None
