"""Offline tests. Mocked Groq responses are NOT evidence of a live model call."""
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from main import create_app
from security import hash_password


@pytest.fixture
def auth(monkeypatch):
    monkeypatch.setenv("CHAT_AUTH_USERS", json.dumps({"demo": hash_password("safe-password-123") }))
    monkeypatch.setenv("CHAT_RATE_LIMIT_REQUESTS", "10")
    monkeypatch.setenv("CHAT_RATE_LIMIT_WINDOW_SECONDS", "60")
    monkeypatch.setenv("GROQ_API_KEY", "mock-key-not-real")
    monkeypatch.setenv("GROQ_MODEL", "openai/gpt-oss-20b")
    monkeypatch.setenv("GROQ_FREE_PLAN_CONFIRMED", "true")
    return ("demo", "safe-password-123")


def test_backend_returns_mocked_model_reply(auth):
    def mock_handler(request):
        assert request.url.path == "/openai/v1/chat/completions"
        assert request.headers["Authorization"] == "Bearer mock-key-not-real"
        body = json.loads(request.content)
        assert body["messages"][-1]["content"] == "Hello Masari"
        return httpx.Response(200, json={"choices": [{"message": {"content": "Hello from mocked Groq!"}, "finish_reason": "stop"}]})
    app = create_app(transport=httpx.MockTransport(mock_handler))
    with TestClient(app) as client:
        result = client.post("/chat", json={"message": "Hello Masari"}, auth=auth)
        assert result.status_code == 200, result.text
        assert result.json() == {"reply": "Hello from mocked Groq!"}
        assert client.get("/health").json() == {"status": "ok"}
        assert "Masari Chatbot" in client.get("/").text


def test_missing_credentials_rejected(auth):
    app = create_app(transport=httpx.MockTransport(lambda r: pytest.fail("Should not call model")))
    with TestClient(app) as client:
        result = client.post("/chat", json={"message": "Hello"})
        assert result.status_code == 401


def test_free_plan_not_confirmed_blocks_call(auth, monkeypatch):
    monkeypatch.setenv("GROQ_FREE_PLAN_CONFIRMED", "false")
    app = create_app(transport=httpx.MockTransport(lambda r: pytest.fail("Should not call model")))
    with TestClient(app) as client:
        result = client.post("/chat", json={"message": "Hello"}, auth=auth)
        assert result.status_code == 503
