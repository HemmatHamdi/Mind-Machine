"""Actual Gradio routes with a fake GPU wrapper and fake engine. No live networking.

The real Gradio queue/validator is exercised; ZeroGPU itself, model code and the
backend control endpoint are fakes, so platform behaviour remains unverified.
"""

from functools import wraps
from pathlib import Path
import runpy
import sys
import time
from types import SimpleNamespace

from fastapi.testclient import TestClient
import pytest

from conftest import KEY, make_snapshot
from dispatch_auth import sign_dispatch
from ledger_store import CentralLedger

MESSAGE = "synthetic"


@pytest.fixture
def gradio_app(monkeypatch, backend):
    monkeypatch.setenv("GRADIO_ANALYTICS_ENABLED", "False")
    monkeypatch.setenv("HF_HUB_OFFLINE", "1")
    for name in ("SPACE_MODEL_INIT_APPROVED", "SPACE_EXECUTION_APPROVED"):
        monkeypatch.delenv(name, raising=False)
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

    # Neither the GPU SDK, torch nor transformers is ever imported here.
    monkeypatch.setitem(sys.modules, "spaces", SimpleNamespace(GPU=decorator))
    namespace = runpy.run_path(str(
        Path(__file__).resolve().parents[2] / "space_app" / "app.py"
    ), run_name="offline_gradio")
    ledger = CentralLedger(backend, clock=time.time)
    ledger.arm(make_snapshot(time.time()))
    g = namespace["authorize"].__globals__
    g["_claim"] = lambda url, key, dispatch_id, tag: ledger.claim(dispatch_id, tag)
    g["_generate_qwen"] = lambda *args: "offline SDK reply"
    monkeypatch.setenv("ZEROGPU_BACKEND_KEY", KEY)
    monkeypatch.setenv("ZEROGPU_CONTROL_URL", "https://backend.invalid/claim")
    monkeypatch.setenv("SPACE_EXECUTION_APPROVED", "true")
    demo = namespace["demo"]
    demo.queue(api_open=False, default_concurrency_limit=1, max_size=1)

    def headers(n=1, key=KEY, reserve=True):
        dispatch_id, issued = f"{n:032x}", int(time.time())
        tag = sign_dispatch(key, dispatch_id, issued, 128, MESSAGE)
        if reserve:
            ledger.reserve(dispatch_id, tag)
        return {"X-MM-Dispatch-ID": dispatch_id, "X-MM-Dispatch-Time": str(issued),
                "X-MM-Dispatch-Tag": tag}

    return SimpleNamespace(demo=demo, gpu_calls=gpu_calls, ledger=ledger, headers=headers)


def submit(app, headers):
    with TestClient(app.demo.app) as client:
        return client.post("/gradio_api/call/generate",
                           json={"data": [MESSAGE, 128]}, headers=headers)


@pytest.mark.parametrize("denial", [
    "disabled", "wrong_key", "unreserved", "replay", "missing_headers",
])
def test_actual_queue_validator_precedes_fake_gpu(gradio_app, monkeypatch, denial):
    app = gradio_app
    if denial == "disabled":
        headers = app.headers()
        monkeypatch.delenv("SPACE_EXECUTION_APPROVED")
    elif denial == "wrong_key":
        headers = app.headers(key="w" * 32)
    elif denial == "unreserved":
        headers = app.headers(reserve=False)
    elif denial == "missing_headers":
        headers = {}
    else:
        headers = app.headers()
        app.ledger.claim(headers["X-MM-Dispatch-ID"], headers["X-MM-Dispatch-Tag"])
    response = submit(app, headers)
    # Gradio rejects at the CPU validator before even returning a queue event.
    assert response.status_code == 400
    assert "event_id" not in response.json()
    assert app.gpu_calls == []
    assert "torch" not in sys.modules and "transformers" not in sys.modules


def test_direct_prediction_cannot_bypass_queue_guard(gradio_app):
    app = gradio_app
    with TestClient(app.demo.app) as client:
        response = client.post("/gradio_api/run/generate",
                               json={"data": [MESSAGE, 128]}, headers=app.headers())
        assert response.status_code in (401, 403, 404)
    assert app.gpu_calls == []


def test_actual_gradio_queue_fake_success_and_claim_is_single_use(gradio_app):
    app = gradio_app
    headers = app.headers()
    with TestClient(app.demo.app) as client:
        client.portal.call(app.demo.run_startup_events)
        first = client.post("/gradio_api/call/generate",
                            json={"data": [MESSAGE, 128]}, headers=headers)
        assert first.status_code == 200
        response = client.get("/gradio_api/call/generate/" + first.json()["event_id"])
        assert "event: complete" in response.text and "offline SDK reply" in response.text
        replay = client.post("/gradio_api/call/generate",
                             json={"data": [MESSAGE, 128]}, headers=headers)
        assert replay.status_code == 400
    assert app.gpu_calls == [True]
