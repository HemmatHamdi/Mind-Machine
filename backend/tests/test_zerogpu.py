"""Offline API + adapter tests: fake Space clients and temporary central ledgers."""

import asyncio
import json
import logging
import sqlite3

import pytest
from fastapi.testclient import TestClient

from conftest import KEY
from dispatch_auth import Dispatch, verify_dispatch
from ledger_store import CentralLedger, SqliteFileBackend
from main import AI_UNAVAILABLE_MESSAGE, create_app
from security import hash_password
from zerogpu import GenerationUnavailable, ZeroGPUAdapter

PASSWORD = "offline-test-password-only"
PASSWORD_HASH = hash_password(PASSWORD)
MESSAGE = "synthetic offline test message"


class FakeSpace:
    """Stands in for the private Space: optionally performs the admission claim."""

    def __init__(self, ledger, reply="Synthetic offline reply", error=None, claims=True):
        self.ledger, self.reply, self.error, self.claims = ledger, reply, error, claims
        self.calls = []

    async def generate(self, message, *, max_new_tokens, dispatch):
        self.calls.append((message, max_new_tokens, dispatch))
        if self.claims:
            self.ledger.claim(dispatch.id, dispatch.tag)
        if self.error is not None:
            raise self.error
        return self.reply


@pytest.fixture(autouse=True)
def accounts(monkeypatch):
    monkeypatch.setenv("CHAT_AUTH_USERS", json.dumps({"offline-user": PASSWORD_HASH}))
    monkeypatch.setenv("CHAT_RATE_LIMIT_REQUESTS", "1000")
    monkeypatch.setenv("CHAT_RATE_LIMIT_WINDOW_SECONDS", "60")


def client_for(space, ledger, **kwargs):
    adapter = ZeroGPUAdapter(space, ledger, dispatch_key=KEY, **kwargs)
    client = TestClient(create_app(generator=adapter))
    client.auth = ("offline-user", PASSWORD)
    return client


def budget_row(ledger):
    with sqlite3.connect(ledger.backend.path) as db:
        return db.execute("SELECT attempts_left, active_job FROM budget").fetchone()


def test_fake_success_preserves_contract_privacy_and_dispatch_binding(
    ledger, caplog, no_outbound_network, clock,
):
    space = FakeSpace(ledger)
    with caplog.at_level(logging.INFO):
        response = client_for(space, ledger).post("/chat", json={"message": f"  {MESSAGE}  "})
    assert response.status_code == 200
    assert response.json() == {"reply": "Synthetic offline reply"}
    assert response.headers["cache-control"] == "no-store"
    message, tokens, dispatch = space.calls[0]
    assert (message, tokens) == (MESSAGE, 128)
    assert verify_dispatch(KEY, dispatch.id, dispatch.issued_at, 128, MESSAGE,
                           dispatch.tag, clock[0])
    assert not verify_dispatch(KEY, dispatch.id, dispatch.issued_at, 128, "other",
                               dispatch.tag, clock[0])
    assert MESSAGE not in caplog.text and PASSWORD not in caplog.text + response.text
    assert MESSAGE.encode() not in ledger.backend.path.read_bytes()
    assert budget_row(ledger) == (5, None)
    assert no_outbound_network == []


def test_default_app_cannot_be_activated_by_environment(monkeypatch):
    for setting in ("HF_TOKEN", "HF_SPACE_ID", "LIBSQL_URL", "LIBSQL_AUTH_TOKEN",
                    "ZEROGPU_ENABLED", "ZEROGPU_EXECUTION_APPROVED"):
        monkeypatch.setenv(setting, "synthetic-unused-setting")
    response = TestClient(create_app()).post(
        "/chat", json={"message": MESSAGE}, auth=("offline-user", PASSWORD))
    assert response.status_code == 503
    assert response.json() == {"detail": AI_UNAVAILABLE_MESSAGE}


@pytest.mark.parametrize("auth", [None, ("offline-user", "wrong-test-password")])
def test_rejected_auth_does_not_dispatch_or_charge(ledger, auth):
    space = FakeSpace(ledger)
    adapter = ZeroGPUAdapter(space, ledger, dispatch_key=KEY)
    response = TestClient(create_app(generator=adapter)).post(
        "/chat", json={"message": MESSAGE}, auth=auth)
    assert response.status_code == 401
    assert not space.calls
    assert budget_row(ledger) == (6, None)


def test_invalid_body_never_reaches_space(ledger):
    space = FakeSpace(ledger)
    assert client_for(space, ledger).post("/chat", json={"message": " "}).status_code == 422
    assert not space.calls
    assert budget_row(ledger) == (6, None)


def test_rate_limit_precedes_dispatch(ledger, monkeypatch):
    monkeypatch.setenv("CHAT_RATE_LIMIT_REQUESTS", "1")
    space = FakeSpace(ledger)
    client = client_for(space, ledger)
    assert client.post("/chat", json={"message": MESSAGE}).status_code == 200
    assert client.post("/chat", json={"message": MESSAGE}).status_code == 429
    assert len(space.calls) == 1


def test_six_attempts_shared_across_users_and_restarts(backend, ledger, clock, monkeypatch):
    monkeypatch.setenv("CHAT_AUTH_USERS", json.dumps(
        {"first": PASSWORD_HASH, "second": PASSWORD_HASH}))
    space = FakeSpace(ledger)
    for i in range(6):
        reopened = CentralLedger(SqliteFileBackend(backend.path), clock=lambda: clock[0])
        space.ledger = reopened
        response = client_for(space, reopened).post(
            "/chat", json={"message": MESSAGE}, auth=(["first", "second"][i % 2], PASSWORD))
        assert response.status_code == 200
    response = client_for(space, ledger).post(
        "/chat", json={"message": MESSAGE}, auth=("first", PASSWORD))
    assert response.status_code == 503 and response.headers["cache-control"] == "no-store"
    assert len(space.calls) == 6
    assert budget_row(ledger) == (0, None)


def test_space_that_never_claims_cannot_complete_and_locks_job(ledger):
    space = FakeSpace(ledger, claims=False)
    client = client_for(space, ledger)
    assert client.post("/chat", json={"message": MESSAGE}).status_code == 503
    assert client.post("/chat", json={"message": MESSAGE}).status_code == 503
    assert len(space.calls) == 1
    assert budget_row(ledger)[1] is not None


def test_unarmed_or_unavailable_storage_never_dispatches(backend, clock):
    unarmed = CentralLedger(backend, clock=lambda: clock[0])
    space = FakeSpace(unarmed)
    assert client_for(space, unarmed).post("/chat", json={"message": MESSAGE}).status_code == 503
    assert not space.calls


def test_database_errors_fail_closed_without_raw_error(ledger, caplog):
    ledger.backend.path.write_bytes(b"synthetic invalid SQLite data")
    space = FakeSpace(ledger)
    response = client_for(space, ledger).post("/chat", json={"message": MESSAGE})
    assert response.status_code == 503 and not space.calls
    assert "SQLite" not in response.text + caplog.text
    assert str(ledger.backend.path) not in response.text + caplog.text


@pytest.mark.parametrize("reply", [None, "", " ", ["invalid"], "x" * 8_001])
def test_invalid_result_stops_future_attempts(ledger, reply):
    space = FakeSpace(ledger, reply=reply)
    client = client_for(space, ledger)
    assert client.post("/chat", json={"message": MESSAGE}).status_code == 503
    assert client.post("/chat", json={"message": MESSAGE}).status_code == 503
    assert len(space.calls) == 1


def test_client_failure_is_sanitized_not_retried_or_refunded(ledger, caplog):
    space = FakeSpace(ledger, error=RuntimeError(MESSAGE + PASSWORD))
    client = client_for(space, ledger)
    with caplog.at_level(logging.INFO):
        first = client.post("/chat", json={"message": MESSAGE})
        later = client.post("/chat", json={"message": MESSAGE})
    assert first.status_code == later.status_code == 503
    assert len(space.calls) == 1
    assert MESSAGE not in first.text + caplog.text and PASSWORD not in first.text + caplog.text
    assert budget_row(ledger)[0] == 5


def test_timeout_quarantines_job_across_restart(backend, ledger, clock):
    class Slow(FakeSpace):
        async def generate(self, message, *, max_new_tokens, dispatch):
            self.calls.append(True)
            await asyncio.sleep(10)

    space = Slow(ledger)
    assert client_for(space, ledger, wait_timeout_seconds=0.001).post(
        "/chat", json={"message": MESSAGE}).status_code == 503
    reopened = CentralLedger(SqliteFileBackend(backend.path), clock=lambda: clock[0])
    assert client_for(space, reopened).post("/chat", json={"message": MESSAGE}).status_code == 503
    assert len(space.calls) == 1


def test_request_cancellation_keeps_job_quarantined(ledger):
    class Waiting(FakeSpace):
        async def generate(self, message, *, max_new_tokens, dispatch):
            await asyncio.Event().wait()

    async def exercise():
        task = asyncio.create_task(
            ZeroGPUAdapter(Waiting(ledger), ledger, dispatch_key=KEY).generate("test"))
        await asyncio.sleep(0.01)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(exercise())
    assert budget_row(ledger)[1] is not None
    with pytest.raises(GenerationUnavailable):
        ledger.reserve("a" * 32, "b" * 64)


@pytest.mark.parametrize("timeout", [0, -1, True, float("inf"), float("nan"), 121, "60"])
def test_invalid_wait_timeouts_are_rejected(ledger, timeout):
    with pytest.raises(ValueError):
        ZeroGPUAdapter(FakeSpace(ledger), ledger, dispatch_key=KEY,
                       wait_timeout_seconds=timeout)


def test_short_dispatch_key_is_rejected_before_any_charge(ledger):
    adapter = ZeroGPUAdapter(FakeSpace(ledger), ledger, dispatch_key="short")
    with pytest.raises(GenerationUnavailable):
        asyncio.run(adapter.generate("synthetic"))
    assert budget_row(ledger) == (6, None)
