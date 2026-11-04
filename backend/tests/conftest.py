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
