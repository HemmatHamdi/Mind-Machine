import ast
import json
import logging
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from main import AI_UNAVAILABLE_MESSAGE, create_app
from security import hash_password


TEST_USER = "test-user"
TEST_PASSWORD = "fake-test-password-only"
TEST_PASSWORD_HASH = hash_password(TEST_PASSWORD)
PRIVATE_MESSAGE = "private test input"
# Negative regression fixtures only: none of these settings is read at runtime.
RETIRED_SETTINGS = (
    "GROQ_API_KEY", "GROQ_MODEL", "GROQ_FREE_PLAN_CONFIRMED",
    "GROQ_TIMEOUT_SECONDS", "GROQ_MAX_COMPLETION_TOKENS",
    "GEMINI_API_KEY", "GEMINI_MODEL", "GEMINI_TIMEOUT_SECONDS",
)


@pytest.fixture(autouse=True)
def configure(monkeypatch):
    for name in RETIRED_SETTINGS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("CHAT_AUTH_USERS", json.dumps({TEST_USER: TEST_PASSWORD_HASH}))
    monkeypatch.setenv("CHAT_RATE_LIMIT_REQUESTS", "1000")
    monkeypatch.setenv("CHAT_RATE_LIMIT_WINDOW_SECONDS", "60")


def authenticated_client():
    client = TestClient(create_app())
    client.auth = (TEST_USER, TEST_PASSWORD)
    return client


@pytest.mark.parametrize("message", ["Hello", "  Hello  ", "اشرح معنى API", "x" * 4000])
def test_valid_chat_is_explicitly_unavailable_without_any_provider_key(message, caplog):
    with caplog.at_level(logging.INFO):
        response = authenticated_client().post("/chat", json={"message": message})
    assert response.status_code == 503
    assert response.json() == {"detail": AI_UNAVAILABLE_MESSAGE}
    assert "currently unavailable" in response.json()["detail"]
    assert "no AI service is configured" in response.json()["detail"]
    assert "reply" not in response.json()
    assert response.headers["cache-control"] == "no-store"
    assert "retry-after" not in response.headers
    assert TEST_PASSWORD not in response.text + caplog.text
    assert message not in response.text + caplog.text


@pytest.mark.parametrize("legacy_present", [False, True])
def test_no_external_provider_is_contacted_even_with_leftover_settings(
    monkeypatch, no_outbound_network, legacy_present
):
    if legacy_present:
        for name in RETIRED_SETTINGS:
            monkeypatch.setenv(name, "synthetic-retired-setting-not-a-secret")
    client = authenticated_client()
    for _ in range(3):
        response = client.post("/chat", json={"message": PRIVATE_MESSAGE})
        assert response.status_code == 503
        assert response.json() == {"detail": AI_UNAVAILABLE_MESSAGE}
    assert no_outbound_network == []
    assert "synthetic-retired-setting" not in response.text


@pytest.mark.parametrize(
    "payload",
    [{}, {"message": ""}, {"message": "   "}, {"message": None},
     {"message": 123}, {"message": ["private"]}, {"message": "private-text-" * 400}],
)
def test_invalid_messages_are_rejected_without_echoing_input(payload):
    response = authenticated_client().post("/chat", json=payload)
    assert response.status_code == 422
    assert response.headers["cache-control"] == "no-store"
    assert "private" not in response.text
    for error in response.json()["detail"]:
        assert "input" not in error
        assert "ctx" not in error


def test_malformed_json_does_not_echo_input():
    response = authenticated_client().post(
        "/chat", content='{"message":"private', headers={"Content-Type": "application/json"}
    )
    assert response.status_code == 422
    assert "private" not in response.text
    assert response.headers["cache-control"] == "no-store"


def test_openapi_preserves_request_contract_and_documents_unavailability():
    schema = TestClient(create_app()).get("/openapi.json").json()
    route = schema["paths"]["/chat"]["post"]
    request = schema["components"]["schemas"]["ChatRequest"]
    assert request["required"] == ["message"]
    assert request["properties"]["message"]["type"] == "string"
    assert request["properties"]["message"]["maxLength"] == 4000
    assert route["security"] == [{"HTTPBasic": []}]
    assert route["responses"]["503"]["description"] == AI_UNAVAILABLE_MESSAGE


def test_runtime_and_template_have_no_provider_configuration_or_client():
    backend = Path(__file__).resolve().parents[1]
    # Modules that legitimately own an HTTPS call path to the storage/control
    # plane (lazy, injectable, never run at import). Provider names stay banned.
    https_allowed = {"ledger_store.py", "dispatch_auth.py"}
    for path in backend.glob("*.py"):
        allowed = path.name in https_allowed
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules = [alias.name.split(".")[0] for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                modules = [(node.module or "").split(".")[0]]
            else:
                continue
            banned = {"httpx", "requests", "urllib", "aiohttp", "groq", "google", "openai"}
            if allowed:
                banned -= {"urllib"}
            assert not set(modules) & banned
        text = path.read_text().lower()
        assert allowed or "https://" not in text
        assert "groq" not in text
        assert "gemini" not in text
    template = (backend / ".env.example").read_text()
    requirements = (backend / "requirements.txt").read_text().lower()
    for name in RETIRED_SETTINGS:
        assert name not in template
    assert "httpx" not in requirements
    assert "groq" not in requirements
    assert "gemini" not in requirements
