"""Actual Gradio routes with a fake GPU wrapper and fake engine. No live networking.

The real Gradio queue/validator runs; ZeroGPU and the model are fakes, so platform
behaviour remains unverified.
"""

from functools import wraps
from pathlib import Path
import runpy
import sys
import time
from types import SimpleNamespace

from fastapi.testclient import TestClient
import pytest

from dispatch_auth import sign_dispatch

KEY = "synthetic-backend-key-not-real-" * 2
MESSAGE = "synthetic"


@pytest.fixture
def gradio_app(monkeypatch):
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

    # The GPU SDK, torch and transformers are never imported here.
    monkeypatch.setitem(sys.modules, "spaces", SimpleNamespace(GPU=decorator))
    namespace = runpy.run_path(str(
        Path(__file__).resolve().parents[2] / "space_app" / "app.py"
    ), run_name="offline_gradio")
    namespace["authorize"].__globals__["_generate_qwen"] = lambda *args: "offline SDK reply"
    monkeypatch.setenv("ZEROGPU_BACKEND_KEY", KEY)
    monkeypatch.setenv("SPACE_EXECUTION_APPROVED", "true")
    demo = namespace["demo"]
    demo.queue(api_open=False, default_concurrency_limit=1, max_size=1)

    def headers(key=KEY, message=MESSAGE, issued=None):
        issued = int(time.time()) if issued is None else issued
        return {"X-MM-Dispatch-ID": "e" * 32, "X-MM-Dispatch-Time": str(issued),
                "X-MM-Dispatch-Tag": sign_dispatch(key, "e" * 32, issued, 128, message)}

    return SimpleNamespace(demo=demo, gpu_calls=gpu_calls, headers=headers)


@pytest.mark.parametrize("denial", [
    "disabled", "wrong_key", "other_message", "expired", "missing_headers",
])
def test_actual_queue_validator_precedes_fake_gpu(gradio_app, monkeypatch, denial):
    app = gradio_app
    headers = app.headers()
    if denial == "disabled":
        monkeypatch.delenv("SPACE_EXECUTION_APPROVED")
    elif denial == "wrong_key":
        headers = app.headers(key="w" * 32)
    elif denial == "other_message":
        headers = app.headers(message="different")
    elif denial == "expired":
        headers = app.headers(issued=int(time.time()) - 120)
    else:
        headers = {}
    with TestClient(app.demo.app) as client:
        response = client.post("/gradio_api/call/generate",
                               json={"data": [MESSAGE, 128]}, headers=headers)
    # Gradio rejects at the CPU validator before even returning a queue event.
    assert response.status_code == 400 and "event_id" not in response.json()
    assert app.gpu_calls == []
    assert "torch" not in sys.modules and "transformers" not in sys.modules


def test_direct_prediction_cannot_bypass_queue_guard(gradio_app):
    app = gradio_app
    with TestClient(app.demo.app) as client:
        response = client.post("/gradio_api/run/generate",
                               json={"data": [MESSAGE, 128]}, headers=app.headers())
        assert response.status_code in (401, 403, 404)
    assert app.gpu_calls == []


def test_actual_gradio_queue_fake_success(gradio_app):
    app = gradio_app
    with TestClient(app.demo.app) as client:
        client.portal.call(app.demo.run_startup_events)
        submission = client.post("/gradio_api/call/generate",
                                 json={"data": [MESSAGE, 128]}, headers=app.headers())
        assert submission.status_code == 200
        response = client.get("/gradio_api/call/generate/" + submission.json()["event_id"])
        assert "event: complete" in response.text and "offline SDK reply" in response.text
    assert app.gpu_calls == [True]
