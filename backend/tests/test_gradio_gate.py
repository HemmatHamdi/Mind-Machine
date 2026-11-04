"""Actual Gradio routes, fake GPU wrapper and fake engine. No live networking."""

from functools import wraps
from pathlib import Path
import runpy
import sys
from types import SimpleNamespace

from fastapi.testclient import TestClient
import pytest

from zerogpu import ManualQuotaSnapshot, QuotaBudget


@pytest.fixture
def gradio_app(monkeypatch, tmp_path):
    monkeypatch.setenv("GRADIO_ANALYTICS_ENABLED", "False")
    monkeypatch.setenv("HF_HUB_OFFLINE", "1")
    # Importing the actual GPU SDK, torch or transformers is NEVER required.
    gpu_calls = []

    def decorator(**options):
        assert options == {"duration": 30, "size": "large"}

        def wrap(fn):
            @wraps(fn)
            def fake_gpu(*args, **kwargs):
                gpu_calls.append(True)
                return fn(*args, **kwargs)
            fake_gpu.zerogpu = None
            return fake_gpu
        return wrap

    monkeypatch.setitem(sys.modules, "spaces", SimpleNamespace(GPU=decorator))
    namespace = runpy.run_path(str(
        Path(__file__).resolve().parents[2] / "space_app" / "app.py"
    ), run_name="offline_gradio")
    ledger = QuotaBudget(tmp_path / "space.sqlite3", clock=lambda: 1000)
    ledger.arm(ManualQuotaSnapshot(1000, 300, 8, 0, True, True))
    namespace["authorize"].__globals__["_budget"] = lambda: ledger
    namespace["authorize"].__globals__["_generate_qwen"] = lambda *args: "offline SDK reply"
    key = "synthetic-backend-key-not-real-" * 2
    monkeypatch.setenv("ZEROGPU_BACKEND_KEY", key)
    monkeypatch.setenv("SPACE_EXECUTION_APPROVED", "true")
    demo = namespace["demo"]
    demo.queue(api_open=False, default_concurrency_limit=1, max_size=1)
    return SimpleNamespace(
        demo=demo, gpu_calls=gpu_calls, key=key, ledger=ledger,
        headers={"X-MM-Backend-Key": key, "X-MM-Dispatch-ID": "e" * 32},
    )


@pytest.mark.parametrize("denial", ["disabled", "wrong_key", "exhausted"])
def test_actual_queue_validator_precedes_fake_gpu(gradio_app, monkeypatch, denial):
    app = gradio_app
    if denial == "disabled":
        monkeypatch.delenv("SPACE_EXECUTION_APPROVED")
    elif denial == "wrong_key":
        app.headers["X-MM-Backend-Key"] = "incorrect"
    else:
        for _ in range(6):
            app.ledger.finish(app.ledger.reserve())
    with TestClient(app.demo.app) as client:
        submission = client.post(
            "/gradio_api/call/generate", json={"data": ["synthetic", 128]},
            headers=app.headers,
        )
        # Gradio rejects the CPU validator before even returning a queue event.
        assert submission.status_code == 400
        assert "event_id" not in submission.json()
    assert app.gpu_calls == []
    assert "torch" not in sys.modules
    assert "transformers" not in sys.modules


def test_direct_prediction_cannot_bypass_queue_guard(gradio_app):
    app = gradio_app
    with TestClient(app.demo.app) as client:
        response = client.post(
            "/gradio_api/run/generate", json={"data": ["synthetic", 128]},
            headers=app.headers,
        )
        assert response.status_code in (401, 403, 404)
    assert app.gpu_calls == []


def test_actual_gradio_queue_fake_success(gradio_app):
    app = gradio_app
    with TestClient(app.demo.app) as client:
        # Match launch's CPU-only queue startup without starting an HTTP server.
        client.portal.call(app.demo.run_startup_events)
        submission = client.post(
            "/gradio_api/call/generate", json={"data": ["synthetic", 128]},
            headers=app.headers,
        )
        assert submission.status_code == 200
        event_id = submission.json()["event_id"]
        response = client.get("/gradio_api/call/generate/" + event_id)
        assert "event: complete" in response.text
        assert "offline SDK reply" in response.text
    assert app.gpu_calls == [True]
