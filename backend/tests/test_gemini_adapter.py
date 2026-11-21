"""Gemini adapter and opt-in wiring tests. All provider calls are faked."""

import asyncio
import sys
from types import ModuleType
from types import SimpleNamespace

from fastapi.testclient import TestClient
import pytest

from gemini_adapter import (
    GeminiAdapter, GeminiUnavailable, MAX_OUTPUT_TOKENS, MODEL_ID,
    SYSTEM_INSTRUCTION,
)
from security import hash_password


class FakeInteractions:
    def __init__(self, output="إجابة تجريبية"):
        self.output = output
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if isinstance(self.output, Exception):
            raise self.output
        return SimpleNamespace(output_text=self.output)


def test_adapter_calls_selected_model_once_without_storing_history():
    interactions = FakeInteractions("  رد تجريبي  ")
    factories = []

    def factory(api_key):
        factories.append(api_key)
        return SimpleNamespace(interactions=interactions)

    adapter = GeminiAdapter(api_key="synthetic-gemini-key", client_factory=factory)
    assert asyncio.run(adapter.generate("مرحبا")) == "رد تجريبي"
    assert factories == ["synthetic-gemini-key"]
    assert interactions.calls == [{
        "model": "gemini-3.5-flash-lite",
        "input": "مرحبا",
        "system_instruction": SYSTEM_INSTRUCTION,
        "generation_config": {"max_output_tokens": MAX_OUTPUT_TOKENS},
        "store": False,
    }]
    assert MODEL_ID == "gemini-3.5-flash-lite"
    assert "synthetic-gemini-key" not in repr(interactions.calls)


def test_provider_error_is_generic_and_not_retried():
    interactions = FakeInteractions(RuntimeError("synthetic key and user prompt"))
    adapter = GeminiAdapter(
        api_key="synthetic-key",
        client_factory=lambda api_key: SimpleNamespace(interactions=interactions),
    )
    with pytest.raises(GeminiUnavailable) as caught:
        asyncio.run(adapter.generate("synthetic question"))
    assert len(interactions.calls) == 1
    assert "synthetic key" not in str(caught.value)
    assert "synthetic question" not in str(caught.value)


def test_default_google_client_disables_sdk_retries(monkeypatch):
    from gemini_adapter import _client_factory

    calls = []

    class HttpRetryOptions:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    class HttpOptions:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    fake_google = ModuleType("google")
    fake_google.genai = SimpleNamespace(
        Client=lambda **kwargs: calls.append(kwargs) or kwargs
    )
    fake_google.types = SimpleNamespace(
        HttpOptions=HttpOptions, HttpRetryOptions=HttpRetryOptions,
    )
    monkeypatch.setitem(sys.modules, "google", fake_google)

    client = _client_factory("synthetic-key")
    assert client["api_key"] == "synthetic-key"
    assert calls[0]["http_options"].kwargs["retry_options"].kwargs == {"attempts": 1}


@pytest.mark.parametrize("message", ["", "  ", "x" * 4_001])
def test_invalid_input_never_constructs_client(message):
    def forbidden(api_key):
        pytest.fail("Invalid input must not construct a provider client.")

    adapter = GeminiAdapter(api_key="synthetic-key", client_factory=forbidden)
    with pytest.raises(GeminiUnavailable):
        asyncio.run(adapter.generate(message))


def test_opt_in_entrypoint_calls_fake_model_only_after_chat_request(monkeypatch):
    import approved_main

    interactions = FakeInteractions("رد من Gemini الوهمي")
    factories = []

    def factory(api_key):
        factories.append(api_key)
        return SimpleNamespace(interactions=interactions)

    monkeypatch.setenv("GEMINI_EXECUTION_APPROVED", "true")
    monkeypatch.setenv("GEMINI_API_KEY", "synthetic-key")
    monkeypatch.setenv("CHAT_AUTH_USERS", __import__("json").dumps({
        "demo": hash_password("synthetic-password-123"),
    }))
    monkeypatch.setenv("CHAT_RATE_LIMIT_REQUESTS", "10")
    monkeypatch.setenv("CHAT_RATE_LIMIT_WINDOW_SECONDS", "60")

    app = approved_main.build_app(client_factory=factory)
    assert factories == [] and interactions.calls == []
    with TestClient(app) as client:
        response = client.post(
            "/chat", json={"message": "سؤال تجريبي"},
            auth=("demo", "synthetic-password-123"),
        )
    assert response.status_code == 200
    assert response.json() == {"reply": "رد من Gemini الوهمي"}
    assert factories == ["synthetic-key"]
    assert len(interactions.calls) == 1
