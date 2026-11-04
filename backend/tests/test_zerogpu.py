"""Offline integration only: fake Space clients and temporary budget databases."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import json
import logging
import sqlite3

import pytest
from fastapi.testclient import TestClient

from dispatch_auth import verify_dispatch
from main import AI_UNAVAILABLE_MESSAGE, create_app
from security import hash_password
from zerogpu import (
    GenerationUnavailable, ManualQuotaSnapshot, QuotaBudget, ZeroGPUAdapter,
)


KEY = "synthetic-backend-key-not-real-" * 2
PASSWORD = "offline-test-password-only"
PASSWORD_HASH = hash_password(PASSWORD)
SYNTHETIC_MESSAGE = "synthetic offline test message"


class FakeSpace:
    def __init__(self, reply="Synthetic offline reply", error=None):
        self.reply = reply
        self.error = error
        self.calls = []

    async def generate(self, message, *, max_new_tokens, dispatch):
        self.calls.append((message, max_new_tokens, dispatch))
        if self.error is not None:
            raise self.error
        return self.reply


@pytest.fixture(autouse=True)
def accounts(monkeypatch):
    monkeypatch.setenv("CHAT_AUTH_USERS", json.dumps({"offline-user": PASSWORD_HASH}))
    monkeypatch.setenv("CHAT_RATE_LIMIT_REQUESTS", "1000")
    monkeypatch.setenv("CHAT_RATE_LIMIT_WINDOW_SECONDS", "60")


@pytest.fixture
def clock():
    return [1_000_000.0]


@pytest.fixture
def snapshot(clock):
    return ManualQuotaSnapshot(
        observed_at=clock[0], gpu_seconds_remaining=300, runs_remaining=8,
        overquota_used=0, personal_free_account_confirmed=True,
        paid_usage_disabled_confirmed=True,
    )


@pytest.fixture
def budget(tmp_path, clock, snapshot):
    result = QuotaBudget(tmp_path / ".zerogpu-budget.sqlite3", clock=lambda: clock[0])
    result.arm(snapshot)
    return result


def client_for(space, budget, **kwargs):
    client = TestClient(create_app(generator=ZeroGPUAdapter(space, budget, dispatch_key=KEY, **kwargs)))
    client.auth = ("offline-user", PASSWORD)
    return client


def test_fake_success_preserves_contract_and_privacy(budget, caplog, no_outbound_network, clock):
    space = FakeSpace()
    with caplog.at_level(logging.INFO):
        response = client_for(space, budget).post(
            "/chat", json={"message": f"  {SYNTHETIC_MESSAGE}  "}
        )
    assert response.status_code == 200
    assert response.json() == {"reply": "Synthetic offline reply"}
    assert response.headers["cache-control"] == "no-store"
    assert [c[:2] for c in space.calls] == [(SYNTHETIC_MESSAGE, 128)]
    dispatch = space.calls[0][2]
    assert verify_dispatch(KEY, dispatch.id, dispatch.issued_at, 128, SYNTHETIC_MESSAGE,
                           dispatch.tag, clock[0])
    assert not verify_dispatch(KEY, dispatch.id, dispatch.issued_at, 128, 'other',
                               dispatch.tag, clock[0])
    assert SYNTHETIC_MESSAGE not in caplog.text
    assert PASSWORD not in caplog.text + response.text
    assert no_outbound_network == []
    assert SYNTHETIC_MESSAGE.encode() not in budget.path.read_bytes()


def test_default_app_cannot_be_activated_by_environment(monkeypatch):
    for setting in (
        "HF_TOKEN", "HF_SPACE_ID", "HF_MODEL_ID", "ZEROGPU_ENABLED",
        "ZEROGPU_FREE_ONLY", "ZEROGPU_QUOTA_CONFIRMED",
    ):
        monkeypatch.setenv(setting, "synthetic-unused-setting")
    client = TestClient(create_app())
    response = client.post(
        "/chat", json={"message": SYNTHETIC_MESSAGE}, auth=("offline-user", PASSWORD)
    )
    assert response.status_code == 503
    assert response.json() == {"detail": AI_UNAVAILABLE_MESSAGE}


@pytest.mark.parametrize("auth", [None, ("offline-user", "wrong-test-password")])
def test_rejected_auth_does_not_dispatch_or_charge(budget, auth):
    space = FakeSpace()
    client = TestClient(create_app(generator=ZeroGPUAdapter(space, budget, dispatch_key=KEY)))
    response = client.post("/chat", json={"message": SYNTHETIC_MESSAGE}, auth=auth)
    assert response.status_code == 401
    assert response.headers["www-authenticate"].startswith("Basic")
    assert response.headers["cache-control"] == "no-store"
    assert not space.calls
    reservation = budget.reserve()
    budget.finish(reservation)
    with sqlite3.connect(budget.path) as db:
        assert db.execute("SELECT attempts_left FROM budget").fetchone() == (5,)


def test_user_rate_limit_precedes_dispatch(budget, monkeypatch):
    monkeypatch.setenv("CHAT_RATE_LIMIT_REQUESTS", "1")
    space = FakeSpace()
    client = client_for(space, budget)
    assert client.post("/chat", json={"message": SYNTHETIC_MESSAGE}).status_code == 200
    response = client.post("/chat", json={"message": SYNTHETIC_MESSAGE})
    assert response.status_code == 429
    assert int(response.headers["retry-after"]) >= 1
    assert len(space.calls) == 1


def test_invalid_body_never_reaches_space(budget):
    space = FakeSpace()
    response = client_for(space, budget).post("/chat", json={"message": " "})
    assert response.status_code == 422
    assert not space.calls


def test_six_attempts_are_shared_across_restarts(budget, clock):
    space = FakeSpace()
    for _ in range(6):
        reopened = QuotaBudget(budget.path, clock=lambda: clock[0])
        response = client_for(space, reopened).post(
            "/chat", json={"message": SYNTHETIC_MESSAGE}
        )
        assert response.status_code == 200
    response = client_for(space, budget).post("/chat", json={"message": SYNTHETIC_MESSAGE})
    assert response.status_code == 503
    assert response.headers["cache-control"] == "no-store"
    assert len(space.calls) == 6
    with sqlite3.connect(budget.path) as db:
        assert db.execute(
            "SELECT attempts_left, gpu_seconds_left, active_job FROM budget"
        ).fetchone() == (0, 0, None)


def test_budget_is_shared_between_distinct_authenticated_users(budget, monkeypatch):
    monkeypatch.setenv(
        "CHAT_AUTH_USERS",
        json.dumps({"first-user": PASSWORD_HASH, "second-user": PASSWORD_HASH}),
    )
    space = FakeSpace()
    client = client_for(space, budget)
    for index in range(6):
        response = client.post(
            "/chat", json={"message": SYNTHETIC_MESSAGE},
            auth=(("first-user" if index % 2 else "second-user"), PASSWORD),
        )
        assert response.status_code == 200
    response = client.post(
        "/chat", json={"message": SYNTHETIC_MESSAGE}, auth=("second-user", PASSWORD)
    )
    assert response.status_code == 503
    assert len(space.calls) == 6


@pytest.mark.parametrize(
    "change",
    [
        {"observed_at": 999_939.0}, {"observed_at": 1_000_001.0},
        {"observed_at": float("nan")}, {"observed_at": True},
        {"gpu_seconds_remaining": 0},
        {"gpu_seconds_remaining": 89}, {"gpu_seconds_remaining": 301},
        {"gpu_seconds_remaining": True}, {"gpu_seconds_remaining": 300.0},
        {"runs_remaining": 2}, {"runs_remaining": 9}, {"runs_remaining": "8"},
        {"overquota_used": 1}, {"overquota_used": False},
        {"personal_free_account_confirmed": False},
        {"paid_usage_disabled_confirmed": False},
    ],
)
def test_arming_requires_fresh_conservative_free_quota(tmp_path, clock, snapshot, change):
    ledger = QuotaBudget(tmp_path / "budget.sqlite3", clock=lambda: clock[0])
    with pytest.raises(GenerationUnavailable):
        ledger.arm(replace(snapshot, **change))
    with pytest.raises(GenerationUnavailable):
        ledger.reserve()


def test_lower_snapshot_reduces_attempts_and_preserves_reserve(tmp_path, clock, snapshot):
    ledger = QuotaBudget(tmp_path / "budget.sqlite3", clock=lambda: clock[0])
    ledger.arm(replace(snapshot, gpu_seconds_remaining=150, runs_remaining=4))
    for _ in range(2):
        ledger.finish(ledger.reserve())
    with pytest.raises(GenerationUnavailable):
        ledger.reserve()


def test_armed_window_cannot_be_reset_or_replenished(budget, snapshot):
    reservation = budget.reserve()
    budget.finish(reservation)
    with pytest.raises(GenerationUnavailable):
        budget.arm(snapshot)


def test_expiry_fails_closed_until_a_new_manual_snapshot(budget, clock, snapshot):
    clock[0] += 86_400
    with pytest.raises(GenerationUnavailable):
        budget.reserve()
    with pytest.raises(GenerationUnavailable):
        budget.arm(snapshot)
    budget.arm(replace(snapshot, observed_at=clock[0]))
    budget.finish(budget.reserve())


def test_one_active_job_is_atomic_across_ledger_instances(budget, clock):
    def reserve():
        ledger = QuotaBudget(budget.path, clock=lambda: clock[0])
        try:
            return ledger.reserve()
        except GenerationUnavailable:
            return None

    with ThreadPoolExecutor(max_workers=8) as workers:
        results = list(workers.map(lambda _: reserve(), range(8)))
    accepted = [value for value in results if value is not None]
    assert len(accepted) == 1
    budget.finish(accepted[0])
    with sqlite3.connect(budget.path) as db:
        assert db.execute("SELECT attempts_left FROM budget").fetchone() == (5,)


def test_unarmed_or_missing_budget_never_dispatches(tmp_path, clock):
    ledger = QuotaBudget(tmp_path / "unarmed.sqlite3", clock=lambda: clock[0])
    space = FakeSpace()
    response = client_for(space, ledger).post("/chat", json={"message": SYNTHETIC_MESSAGE})
    assert response.status_code == 503
    assert not space.calls


def test_database_errors_fail_closed_without_raw_error(budget, caplog):
    budget.path.write_bytes(b"synthetic invalid SQLite data")
    space = FakeSpace()
    response = client_for(space, budget).post("/chat", json={"message": SYNTHETIC_MESSAGE})
    assert response.status_code == 503
    assert not space.calls
    assert "SQLite" not in response.text + caplog.text
    assert str(budget.path) not in response.text + caplog.text


@pytest.mark.parametrize("reply", [None, "", " ", ["invalid"], "x" * 8_001])
def test_invalid_result_stops_future_attempts(budget, reply):
    space = FakeSpace(reply=reply)
    client = client_for(space, budget)
    assert client.post("/chat", json={"message": SYNTHETIC_MESSAGE}).status_code == 503
    assert client.post("/chat", json={"message": SYNTHETIC_MESSAGE}).status_code == 503
    assert len(space.calls) == 1


def test_client_failure_is_sanitized_not_retried_or_refunded(budget, caplog, clock, snapshot):
    space = FakeSpace(error=RuntimeError(SYNTHETIC_MESSAGE + PASSWORD))
    client = client_for(space, budget)
    with caplog.at_level(logging.INFO):
        response = client.post("/chat", json={"message": SYNTHETIC_MESSAGE})
        later = client.post("/chat", json={"message": SYNTHETIC_MESSAGE})
    assert response.status_code == later.status_code == 503
    assert len(space.calls) == 1
    assert SYNTHETIC_MESSAGE not in response.text + caplog.text
    assert PASSWORD not in response.text + caplog.text
    clock[0] += 86_400
    reopened = QuotaBudget(budget.path, clock=lambda: clock[0])
    with pytest.raises(GenerationUnavailable):
        reopened.arm(replace(snapshot, observed_at=clock[0]))


def test_timeout_quarantines_job_across_restart(budget, clock):
    class SlowSpace(FakeSpace):
        async def generate(self, message, *, max_new_tokens, dispatch):
            self.calls.append(True)
            await asyncio.sleep(10)
            return self.reply

    space = SlowSpace()
    response = client_for(space, budget, wait_timeout_seconds=0.001).post(
        "/chat", json={"message": SYNTHETIC_MESSAGE}
    )
    assert response.status_code == 503
    reopened = QuotaBudget(budget.path, clock=lambda: clock[0])
    response = client_for(space, reopened).post("/chat", json={"message": SYNTHETIC_MESSAGE})
    assert response.status_code == 503
    assert len(space.calls) == 1


def test_request_cancellation_keeps_job_quarantined(budget):
    class WaitingSpace(FakeSpace):
        async def generate(self, message, *, max_new_tokens, dispatch):
            await asyncio.Event().wait()

    async def exercise():
        task = asyncio.create_task(ZeroGPUAdapter(WaitingSpace(), budget, dispatch_key=KEY).generate("test"))
        await asyncio.sleep(0.01)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    asyncio.run(exercise())
    with pytest.raises(GenerationUnavailable):
        budget.reserve()


@pytest.mark.parametrize("timeout", [0, -1, True, float("inf"), float("nan"), 121, "60"])
def test_invalid_wait_timeouts_are_rejected(budget, timeout):
    with pytest.raises(ValueError):
        ZeroGPUAdapter(FakeSpace(), budget, dispatch_key=KEY, wait_timeout_seconds=timeout)


def test_new_budget_file_is_private_and_cannot_follow_symlinks(tmp_path, clock):
    path = tmp_path / "budget.sqlite3"
    QuotaBudget(path, clock=lambda: clock[0])
    assert path.stat().st_mode & 0o777 == 0o600
    link = tmp_path / "link.sqlite3"
    link.symlink_to(path)
    with pytest.raises(OSError):
        QuotaBudget(link, clock=lambda: clock[0])


def test_init_ledger_tool_arms_only_with_confirmations(tmp_path):
    import init_ledger
    path = tmp_path / "ledger.sqlite3"
    base = ["--path", str(path), "--gpu-seconds-remaining", "300", "--runs-remaining", "8"]
    assert init_ledger.main(base) == 1  # missing confirmations: not armed
    assert init_ledger.main(base + ["--confirm-free-account", "--confirm-no-paid-usage"]) == 0
    assert path.stat().st_mode & 0o777 == 0o600
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT attempts_left FROM budget").fetchone() == (6,)
    assert init_ledger.main(["--path", "relative.db", "--gpu-seconds-remaining", "300",
                             "--runs-remaining", "8"]) == 2
