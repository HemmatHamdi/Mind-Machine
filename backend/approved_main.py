"""Opt-in Gemini entrypoint; the default main:app remains disabled."""

import os

from gemini_adapter import GeminiAdapter
from main import create_app


def build_app(*, client_factory=None):
    if os.getenv("GEMINI_EXECUTION_APPROVED") != "true":
        return create_app()
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return create_app()
    factory = client_factory
    if factory is None:
        return create_app(generator=GeminiAdapter(api_key=api_key))
    return create_app(generator=GeminiAdapter(api_key=api_key, client_factory=factory))


app = build_app()
