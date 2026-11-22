import base64
import json
import logging
import math
from concurrent.futures import ThreadPoolExecutor

import pytest
from dotenv import dotenv_values
from fastapi import HTTPException
from fastapi.testclient import TestClient

from create_chat_user import add_user
from main import AI_UNAVAILABLE_MESSAGE, create_app
from security import UserRateLimiter, hash_password, parse_users, verify_password


# Synthetic test accounts only; never provisioned in a real environment.
ALICE = ("alice", "fake-alice-password-123")
BOB = ("bob", "fake-bob-password-456")
PRIVATE_PROMPT = "private chat input for tests"


@pytest.fixture(scope="module")
def user_hashes():
    return {ALICE[0]: hash_password(ALICE[1]), BOB[0]: hash_password(BOB[1])}


@pytest.fixture(autouse=True)
def configure(monkeypatch, user_hashes):
    monkeypatch.setenv("CHAT_AUTH_USERS", json.dumps(user_hashes))
    monkeypatch.setenv("CHAT_RATE_LIMIT_REQUESTS", "2")
    monkeypatch.setenv("CHAT_RATE_LIMIT_WINDOW_SECONDS", "60")


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def make_client(clock=None):
    return TestClient(create_app(**({"clock": clock} if clock else {})))


def send(client, auth=ALICE, **kwargs):
    return client.post("/chat", auth=auth, json={"message": PRIVATE_PROMPT}, **kwargs)


def test_authenticated_chat_is_unavailable_without_echoing_private_data(caplog):
    with caplog.at_level(logging.INFO):
        response = send(make_client())
    assert response.status_code == 503
    assert response.json() == {"detail": AI_UNAVAILABLE_MESSAGE}
    assert response.headers["cache-control"] == "no-store"
    for private in (ALICE[1], PRIVATE_PROMPT):
        assert private not in response.text + caplog.text


@pytest.mark.parametrize("auth", [None, ("alice", "wrong"), ("unknown", ALICE[1])])
def test_unauthorized_requests_are_generic_and_never_call_provider(auth, caplog):
    with caplog.at_level(logging.INFO):
        response = send(make_client(), auth=auth)
    assert response.status_code == 401
    assert response.headers["www-authenticate"].startswith("Basic")
    assert response.headers["cache-control"] == "no-store"
    for private in (ALICE[1], PRIVATE_PROMPT):
        assert private not in response.text + caplog.text


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
    response = make_client().post(
        "/chat", headers={"Authorization": header}, json={"message": "hi"}
    )
    assert response.status_code == 401
    assert response.headers["www-authenticate"].startswith("Basic")
    assert header not in response.text


def test_unauthenticated_malformed_json_is_rejected_before_parsing():
    response = make_client().post(
        "/chat", content='{"message":"private', headers={"Content-Type": "application/json"}
    )
    assert response.status_code == 401
    assert "private" not in response.text


def test_trailing_slash_cannot_bypass_authentication():
    response = make_client().post("/chat/", json={"message": "hi"}, follow_redirects=False)
    assert response.status_code == 401


def test_proxy_root_path_cannot_bypass_authentication_or_limits():
    client = TestClient(create_app(clock=Clock()), root_path="/service")
    assert client.post("/service/chat", json={"message": "hi"}).status_code == 401
    for _ in range(2):
        response = client.post("/service/chat", auth=ALICE, json={"message": "hi"})
        assert response.status_code == 503
        assert response.json() == {"detail": AI_UNAVAILABLE_MESSAGE}
    limited = client.post("/service/chat", auth=ALICE, json={"message": "hi"})
    assert limited.status_code == 429
    assert limited.headers["retry-after"] == "60"


def test_mounted_app_authenticates_before_parsing():
    from fastapi import FastAPI

    parent = FastAPI()
    parent.mount("/nested", create_app())
    client = TestClient(parent)
    response = client.post(
        "/nested/chat", content='{"message":"private', headers={"Content-Type": "application/json"}
    )
    assert response.status_code == 401
    assert "private" not in response.text


def test_sliding_window_limit_retry_after_and_exact_expiry():
    clock = Clock()
    client = make_client(clock)
    assert send(client).status_code == 503
    clock.now += 10
    assert send(client).status_code == 503
    clock.now += 30.25
    response = send(client)
    assert response.status_code == 429
    assert response.headers["retry-after"] == str(math.ceil(19.75))
    clock.now = 1060.0
    assert send(client).status_code == 503
    assert send(client).status_code == 429
    clock.now = 1070.0
    assert send(client).status_code == 503


def test_users_have_independent_limits_and_headers_cannot_spoof_identity():
    client = make_client(Clock())
    assert send(client).status_code == 503
    assert send(client).status_code == 503
    response = send(client, headers={"X-User-ID": "bob", "X-Forwarded-For": "1.2.3.4"})
    assert response.status_code == 429
    assert send(client, auth=BOB).status_code == 503


def test_failed_logins_do_not_consume_the_users_quota():
    client = make_client(Clock())
    for _ in range(3):
        assert send(client, auth=("alice", "incorrect")).status_code == 401
    assert send(client).status_code == 503
    assert send(client).status_code == 503
    assert send(client).status_code == 429


def test_invalid_input_and_unavailability_count_as_authenticated_attempts():
    client = make_client(Clock())
    assert client.post("/chat", auth=ALICE, json={"message": " "}).status_code == 422
    assert send(client).status_code == 503
    response = send(client)
    assert response.status_code == 429
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["retry-after"] == "60"


def test_limit_is_shared_across_clients_not_reset_per_connection():
    app = create_app(clock=Clock())
    first, second = TestClient(app), TestClient(app)
    assert send(first).status_code == 503
    assert send(second).status_code == 503
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
    with caplog.at_level(logging.INFO):
        response = send(make_client())
    assert response.status_code == 503
    assert response.json()["detail"] == "Chat security is not configured. Contact the administrator."
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
    response = send(make_client())
    assert response.status_code == 503
    assert "Chat security is not configured" in response.json()["detail"]


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
    env.write_text("CHAT_RATE_LIMIT_REQUESTS=7\nCHAT_RATE_LIMIT_WINDOW_SECONDS=120\n")
    add_user(env, *ALICE)
    add_user(env, *BOB)
    values = dotenv_values(env)
    users = parse_users(values["CHAT_AUTH_USERS"])
    assert set(users) == {"alice", "bob"}
    assert verify_password(ALICE[1], users["alice"])
    assert values["CHAT_RATE_LIMIT_REQUESTS"] == "7"
    assert values["CHAT_RATE_LIMIT_WINDOW_SECONDS"] == "120"
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
    response = make_client().get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()
    assert schema["components"]["securitySchemes"]["HTTPBasic"]["scheme"] == "basic"
    assert schema["paths"]["/chat"]["post"]["security"] == [{"HTTPBasic": []}]
    for secret in (ALICE[1], user_hashes["alice"]):
        assert secret not in response.text
