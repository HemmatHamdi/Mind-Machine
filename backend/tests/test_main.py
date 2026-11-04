import httpx
from fastapi.testclient import TestClient

from main import create_app


MODEL_RESPONSE = {
    "candidates": [
        {"content": {"parts": [{"text": "Hello from Gemini."}], "role": "model"}}
    ]
}


def configure(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key-not-a-real-credential")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-test-model")
    monkeypatch.setenv("GEMINI_TIMEOUT_SECONDS", "20")


def test_chat_sends_message_server_side_and_returns_model_text(monkeypatch):
    configure(monkeypatch)
    observed = {}

    def handler(request: httpx.Request) -> httpx.Response:
        observed["url"] = str(request.url)
        observed["api_key_header"] = request.headers.get("x-goog-api-key")
        observed["payload"] = request.read().decode()
        return httpx.Response(200, json=MODEL_RESPONSE)

    client = TestClient(create_app(httpx.MockTransport(handler)))
    response = client.post("/chat", json={"message": "Hello"})

    assert response.status_code == 200
    assert response.json() == {"reply": "Hello from Gemini."}
    assert observed["url"].endswith("/models/gemini-test-model:generateContent")
    assert observed["api_key_header"] == "test-key-not-a-real-credential"
    assert '"text":"Hello"' in observed["payload"]
    assert "test-key-not-a-real-credential" not in observed["url"]


def test_blank_message_is_rejected(monkeypatch):
    configure(monkeypatch)
    client = TestClient(create_app())

    response = client.post("/chat", json={"message": "   "})

    assert response.status_code == 422


def test_validation_errors_do_not_echo_user_input(monkeypatch):
    configure(monkeypatch)
    client = TestClient(create_app())
    private_message = "private-text-" * 400

    response = client.post("/chat", json={"message": private_message})

    assert response.status_code == 422
    assert "private-text-" not in response.text
    assert "input" not in response.json()["detail"][0]


def test_missing_credentials_return_configuration_error(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("GEMINI_MODEL", "gemini-test-model")
    client = TestClient(create_app())

    response = client.post("/chat", json={"message": "Hello"})

    assert response.status_code == 503
    assert "GEMINI_API_KEY" in response.json()["detail"]


def test_provider_timeout_returns_gateway_timeout(monkeypatch):
    configure(monkeypatch)

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("simulated timeout", request=request)

    client = TestClient(create_app(httpx.MockTransport(handler)))
    response = client.post("/chat", json={"message": "Hello"})

    assert response.status_code == 504
    assert "simulated timeout" not in response.text


def test_provider_error_is_sanitized(monkeypatch):
    configure(monkeypatch)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": {"message": "sensitive upstream detail"}})

    client = TestClient(create_app(httpx.MockTransport(handler)))
    response = client.post("/chat", json={"message": "Hello"})

    assert response.status_code == 502
    assert "sensitive upstream detail" not in response.text


def test_unexpected_provider_response_returns_sanitized_error(monkeypatch):
    configure(monkeypatch)
    client = TestClient(
        create_app(httpx.MockTransport(lambda request: httpx.Response(200, json={"candidates": []})))
    )

    response = client.post("/chat", json={"message": "Hello"})

    assert response.status_code == 502
    assert "Traceback" not in response.text
