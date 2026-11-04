"""Review-phase tests: fake Gradio/ZeroGPU/model, no SDK or model execution."""

import asyncio
from contextlib import nullcontext
import importlib
from pathlib import Path
import runpy
import sqlite3
import sys
from threading import Event
from types import SimpleNamespace

import pytest

from space_transport import PrivateSpaceClient, SPACE_ID
from zerogpu import (
    GenerationUnavailable, ManualQuotaSnapshot, QuotaBudget, ZeroGPUAdapter,
)


@pytest.fixture
def ledger(tmp_path):
    budget = QuotaBudget(tmp_path / ".zerogpu-budget.sqlite3", clock=lambda: 1000)
    budget.arm(ManualQuotaSnapshot(1000, 300, 8, 0, True, True))
    return budget


class FakeJob:
    def __init__(self, result="offline reply", error=None):
        self.value, self.error = result, error

    def result(self, timeout):
        assert timeout == 55
        if self.error:
            raise self.error
        return self.value


@pytest.mark.parametrize("error", [None, TimeoutError("synthetic private input")])
def test_transport_single_submit_and_header_only_credentials(ledger, error, caplog):
    created, calls = [], []

    def factory(**kwargs):
        created.append(kwargs)

        def submit(*args, **options):
            calls.append((args, options))
            return FakeJob(error=error)

        return SimpleNamespace(submit=submit)

    key = "synthetic-backend-key-not-real-" * 2
    transport = PrivateSpaceClient(
        token="synthetic-read-token", backend_key=key,
        execution_approved=True, client_factory=factory,
    )
    adapter = ZeroGPUAdapter(transport, ledger)
    if error:
        with pytest.raises(GenerationUnavailable):
            asyncio.run(adapter.generate("synthetic message"))
        with pytest.raises(GenerationUnavailable):
            asyncio.run(adapter.generate("second message"))
    else:
        assert asyncio.run(adapter.generate("synthetic message")) == "offline reply"
    assert len(created) == len(calls) == 1
    config = created[0]
    assert config["src"] == SPACE_ID
    assert config["token"] == "synthetic-read-token"
    assert config["headers"]["X-MM-Backend-Key"] == key
    assert config["analytics_enabled"] is False
    assert config["ssl_verify"] is True
    assert config["download_files"] is False
    assert calls == [(("synthetic message", 128), {"api_name": "/generate"})]
    assert "synthetic message" not in caplog.text
    assert key not in caplog.text


def test_transport_import_and_construction_do_not_connect():
    def forbidden(**kwargs):
        pytest.fail("Client must not be constructed without a request.")

    PrivateSpaceClient(
        token="synthetic", backend_key="x" * 32,
        execution_approved=True, client_factory=forbidden,
    )
    with pytest.raises(GenerationUnavailable):
        PrivateSpaceClient(token="synthetic", backend_key="x" * 32)


@pytest.mark.parametrize("value", [0, 7, True, 1.5, "6"])
def test_attempt_ceiling_cannot_be_raised_or_invalid(tmp_path, value):
    with pytest.raises(ValueError):
        QuotaBudget(tmp_path / "budget.sqlite3", max_attempts=value)


def test_lower_configured_ceiling_and_dispatch_replay(tmp_path):
    budget = QuotaBudget(tmp_path / "budget.sqlite3", clock=lambda: 1000, max_attempts=2)
    budget.arm(ManualQuotaSnapshot(1000, 300, 8, 0, True, True))
    dispatch = "a" * 32
    with pytest.raises(GenerationUnavailable):
        budget.require_active(dispatch)
    assert budget.reserve(dispatch) == dispatch
    budget.require_active(dispatch)
    budget.finish(dispatch)
    with pytest.raises(GenerationUnavailable):
        budget.reserve(dispatch)
    budget.finish(budget.reserve("b" * 32))
    with pytest.raises(GenerationUnavailable):
        budget.reserve("c" * 32)


@pytest.fixture
def space(monkeypatch, ledger):
    events, decorations = [], []

    class Element:
        def __init__(self, *args, **kwargs):
            pass

        def click(self, **kwargs):
            events.append(kwargs)

    class FakeGradioError(Exception):
        pass

    def decorate(**options):
        decorations.append(options)
        return lambda fn: fn

    monkeypatch.setitem(sys.modules, "spaces", SimpleNamespace(GPU=decorate))
    monkeypatch.setitem(sys.modules, "gradio", SimpleNamespace(
        Blocks=lambda **kwargs: nullcontext(),
        Markdown=Element, Textbox=Element, Number=Element, Button=Element,
        Request=object, Error=FakeGradioError,
    ))
    # Neither SDK nor torch/transformers can be imported or run by this fixture.
    namespace = runpy.run_path(str(
        Path(__file__).resolve().parents[2] / "space_app" / "app.py"
    ), run_name="offline_space")
    key = "synthetic-space-key-not-real-" * 2
    monkeypatch.setenv("ZEROGPU_BACKEND_KEY", key)
    monkeypatch.setenv("SPACE_EXECUTION_APPROVED", "true")
    namespace["authorize"].__globals__["_budget"] = lambda: ledger
    request = SimpleNamespace(headers={
        "x-mm-backend-key": key, "x-mm-dispatch-id": "d" * 32,
    })
    return SimpleNamespace(
        ns=namespace, events=events, decorations=decorations,
        request=request, error=FakeGradioError,
    )


def test_real_handler_registered_without_startup_loading(space):
    assert space.decorations == [{"duration": 30, "size": "large"}]
    assert len(space.events) == 1
    event = space.events[0]
    assert event["fn"] is space.ns["generate"]
    assert event["validator"] is space.ns["authorize"]
    assert event["api_name"] == "generate"
    assert event["concurrency_limit"] == 1
    assert space.ns["_model"] is space.ns["_tokenizer"] is None
    assert "torch" not in sys.modules
    assert "transformers" not in sys.modules


@pytest.mark.parametrize("case", [
    "disabled", "wrong_key", "no_key", "bad_dispatch", "bad_input",
    "too_many_tokens", "fractional_tokens", "nan_tokens", "exhausted", "uncertain",
])
def test_space_cpu_gate_rejects_before_model_or_gpu(space, ledger, monkeypatch, case):
    message, tokens = "synthetic message", 128
    if case == "disabled":
        monkeypatch.delenv("SPACE_EXECUTION_APPROVED")
    elif case == "wrong_key":
        space.request.headers["x-mm-backend-key"] = "wrong"
    elif case == "no_key":
        space.request.headers.clear()
    elif case == "bad_dispatch":
        space.request.headers["x-mm-dispatch-id"] = ""
    elif case == "bad_input":
        message = "x" * 4001
    elif case == "too_many_tokens":
        tokens = 129
    elif case == "fractional_tokens":
        tokens = 1.5
    elif case == "nan_tokens":
        tokens = float("nan")
    elif case == "exhausted":
        for _ in range(6):
            ledger.finish(ledger.reserve())
    elif case == "uncertain":
        ledger.reserve()
    with pytest.raises(space.error) as error:
        space.ns["authorize"](message, tokens, space.request)
    assert "synthetic message" not in str(error.value)
    assert space.ns["_model"] is None


def test_space_success_with_fake_engine_and_no_refund(space, ledger):
    space.ns["authorize"]("synthetic", 128, space.request)
    invoked = []

    def engine(*args):
        invoked.append(args)
        return "offline fake engine reply"

    space.ns["generate"].__globals__["_generate_qwen"] = engine
    assert space.ns["generate"]("synthetic", 128, space.request) == "offline fake engine reply"
    assert invoked == [("synthetic", 128)]
    with sqlite3.connect(ledger.path) as db:
        assert db.execute(
            "SELECT attempts_left, active_job FROM budget"
        ).fetchone() == (5, None)


def test_space_failure_locks_future_requests(space, ledger):
    space.ns["authorize"]("synthetic", 128, space.request)

    def broken(*args):
        raise TimeoutError("synthetic message and credential must not escape")

    space.ns["generate"].__globals__["_generate_qwen"] = broken
    with pytest.raises(space.error) as error:
        space.ns["generate"]("synthetic", 128, space.request)
    assert "credential" not in str(error.value)
    with pytest.raises(space.error):
        space.ns["authorize"]("synthetic", 128, space.request)
    with sqlite3.connect(ledger.path) as db:
        assert db.execute("SELECT attempts_left FROM budget").fetchone() == (5,)


def test_future_entrypoint_stays_disabled_by_default(monkeypatch):
    monkeypatch.delenv("ZEROGPU_EXECUTION_APPROVED", raising=False)
    module = importlib.import_module("approved_main")
    assert module.build_app().title == "Masari Chat API"


@pytest.mark.parametrize("setting", ["missing", "bad_attempts", "bad_key", "bad_database"])
def test_future_entrypoint_bad_configuration_fails_closed(monkeypatch, tmp_path, setting):
    import approved_main

    monkeypatch.setenv("ZEROGPU_EXECUTION_APPROVED", "true")
    monkeypatch.setenv("HF_TOKEN", "synthetic-read-token")
    monkeypatch.setenv("ZEROGPU_BACKEND_KEY", "x" * 32)
    path = tmp_path / "budget.sqlite3"
    QuotaBudget(path)
    monkeypatch.setenv("ZEROGPU_BUDGET_PATH", str(path))
    if setting == "missing":
        monkeypatch.delenv("ZEROGPU_BUDGET_PATH")
    elif setting == "bad_attempts":
        monkeypatch.setenv("ZEROGPU_MAX_ATTEMPTS", "7")
    elif setting == "bad_key":
        monkeypatch.setenv("ZEROGPU_BACKEND_KEY", "short")
    else:
        path.write_bytes(b"invalid database")
    assert approved_main.build_app().title == "Masari Chat API"


def test_offline_end_to_end_shared_six_attempts(
    space, ledger, monkeypatch, tmp_path, caplog, no_outbound_network,
):
    """Actual API + adapter + transport, fake SDK jobs and fake Qwen engine."""
    import json
    from fastapi.testclient import TestClient
    from main import create_app
    from security import hash_password

    backend_budget = QuotaBudget(tmp_path / "backend.sqlite3", clock=lambda: 1000)
    backend_budget.arm(ManualQuotaSnapshot(1000, 300, 8, 0, True, True))
    monkeypatch.setenv("CHAT_AUTH_USERS", json.dumps({
        "first": hash_password("synthetic-password"),
        "second": hash_password("synthetic-password"),
    }))
    monkeypatch.setenv("CHAT_RATE_LIMIT_REQUESTS", "100")
    monkeypatch.setenv("CHAT_RATE_LIMIT_WINDOW_SECONDS", "60")
    calls = []
    key = space.request.headers["x-mm-backend-key"]
    space.ns["generate"].__globals__["_generate_qwen"] = lambda *args: "offline reply"

    def client_factory(**config):
        request = SimpleNamespace(headers={
            name.lower(): value for name, value in config["headers"].items()
        })

        def submit(message, tokens, *, api_name):
            assert api_name == "/generate"
            calls.append(True)
            space.ns["authorize"](message, tokens, request)
            return FakeJob(space.ns["generate"](message, tokens, request))

        return SimpleNamespace(submit=submit)

    generator = ZeroGPUAdapter(PrivateSpaceClient(
        token="synthetic-read-token", backend_key=key,
        execution_approved=True, client_factory=client_factory,
    ), backend_budget)
    client = TestClient(create_app(generator=generator))
    assert client.post("/chat", json={"message": "synthetic"}).status_code == 401
    assert not calls
    for i in range(6):
        response = client.post(
            "/chat", json={"message": "synthetic"},
            auth=(["first", "second"][i % 2], "synthetic-password"),
        )
        assert response.status_code == 200
        assert response.json() == {"reply": "offline reply"}
        assert response.headers["cache-control"] == "no-store"
    response = client.post(
        "/chat", json={"message": "synthetic"},
        auth=("first", "synthetic-password"),
    )
    assert response.status_code == 503
    assert len(calls) == 6
    for budget in (backend_budget, ledger):
        with sqlite3.connect(budget.path) as db:
            assert db.execute(
                "SELECT attempts_left, active_job FROM budget"
            ).fetchone() == (0, None)
        assert key.encode() not in budget.path.read_bytes()
        assert b"synthetic" not in budget.path.read_bytes()
    assert not no_outbound_network
    assert key not in caplog.text


def test_lower_ceiling_on_existing_window_fails_closed(ledger):
    stricter = QuotaBudget(ledger.path, clock=lambda: 1000, max_attempts=2)
    with pytest.raises(GenerationUnavailable):
        stricter.reserve()


def test_cancel_during_metadata_discovery_never_late_submits(ledger):
    started, release = Event(), Event()
    submissions = []

    def factory(**kwargs):
        started.set()
        assert release.wait(3)
        return SimpleNamespace(submit=lambda *a, **k: submissions.append(True))

    adapter = ZeroGPUAdapter(PrivateSpaceClient(
        token="synthetic", backend_key="x" * 32, execution_approved=True,
        client_factory=factory,
    ), ledger)

    async def scenario():
        task = asyncio.create_task(adapter.generate("synthetic"))
        try:
            for _ in range(500):
                if started.is_set():
                    break
                await asyncio.sleep(0.001)
            assert started.is_set()
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        finally:
            release.set()

    asyncio.run(scenario())
    assert submissions == []
    with pytest.raises(GenerationUnavailable):
        ledger.reserve()
