import json
import logging

import httpx
import pytest
from fastapi.testclient import TestClient

from main import GROQ_CHAT_URL, create_app


TEST_KEY = "test-key-not-a-real-credential"
PRIVATE_MESSAGE = "private test input"
MODEL_RESPONSE = {
    "choices": [
        {
            "message": {"content": "Hello from Groq.", "role": "assistant"},
            "finish_reason": "stop",
        }
    ]
}


@pytest.fixture(autouse=True)
def configure(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", TEST_KEY)
    monkeypatch.setenv("GROQ_MODEL", "openai/test-model")
    monkeypatch.setenv("GROQ_FREE_PLAN_CONFIRMED", "true")
    monkeypatch.setenv("GROQ_TIMEOUT_SECONDS", "30")
    monkeypatch.setenv("GROQ_MAX_COMPLETION_TOKENS", "512")


def test_chat_sends_message_server_side_and_returns_model_text():
    observed = []

    def handler(request: httpx.Request) -> httpx.Response:
        observed.append(request)
        return httpx.Response(200, json=MODEL_RESPONSE)

    client = TestClient(create_app(httpx.MockTransport(handler)))
    response = client.post("/chat", json={"message": "  Hello  "})

    assert response.status_code == 200
    assert response.json() == {"reply": "Hello from Groq."}
    assert len(observed) == 1
    request = observed[0]
    assert str(request.url) == GROQ_CHAT_URL
    assert request.headers["authorization"] == f"Bearer {TEST_KEY}"
    assert json.loads(request.content) == {
        "model": "openai/test-model",
        "messages": [{"role": "user", "content": "Hello"}],
        "max_completion_tokens": 512,
        "stream": False,
    }
    assert TEST_KEY not in str(request.url)


@pytest.mark.parametrize(
    "payload",
    [{}, {"message": ""}, {"message": "   "}, {"message": None},
     {"message": 123}, {"message": ["private"]}, {"message": "private-text-" * 400}],
)
def test_invalid_messages_are_rejected_without_echoing_input(payload):
    calls = []
    client = TestClient(create_app(httpx.MockTransport(lambda r: calls.append(r))))

    response = client.post("/chat", json=payload)

    assert response.status_code == 422
    assert calls == []
    assert "private" not in response.text
    for error in response.json()["detail"]:
        assert "input" not in error
        assert "ctx" not in error


def test_malformed_json_does_not_echo_input():
    response = TestClient(create_app()).post(
        "/chat", content='{"message":"private', headers={"Content-Type": "application/json"}
    )
    assert response.status_code == 422
    assert "private" not in response.text


@pytest.mark.parametrize("name", ["GROQ_API_KEY", "GROQ_MODEL"])
def test_missing_configuration_never_calls_provider(monkeypatch, name):
    monkeypatch.delenv(name)
    calls = []
    client = TestClient(create_app(httpx.MockTransport(lambda r: calls.append(r))))
    response = client.post("/chat", json={"message": PRIVATE_MESSAGE})
    assert response.status_code == 503
    assert calls == []


@pytest.mark.parametrize("confirmed", ["", "false", "yes", "1"])
def test_free_plan_guard_fails_closed(monkeypatch, confirmed):
    monkeypatch.setenv("GROQ_FREE_PLAN_CONFIRMED", confirmed)
    calls = []
    client = TestClient(create_app(httpx.MockTransport(lambda r: calls.append(r))))
    response = client.post("/chat", json={"message": PRIVATE_MESSAGE})
    assert response.status_code == 503
    assert calls == []


@pytest.mark.parametrize(
    "name,value",
    [
        ("GROQ_MODEL", "https://other.example/model"),
        ("GROQ_MODEL", "model:fastest"),
        ("GROQ_MODEL", "../model"),
        ("GROQ_TIMEOUT_SECONDS", "nan"),
        ("GROQ_TIMEOUT_SECONDS", "inf"),
        ("GROQ_TIMEOUT_SECONDS", "0"),
        ("GROQ_TIMEOUT_SECONDS", "121"),
        ("GROQ_TIMEOUT_SECONDS", "invalid"),
        ("GROQ_MAX_COMPLETION_TOKENS", "0"),
        ("GROQ_MAX_COMPLETION_TOKENS", "1025"),
        ("GROQ_MAX_COMPLETION_TOKENS", "1.5"),
    ],
)
def test_invalid_configuration_never_calls_provider(monkeypatch, name, value):
    monkeypatch.setenv(name, value)
    calls = []
    client = TestClient(create_app(httpx.MockTransport(lambda r: calls.append(r))))
    response = client.post("/chat", json={"message": PRIVATE_MESSAGE})
    assert response.status_code == 503
    assert calls == []


@pytest.mark.parametrize(
    "status,expected",
    [(400, 502), (401, 503), (402, 503), (403, 503), (404, 503),
     (413, 502), (422, 502), (429, 429), (500, 502), (502, 502), (503, 503)],
)
def test_provider_failures_are_sanitized_without_retry(status, expected, caplog):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(
            status,
            json={"error": {"message": f"{TEST_KEY} {PRIVATE_MESSAGE} sensitive upstream"}},
        )

    with caplog.at_level(logging.INFO):
        response = TestClient(create_app(httpx.MockTransport(handler))).post(
            "/chat", json={"message": PRIVATE_MESSAGE}
        )

    assert response.status_code == expected
    assert len(calls) == 1
    assert f"status={status}" in caplog.text
    for secret in (TEST_KEY, PRIVATE_MESSAGE, "sensitive upstream"):
        assert secret not in response.text
        assert secret not in caplog.text


@pytest.mark.parametrize(
    "exception,expected", [(httpx.ReadTimeout, 504), (httpx.ConnectError, 502)]
)
def test_transport_failures_are_sanitized_without_retry(exception, expected, caplog):
    calls = []

    def handler(request):
        calls.append(request)
        raise exception(f"{TEST_KEY} {PRIVATE_MESSAGE}", request=request)

    with caplog.at_level(logging.INFO):
        response = TestClient(create_app(httpx.MockTransport(handler))).post(
            "/chat", json={"message": PRIVATE_MESSAGE}
        )

    assert response.status_code == expected
    assert len(calls) == 1
    for secret in (TEST_KEY, PRIVATE_MESSAGE):
        assert secret not in response.text
        assert secret not in caplog.text


@pytest.mark.parametrize(
    "body",
    [
        {}, None, [], {"choices": []}, {"choices": [None]},
        {"choices": [{"message": {"content": None}, "finish_reason": "stop"}]},
        {"choices": [{"message": {"content": 12}, "finish_reason": "stop"}]},
        {"choices": [{"message": {"content": " "}, "finish_reason": "stop"}]},
        {"choices": [{"message": {"content": "partial"}, "finish_reason": "length"}]},
        {"choices": [{"message": {"content": "unsafe"}, "finish_reason": "content_filter"}]},
        {"choices": [{"message": {"reasoning": PRIVATE_MESSAGE}, "finish_reason": "stop"}]},
    ],
)
def test_invalid_or_incomplete_provider_response_is_sanitized(body):
    transport = httpx.MockTransport(lambda r: httpx.Response(200, content=json.dumps(body)))
    response = TestClient(create_app(transport)).post("/chat", json={"message": PRIVATE_MESSAGE})
    assert response.status_code == 502
    assert PRIVATE_MESSAGE not in response.text
    assert "Traceback" not in response.text


def test_non_json_response_is_sanitized():
    transport = httpx.MockTransport(lambda r: httpx.Response(200, text=PRIVATE_MESSAGE))
    response = TestClient(create_app(transport)).post("/chat", json={"message": PRIVATE_MESSAGE})
    assert response.status_code == 502
    assert PRIVATE_MESSAGE not in response.text


def test_redirect_is_not_followed():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(307, headers={"location": "https://other.example/"})

    response = TestClient(create_app(httpx.MockTransport(handler))).post(
        "/chat", json={"message": PRIVATE_MESSAGE}
    )
    assert response.status_code == 502
    assert len(calls) == 1
