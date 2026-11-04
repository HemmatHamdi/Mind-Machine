import base64
import json
import logging
import math
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest
from dotenv import dotenv_values
from fastapi import HTTPException
from fastapi.testclient import TestClient

from create_chat_user import add_user
from main import create_app
from security import UserRateLimiter, hash_password, parse_users, verify_password


# Synthetic test accounts only; never provisioned in a real environment.
ALICE = ("alice", "fake-alice-password-123")
BOB = ("bob", "fake-bob-password-456")
PROVIDER_KEY = "fake-provider-key-for-tests"
PRIVATE_PROMPT = "private chat input for tests"
MODEL_RESPONSE = {
    "choices": [
        {"message": {"content": "A mocked reply."}, "finish_reason": "stop"}
    ]
}


@pytest.fixture(scope="module")
def user_hashes():
    return {ALICE[0]: hash_password(ALICE[1]), BOB[0]: hash_password(BOB[1])}


@pytest.fixture(autouse=True)
def configure(monkeypatch, user_hashes):
    monkeypatch.setenv("CHAT_AUTH_USERS", json.dumps(user_hashes))
    monkeypatch.setenv("CHAT_RATE_LIMIT_REQUESTS", "2")
    monkeypatch.setenv("CHAT_RATE_LIMIT_WINDOW_SECONDS", "60")
    monkeypatch.setenv("GROQ_API_KEY", PROVIDER_KEY)
    monkeypatch.setenv("GROQ_MODEL", "openai/gpt-oss-20b")
    monkeypatch.setenv("GROQ_FREE_PLAN_CONFIRMED", "true")
    monkeypatch.setenv("GROQ_TIMEOUT_SECONDS", "30")
    monkeypatch.setenv("GROQ_MAX_COMPLETION_TOKENS", "512")


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def make_client(clock=None, provider_status=200):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(provider_status, json=MODEL_RESPONSE)

    app = create_app(httpx.MockTransport(handler), **({"clock": clock} if clock else {}))
    return TestClient(app), calls


def send(client, auth=ALICE, **kwargs):
    return client.post("/chat", auth=auth, json={"message": PRIVATE_PROMPT}, **kwargs)


def test_authenticated_success_preserves_groq_contract_and_model():
    client, calls = make_client()
    response = send(client)
    assert response.status_code == 200
    assert response.json() == {"reply": "A mocked reply."}
    assert response.headers["cache-control"] == "no-store"
    assert len(calls) == 1
    assert str(calls[0].url) == "https://api.groq.com/openai/v1/chat/completions"
    assert calls[0].headers["authorization"] == f"Bearer {PROVIDER_KEY}"
    assert ALICE[1] not in str(calls[0].headers)
    assert json.loads(calls[0].content)["model"] == "openai/gpt-oss-20b"


@pytest.mark.parametrize("auth", [None, ("alice", "wrong"), ("unknown", ALICE[1])])
def test_unauthorized_requests_are_generic_and_never_call_provider(auth, caplog):
    client, calls = make_client()
    with caplog.at_level(logging.INFO):
        response = send(client, auth=auth)
    assert response.status_code == 401
    assert response.headers["www-authenticate"].startswith("Basic")
    assert response.headers["cache-control"] == "no-store"
    assert calls == []
    for private in (ALICE[1], PROVIDER_KEY, PRIVATE_PROMPT):
        assert private not in response.text
        assert private not in caplog.text


@pytest.mark.parametrize(
    "header",
    [
        "Bearer not-a-valid-chat-token",
        "Basic %%%",
        "Basic " + base64.b64encode(b"no-separator").decode(),
        "Basic " + base64.b64encode(b"\xff:\xff").decode(),
    ],
)
def test_malformed_authentication_is_401_and_sanitized(header):
    client, calls = make_client()
    response = client.post("/chat", headers={"Authorization": header}, json={"message": "hi"})
    assert response.status_code == 401
    assert response.headers["www-authenticate"].startswith("Basic")
    assert header not in response.text
    assert calls == []


def test_unauthenticated_malformed_json_is_rejected_before_parsing():
    client, calls = make_client()
    response = client.post(
        "/chat", content='{"message":"private', headers={"Content-Type": "application/json"}
    )
    assert response.status_code == 401
    assert "private" not in response.text
    assert calls == []


def test_trailing_slash_cannot_bypass_authentication():
    client, calls = make_client()
    response = client.post("/chat/", json={"message": "hi"}, follow_redirects=False)
    assert response.status_code == 401
    assert calls == []


def test_proxy_root_path_cannot_bypass_authentication_or_limits():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, json=MODEL_RESPONSE)

    app = create_app(httpx.MockTransport(handler), clock=Clock())
    client = TestClient(app, root_path="/service")
    assert client.post("/service/chat", json={"message": "hi"}).status_code == 401
    for _ in range(2):
        assert client.post(
            "/service/chat", auth=ALICE, json={"message": "hi"}
        ).status_code == 200
    limited = client.post("/service/chat", auth=ALICE, json={"message": "hi"})
    assert limited.status_code == 429
    assert limited.headers["retry-after"] == "60"
    assert len(calls) == 2


def test_mounted_app_authenticates_before_parsing():
    from fastapi import FastAPI

    app = create_app(httpx.MockTransport(lambda r: httpx.Response(200, json=MODEL_RESPONSE)))
    parent = FastAPI()
    parent.mount("/nested", app)
    client = TestClient(parent)
    response = client.post(
        "/nested/chat", content='{"message":"private', headers={"Content-Type": "application/json"}
    )
    assert response.status_code == 401
    assert "private" not in response.text


def test_sliding_window_limit_retry_after_and_exact_expiry():
    clock = Clock()
    client, calls = make_client(clock)
    assert send(client).status_code == 200
    clock.now += 10
    assert send(client).status_code == 200
    clock.now += 30.25
    response = send(client)
    assert response.status_code == 429
    assert response.headers["retry-after"] == str(math.ceil(19.75))
    assert len(calls) == 2
    clock.now = 1060.0
    assert send(client).status_code == 200
    assert len(calls) == 3
    assert send(client).status_code == 429
    clock.now = 1070.0
    assert send(client).status_code == 200


def test_users_have_independent_limits_and_headers_cannot_spoof_identity():
    client, calls = make_client(Clock())
    assert send(client).status_code == 200
    assert send(client).status_code == 200
    response = send(client, headers={"X-User-ID": "bob", "X-Forwarded-For": "1.2.3.4"})
    assert response.status_code == 429
    assert send(client, auth=BOB).status_code == 200
    assert len(calls) == 3


def test_failed_logins_do_not_consume_the_users_quota():
    client, calls = make_client(Clock())
    for _ in range(3):
        assert send(client, auth=("alice", "incorrect")).status_code == 401
    assert send(client).status_code == 200
    assert send(client).status_code == 200
    assert send(client).status_code == 429
    assert len(calls) == 2


def test_invalid_input_and_provider_errors_count_as_authenticated_attempts():
    client, calls = make_client(Clock(), provider_status=503)
    invalid = client.post("/chat", auth=ALICE, json={"message": " "})
    assert invalid.status_code == 422
    assert send(client).status_code == 503
    assert send(client).status_code == 429
    assert len(calls) == 1


def test_limit_is_shared_across_clients_not_reset_per_connection():
    clock = Clock()
    app = create_app(
        httpx.MockTransport(lambda r: httpx.Response(200, json=MODEL_RESPONSE)), clock=clock
    )
    first, second = TestClient(app), TestClient(app)
    assert send(first).status_code == 200
    assert send(second).status_code == 200
    assert send(first).status_code == 429


def test_limiter_reservations_are_atomic_under_concurrency():
    limiter = UserRateLimiter(3, 60, Clock())

    def check(_):
        try:
            limiter.check("alice")
            return 200
        except HTTPException as exc:
            assert exc.headers["Retry-After"] == "60"
            return exc.status_code

    with ThreadPoolExecutor(max_workers=10) as pool:
        statuses = list(pool.map(check, range(30)))
    assert statuses.count(200) == 3
    assert statuses.count(429) == 27


@pytest.mark.parametrize(
    "value",
    ["", "{}", "not-json", "[]", "null", '{"alice":"plaintext-password"}',
     '{"bad user":"private-hash-value"}'],
)
def test_invalid_authentication_config_fails_closed(monkeypatch, value, caplog):
    monkeypatch.setenv("CHAT_AUTH_USERS", value)
    client, calls = make_client()
    with caplog.at_level(logging.INFO):
        response = send(client)
    assert response.status_code == 503
    assert calls == []
    assert "plaintext-password" not in response.text + caplog.text
    assert "private-hash-value" not in response.text + caplog.text


@pytest.mark.parametrize(
    "name,value",
    [
        ("CHAT_RATE_LIMIT_REQUESTS", "0"),
        ("CHAT_RATE_LIMIT_REQUESTS", "-1"),
        ("CHAT_RATE_LIMIT_REQUESTS", "10001"),
        ("CHAT_RATE_LIMIT_REQUESTS", "bad"),
        ("CHAT_RATE_LIMIT_WINDOW_SECONDS", "0"),
        ("CHAT_RATE_LIMIT_WINDOW_SECONDS", "86401"),
        ("CHAT_RATE_LIMIT_WINDOW_SECONDS", "0.5"),
    ],
)
def test_invalid_rate_config_fails_closed(monkeypatch, name, value):
    monkeypatch.setenv(name, value)
    client, calls = make_client()
    assert send(client).status_code == 503
    assert calls == []


def test_hashes_are_salted_and_password_verification_works():
    first = hash_password(ALICE[1])
    second = hash_password(ALICE[1])
    assert first != second
    assert ALICE[1] not in first
    assert verify_password(ALICE[1], first)
    assert not verify_password("incorrect-password", first)
    assert not verify_password("x" * 257, first)


@pytest.mark.parametrize("password", ["short", "ع" * 16, "x" * 257])
def test_enrollment_rejects_invalid_passwords(password):
    with pytest.raises(ValueError):
        hash_password(password)


def test_account_helper_writes_hash_only_preserves_config_and_permissions(tmp_path, capsys):
    env = tmp_path / ".env"
    env.write_text("GROQ_MODEL=openai/gpt-oss-20b\nGROQ_FREE_PLAN_CONFIRMED=true\n")
    add_user(env, *ALICE)
    add_user(env, *BOB)
    values = dotenv_values(env)
    users = parse_users(values["CHAT_AUTH_USERS"])
    assert set(users) == {"alice", "bob"}
    assert verify_password(ALICE[1], users["alice"])
    assert values["GROQ_MODEL"] == "openai/gpt-oss-20b"
    assert values["GROQ_FREE_PLAN_CONFIRMED"] == "true"
    assert env.stat().st_mode & 0o777 == 0o600
    assert ALICE[1] not in env.read_text()
    assert BOB[1] not in env.read_text()
    assert capsys.readouterr().out == ""


def test_account_helper_creates_a_private_env_file(tmp_path):
    env = tmp_path / ".env"
    add_user(env, *ALICE)
    assert env.stat().st_mode & 0o777 == 0o600
    assert verify_password(ALICE[1], parse_users(dotenv_values(env)["CHAT_AUTH_USERS"])["alice"])


def test_account_helper_rejects_tracked_template_and_symlink(tmp_path):
    with pytest.raises(ValueError):
        add_user(tmp_path / ".env.example", *ALICE)
    target = tmp_path / "target"
    target.write_text("unchanged")
    link = tmp_path / ".env"
    link.symlink_to(target)
    with pytest.raises(ValueError):
        add_user(link, *ALICE)
    assert target.read_text() == "unchanged"


def test_openapi_documents_http_basic_without_configuration_secrets(user_hashes):
    client, calls = make_client()
    response = client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()
    assert schema["components"]["securitySchemes"]["HTTPBasic"]["scheme"] == "basic"
    assert schema["paths"]["/chat"]["post"]["security"] == [{"HTTPBasic": []}]
    for secret in (ALICE[1], PROVIDER_KEY, user_hashes["alice"]):
        assert secret not in response.text
    assert calls == []
