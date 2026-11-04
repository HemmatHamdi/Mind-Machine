"""Fail every test if application code attempts outbound networking."""

import socket

import httpx
import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def no_outbound_network(monkeypatch):
    attempts = []
    original_send = httpx.Client.send

    def deny(*args, **kwargs):
        # Record only a count: never URLs, headers, credentials, or user content.
        attempts.append(True)
        raise AssertionError("Outbound networking is prohibited in this test suite.")

    def send(client, *args, **kwargs):
        if not isinstance(client, TestClient):
            return deny()
        return original_send(client, *args, **kwargs)

    monkeypatch.setattr(httpx.Client, "send", send)
    monkeypatch.setattr(httpx.AsyncClient, "send", deny)
    monkeypatch.setattr(socket, "getaddrinfo", deny)
    monkeypatch.setattr(socket.socket, "connect", deny)
    monkeypatch.setattr(socket.socket, "connect_ex", deny)
    monkeypatch.setattr(socket.socket, "sendto", deny)
    yield attempts
    # Still fail if application code swallows the blocking exception.
    assert not attempts, "Application attempted outbound networking."


# ---- shared offline ledger fixtures (isolated temporary databases only) ----
import os  # noqa: E402

from ledger_store import CentralLedger, create_local_test_database  # noqa: E402
from zerogpu import ManualQuotaSnapshot  # noqa: E402

KEY = "synthetic-backend-key-not-real-" * 2


def make_snapshot(at):
    return ManualQuotaSnapshot(
        observed_at=at, gpu_seconds_remaining=300, runs_remaining=8,
        overquota_used=0, personal_free_account_confirmed=True,
        paid_usage_disabled_confirmed=True,
    )


@pytest.fixture
def clock():
    return [1_000_000.0]


@pytest.fixture
def ledger_dir(tmp_path):
    directory = tmp_path / "ledger"
    directory.mkdir()
    os.chmod(directory, 0o700)
    return directory


@pytest.fixture
def backend(ledger_dir):
    return create_local_test_database(ledger_dir / "ledger.sqlite3")


@pytest.fixture
def ledger(backend, clock):
    result = CentralLedger(backend, clock=lambda: clock[0])
    result.arm(make_snapshot(clock[0]))
    return result
