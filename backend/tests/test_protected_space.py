"""Transport, signed dispatch, Space app and entrypoint tests.

Everything is fake: no Gradio server, SDK, torch, transformers, model, GPU or Hugging
Face endpoint. Passing here does NOT verify ZeroGPU, Space networking or live latency.
"""

import asyncio
from contextlib import nullcontext
import importlib
import json
from pathlib import Path
import runpy
import sqlite3
import sys
import time
from threading import Event
from types import SimpleNamespace

import pytest

from dispatch_auth import Dispatch, sign_dispatch, valid_dispatch_id, verify_dispatch
from space_transport import PrivateSpaceClient, SPACE_ID
from zerogpu import (
    GenerationUnavailable, ManualQuotaSnapshot, QuotaBudget, ZeroGPUAdapter,
)

KEY = "synthetic-backend-key-not-real-" * 2
SPACE_APP = Path(__file__).resolve().parents[2] / "space_app" / "app.py"


@pytest.fixture
def clock():
    return [1_000_000.0]


@pytest.fixture
def ledger(tmp_path, clock):
    budget = QuotaBudget(tmp_path / ".zerogpu-budget.sqlite3", clock=lambda: clock[0])
    budget.arm(ManualQuotaSnapshot(clock[0], 300, 8, 0, True, True))
    return budget


@pytest.fixture(autouse=True)
def wall_clock(monkeypatch, clock):
    # The Space checks ticket age against wall time; align it with the test clock.
    monkeypatch.setattr(time, "time", lambda: clock[0])


def headers_for(message="synthetic message", n=1, tokens=128, key=KEY, at=None):
    dispatch_id, issued = f"{n:032x}", int(at if at is not None else time.time())
    return SimpleNamespace(headers={
        "x-mm-dispatch-id": dispatch_id, "x-mm-dispatch-time": str(issued),
        "x-mm-dispatch-tag": sign_dispatch(key, dispatch_id, issued, tokens, message)})


# ---------------- signed dispatch ----------------

def test_dispatch_tag_binds_every_field_and_expires():
    d = "a" * 32
    tag = sign_dispatch(KEY, d, 1000, 128, "hello")
    assert verify_dispatch(KEY, d, 1000, 128, "hello", tag, 1000)
    assert verify_dispatch(KEY, d, 1000, 128, "hello", tag, 1090)
    for args in (("b" * 32, 1000, 128, "hello"), (d, 1001, 128, "hello"),
                 (d, 1000, 127, "hello"), (d, 1000, 128, "hellO")):
        assert not verify_dispatch(KEY, *args, tag, 1000)
    assert not verify_dispatch(KEY, d, 1000, 128, "hello", tag, 1091)   # expired
    assert not verify_dispatch(KEY, d, 1000, 128, "hello", tag, 990)    # future
    assert not verify_dispatch("z" * 32, d, 1000, 128, "hello", tag, 1000)
    assert not verify_dispatch(KEY, d, 1000, 128, "hello", "x", 1000)
    assert not verify_dispatch("short", d, 1000, 128, "hello", tag, 1000)
    assert not valid_dispatch_id("A" * 32)


# ---------------- transport ----------------

class FakeJob:
    def __init__(self, result="offline reply", error=None):
        self.value, self.error = result, error

    def result(self, timeout):
        assert timeout == 55
        if self.error:
            raise self.error
        return self.value


@pytest.mark.parametrize("error", [None, TimeoutError("synthetic private input")])
def test_transport_single_submit_signed_headers_and_no_root_key(ledger, error, caplog):
    created, calls = [], []

    def factory(**kwargs):
        created.append(kwargs)

        def submit(*args, **options):
            calls.append((args, options))
            return FakeJob(error=error)

        return SimpleNamespace(submit=submit)

    transport = PrivateSpaceClient(
        token="synthetic-read-token", execution_approved=True, client_factory=factory)
    adapter = ZeroGPUAdapter(transport, ledger, dispatch_key=KEY)
    if error:
        with pytest.raises(GenerationUnavailable):
            asyncio.run(adapter.generate("synthetic message"))
        with pytest.raises(GenerationUnavailable):
            asyncio.run(adapter.generate("second message"))
    else:
        assert asyncio.run(adapter.generate("synthetic message")) == "offline reply"
    assert len(created) == len(calls) == 1
    config = created[0]
    assert config["src"] == SPACE_ID and config["token"] == "synthetic-read-token"
    headers = config["headers"]
    assert set(headers) == {"X-MM-Dispatch-ID", "X-MM-Dispatch-Time", "X-MM-Dispatch-Tag"}
    assert KEY not in json.dumps(headers)
    assert verify_dispatch(
        KEY, headers["X-MM-Dispatch-ID"], int(headers["X-MM-Dispatch-Time"]), 128,
        "synthetic message", headers["X-MM-Dispatch-Tag"], time.time())
    assert config["analytics_enabled"] is False and config["ssl_verify"] is True
    assert config["download_files"] is False
    assert calls == [(("synthetic message", 128), {"api_name": "/generate"})]
    assert "synthetic message" not in caplog.text and KEY not in caplog.text


def test_transport_import_and_construction_do_not_connect():
    def forbidden(**kwargs):
        pytest.fail("Client must not be constructed without a request.")

    PrivateSpaceClient(token="synthetic", execution_approved=True, client_factory=forbidden)
    with pytest.raises(GenerationUnavailable):
        PrivateSpaceClient(token="synthetic")
    with pytest.raises(GenerationUnavailable):
        PrivateSpaceClient(token="", execution_approved=True)


@pytest.mark.parametrize("value", [0, 7, True, 1.5, "6"])
def test_attempt_ceiling_cannot_be_raised_or_invalid(tmp_path, value):
    with pytest.raises(ValueError):
        QuotaBudget(tmp_path / "budget.sqlite3", max_attempts=value)


def test_lower_ceiling_and_reservation_replay(tmp_path, clock):
    budget = QuotaBudget(tmp_path / "b.sqlite3", clock=lambda: clock[0], max_attempts=2)
    budget.arm(ManualQuotaSnapshot(clock[0], 300, 8, 0, True, True))
    dispatch = "a" * 32
    assert budget.reserve(dispatch) == dispatch
    budget.finish(dispatch)
    with pytest.raises(GenerationUnavailable):
        budget.reserve(dispatch)
    budget.finish(budget.reserve("b" * 32))
    with pytest.raises(GenerationUnavailable):
        budget.reserve("c" * 32)


def test_cancel_during_metadata_discovery_never_late_submits(ledger):
    started, release = Event(), Event()
    submissions = []

    def factory(**kwargs):
        started.set()
        assert release.wait(3)
        return SimpleNamespace(submit=lambda *a, **k: submissions.append(True))

    adapter = ZeroGPUAdapter(PrivateSpaceClient(
        token="synthetic", execution_approved=True, client_factory=factory),
        ledger, dispatch_key=KEY)

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


# ---------------- Space app (fake gradio/spaces/torch/transformers) ----------------

class FakeStack:
    """Records loads; any generation during startup would be visible."""

    def __init__(self, fail=False):
        self.loads, self.moves, self.generations, self.fail = [], [], [], fail
        outer = self

        class Row:
            def __getitem__(self, item):
                return "tokens"

        class Outputs:
            def __getitem__(self, item):
                return Row()

        class Ids:
            shape = (1, 3)

        class Batch(dict):
            def to(self, device):
                return self

        class Model:
            def to(self, device):
                outer.moves.append(device)
                return self

            def eval(self):
                return self

            def generate(self, **kwargs):
                outer.generations.append(kwargs)
                return Outputs()

        class Tokenizer:
            eos_token_id = 0

            def apply_chat_template(self, *args, **kwargs):
                return "prompt"

            def __call__(self, text, **kwargs):
                return Batch(input_ids=Ids())

            def decode(self, tokens, **kwargs):
                return " offline fake reply "

        def loader(kind, cls):
            def from_pretrained(model_id, **kwargs):
                outer.loads.append((kind, model_id, kwargs))
                if outer.fail:
                    raise OSError("synthetic secret load failure")
                return cls()
            return from_pretrained

        self.transformers = SimpleNamespace(
            AutoModelForCausalLM=SimpleNamespace(from_pretrained=loader("model", Model)),
            AutoTokenizer=SimpleNamespace(from_pretrained=loader("tokenizer", Tokenizer)))
        self.torch = SimpleNamespace(float16="float16", inference_mode=lambda: nullcontext())


@pytest.fixture
def load_space(monkeypatch):
    class FakeGradioError(Exception):
        pass

    events, decorations = [], []

    class Element:
        def __init__(self, *args, **kwargs):
            pass

        def click(self, **kwargs):
            events.append(kwargs)

    def decorate(**options):
        decorations.append(options)
        return lambda fn: fn

    def factory(*, init=False, execute=True, fail=False):
        fake = FakeStack(fail=fail)
        monkeypatch.setitem(sys.modules, "spaces", SimpleNamespace(GPU=decorate))
        monkeypatch.setitem(sys.modules, "gradio", SimpleNamespace(
            Blocks=lambda **kwargs: nullcontext(), Markdown=Element, Textbox=Element,
            Number=Element, Button=Element, Request=object, Error=FakeGradioError))
        monkeypatch.setitem(sys.modules, "torch", fake.torch)
        monkeypatch.setitem(sys.modules, "transformers", fake.transformers)
        monkeypatch.setenv("ZEROGPU_BACKEND_KEY", KEY)
        for name, on in (("SPACE_MODEL_INIT_APPROVED", init), ("SPACE_EXECUTION_APPROVED", execute)):
            if on:
                monkeypatch.setenv(name, "true")
            else:
                monkeypatch.delenv(name, raising=False)
        namespace = runpy.run_path(str(SPACE_APP), run_name="offline_space")
        return SimpleNamespace(ns=namespace, events=events, decorations=decorations,
                               fake=fake, error=FakeGradioError)

    return factory


def test_default_startup_loads_nothing_and_registers_real_handler(load_space):
    space = load_space(init=False, execute=False)
    assert space.decorations == [{"duration": 30, "size": "large"}]
    event = space.events[0]
    assert event["fn"] is space.ns["generate"] and event["validator"] is space.ns["authorize"]
    assert event["api_name"] == "generate" and event["concurrency_limit"] == 1
    assert space.ns["_model"] is space.ns["_tokenizer"] is None
    assert space.fake.loads == [] and space.fake.moves == [] and space.fake.generations == []


def test_init_flag_loads_once_at_startup_and_handler_only_infers(load_space):
    space = load_space(init=True, execute=True)
    assert sorted(kind for kind, *_ in space.fake.loads) == ["model", "tokenizer"]
    for _, model_id, kwargs in space.fake.loads:
        assert model_id == "Qwen/Qwen2.5-1.5B-Instruct"
        assert kwargs["revision"] == "989aa7980e4cf806f80c7fef2b1adb7bc71aa306"
        assert kwargs["trust_remote_code"] is False and kwargs["token"] is False
    assert space.fake.moves == ["cuda"] and space.fake.generations == []  # no warm-up
    request = headers_for("synthetic message")
    assert space.ns["authorize"]("synthetic message", 128, request) == ("synthetic message", 128)
    assert space.ns["generate"]("synthetic message", 128, request) == "offline fake reply"
    assert len(space.fake.loads) == 2          # the handler never loads a model
    assert len(space.fake.generations) == 1
    assert space.fake.generations[0]["max_new_tokens"] == 128
    assert space.fake.generations[0]["do_sample"] is False


def test_failed_startup_load_fails_closed_without_retry_or_error_text(load_space):
    space = load_space(init=True, execute=True, fail=True)
    assert space.ns["_model"] is None
    request = headers_for()
    space.ns["authorize"]("synthetic message", 128, request)
    with pytest.raises(space.error) as caught:
        space.ns["generate"]("synthetic message", 128, request)
    assert "secret" not in str(caught.value)
    assert len(space.fake.loads) == 1


def test_inference_and_init_flags_are_independent(load_space):
    space = load_space(init=True, execute=False)      # loaded, but inference refused
    request = headers_for()
    with pytest.raises(space.error):
        space.ns["authorize"]("synthetic message", 128, request)
    with pytest.raises(space.error):
        space.ns["generate"]("synthetic message", 128, request)
    assert space.fake.generations == []
    space = load_space(init=False, execute=True)      # admitted, but no lazy load
    with pytest.raises(space.error):
        space.ns["generate"]("synthetic message", 128, request)
    assert space.fake.loads == [] and space.fake.generations == []


@pytest.mark.parametrize("case", [
    "wrong_key", "no_headers", "tampered_message", "expired", "bad_tokens",
    "too_many_tokens", "fractional_tokens", "nan_tokens", "oversized", "bad_time",
])
def test_space_gate_rejects_before_model_or_gpu(load_space, clock, monkeypatch, case):
    space = load_space(init=True, execute=True)
    message, tokens = "synthetic message", 128
    request = headers_for(message)
    if case == "wrong_key":
        monkeypatch.setenv("ZEROGPU_BACKEND_KEY", "w" * 32)
    elif case == "no_headers":
        request.headers.clear()
    elif case == "tampered_message":
        message = "synthetic messagE"
    elif case == "expired":
        clock[0] += 91
    elif case == "bad_tokens":
        tokens = 0
    elif case == "too_many_tokens":
        tokens = 129
    elif case == "fractional_tokens":
        tokens = 1.5
    elif case == "nan_tokens":
        tokens = float("nan")
    elif case == "oversized":
        message = "x" * 4001
    elif case == "bad_time":
        request.headers["x-mm-dispatch-time"] = "not-a-number"
    with pytest.raises(space.error) as caught:
        space.ns["authorize"](message, tokens, request)
    assert "synthetic message" not in str(caught.value)
    assert space.fake.generations == []


def test_handler_independently_rejects_unsigned_requests(load_space):
    space = load_space(init=True, execute=True)
    with pytest.raises(space.error):
        space.ns["generate"]("synthetic message", 128, SimpleNamespace(headers={}))
    assert space.fake.generations == []


def test_space_failure_is_generic_and_has_no_quota_or_database_code(load_space):
    space = load_space(init=True, execute=True)
    request = headers_for()

    def broken(*args):
        raise TimeoutError("synthetic message and credential must not escape")

    space.ns["generate"].__globals__["_generate_qwen"] = broken
    with pytest.raises(space.error) as caught:
        space.ns["generate"]("synthetic message", 128, request)
    assert "credential" not in str(caught.value)
    source = SPACE_APP.read_text()
    for forbidden in ("sqlite3", "QuotaBudget", "SPACE_BUDGET_PATH", "zerogpu"):
        assert forbidden not in source


# ---------------- entrypoint ----------------

def test_future_entrypoint_stays_disabled_by_default(monkeypatch):
    monkeypatch.delenv("ZEROGPU_EXECUTION_APPROVED", raising=False)
    module = importlib.import_module("approved_main")
    assert module.build_app().title == "Masari Chat API"


@pytest.mark.parametrize("setting", ["missing", "bad_attempts", "bad_database"])
def test_future_entrypoint_bad_configuration_fails_closed(monkeypatch, tmp_path, setting):
    import approved_main

    monkeypatch.setenv("ZEROGPU_EXECUTION_APPROVED", "true")
    monkeypatch.setenv("HF_TOKEN", "synthetic-read-token")
    monkeypatch.setenv("ZEROGPU_BACKEND_KEY", KEY)
    path = tmp_path / "budget.sqlite3"
    QuotaBudget(path)
    monkeypatch.setenv("ZEROGPU_BUDGET_PATH", str(path))
    if setting == "missing":
        monkeypatch.delenv("ZEROGPU_BUDGET_PATH")
    elif setting == "bad_attempts":
        monkeypatch.setenv("ZEROGPU_MAX_ATTEMPTS", "7")
    else:
        path.write_bytes(b"invalid database")
    assert approved_main.build_app().title == "Masari Chat API"


def test_offline_end_to_end_six_attempts_signed_dispatch(
    load_space, ledger, monkeypatch, caplog, no_outbound_network,
):
    """Real API + adapter + transport + Space validator/handler; fake SDK and model."""
    from fastapi.testclient import TestClient
    from main import create_app
    from security import hash_password

    space = load_space(init=True, execute=True)
    monkeypatch.setenv("CHAT_AUTH_USERS", json.dumps({
        "first": hash_password("synthetic-password"),
        "second": hash_password("synthetic-password")}))
    monkeypatch.setenv("CHAT_RATE_LIMIT_REQUESTS", "100")
    monkeypatch.setenv("CHAT_RATE_LIMIT_WINDOW_SECONDS", "60")
    calls = []

    def client_factory(**config):
        request = SimpleNamespace(headers={k.lower(): v for k, v in config["headers"].items()})

        def submit(message, tokens, *, api_name):
            calls.append(api_name)
            space.ns["authorize"](message, tokens, request)
            return FakeJob(space.ns["generate"](message, tokens, request))

        return SimpleNamespace(submit=submit)

    generator = ZeroGPUAdapter(PrivateSpaceClient(
        token="synthetic-read-token", execution_approved=True,
        client_factory=client_factory), ledger, dispatch_key=KEY)
    client = TestClient(create_app(generator=generator))
    assert client.post("/chat", json={"message": "synthetic"}).status_code == 401 and not calls
    for i in range(6):
        response = client.post("/chat", json={"message": "synthetic"},
                               auth=(["first", "second"][i % 2], "synthetic-password"))
        assert response.status_code == 200 and response.json() == {"reply": "offline fake reply"}
        assert response.headers["cache-control"] == "no-store"
    assert client.post("/chat", json={"message": "synthetic"},
                       auth=("first", "synthetic-password")).status_code == 503
    assert len(calls) == 6 and len(space.fake.generations) == 6
    assert len(space.fake.loads) == 2             # model loaded once, at startup
    with sqlite3.connect(ledger.path) as db:
        assert db.execute("SELECT attempts_left, active_job FROM budget").fetchone() == (0, None)
    raw = ledger.path.read_bytes()
    assert KEY.encode() not in raw and b"synthetic" not in raw
    assert not no_outbound_network and KEY not in caplog.text
