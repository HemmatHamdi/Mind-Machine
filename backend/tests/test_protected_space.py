"""Transport, control endpoint, Space app and entrypoint tests.

Everything is fake: no Gradio server, SDK, torch, transformers, model, GPU, Turso or
Hugging Face endpoint. Passing here does NOT verify platform behaviour (ZeroGPU,
Gradio queueing under load, remote libSQL transactions, HTTPS ingress).
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

from fastapi.testclient import TestClient
import pytest

from conftest import KEY
from control import CLAIM_PATH, build_control_router
from dispatch_auth import (
    AdmissionError, Dispatch, PROOF_HEADER, claim_admission, claim_proof,
    sign_dispatch, valid_dispatch_id, verify_claim_proof, verify_dispatch,
)
from ledger_store import CentralLedger
from main import create_app
from space_transport import PrivateSpaceClient, SPACE_ID
from zerogpu import GenerationUnavailable, ZeroGPUAdapter

SPACE_APP = Path(__file__).resolve().parents[2] / "space_app" / "app.py"
CONTROL_URL = "https://backend.invalid" + CLAIM_PATH


def dispatch_for(ledger, n, message="synthetic message", tokens=128):
    dispatch_id = f"{n:032x}"
    issued = int(ledger.clock())
    return Dispatch(dispatch_id, issued, sign_dispatch(KEY, dispatch_id, issued, tokens, message))


# ---------------- dispatch authentication primitives ----------------

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


def test_claim_proof_is_purpose_bound_and_not_the_dispatch_tag():
    d, tag = "a" * 32, sign_dispatch(KEY, "a" * 32, 1000, 128, "hello")
    proof = claim_proof(KEY, d, tag)
    assert proof != tag and verify_claim_proof(KEY, d, tag, proof)
    assert not verify_claim_proof(KEY, d, tag, tag)
    assert not verify_claim_proof(KEY, "b" * 32, tag, proof)
    assert not verify_claim_proof("z" * 32, d, tag, proof)
    assert not valid_dispatch_id("A" * 32)


def test_space_claim_client_requires_https_sends_no_key_and_never_retries():
    calls = []

    def post(url, headers, body, timeout):
        calls.append((url, headers, body))
        return 200

    d, tag = "a" * 32, "b" * 64
    claim_admission(CONTROL_URL, KEY, d, tag, post=post)
    assert len(calls) == 1
    _, headers, body = calls[0]
    assert headers[PROOF_HEADER] == claim_proof(KEY, d, tag)
    assert KEY not in json.dumps(headers) + body.decode()
    for url in ("http://backend.invalid/x", "", None):
        with pytest.raises(AdmissionError):
            claim_admission(url, KEY, d, tag, post=post)
    for failing in (lambda *a: 403, lambda *a: 500, lambda *a: (_ for _ in ()).throw(OSError(KEY))):
        with pytest.raises(AdmissionError) as caught:
            claim_admission(CONTROL_URL, KEY, d, tag, post=failing)
        assert KEY not in repr(caught.value)
    assert len(calls) == 1


# ---------------- control endpoint ----------------

@pytest.fixture
def control(ledger):
    app = create_app(extra_routers=(build_control_router(ledger, KEY),))
    return SimpleNamespace(client=TestClient(app), ledger=ledger)


def post_claim(control, d, proof=None, **body):
    payload = {"dispatch_id": d.id, "tag": d.tag, **body}
    headers = {PROOF_HEADER: proof if proof is not None else claim_proof(KEY, d.id, d.tag)}
    return control.client.post(CLAIM_PATH, json=payload, headers=headers)


def test_control_admits_once_with_valid_proof(control):
    d = dispatch_for(control.ledger, 1)
    control.ledger.reserve(d.id, d.tag)
    response = post_claim(control, d)
    assert response.status_code == 200 and response.json() == {"admitted": True}
    assert response.headers["cache-control"] == "no-store"
    assert post_claim(control, d).status_code == 403  # replay


@pytest.mark.parametrize("case", ["no_proof", "bad_proof", "unreserved", "wrong_tag", "unarmed_storage"])
def test_control_denials_are_uniform_and_content_free(control, case, monkeypatch):
    d = dispatch_for(control.ledger, 1)
    if case != "unreserved":
        control.ledger.reserve(d.id, d.tag)
    if case == "no_proof":
        response = control.client.post(CLAIM_PATH, json={"dispatch_id": d.id, "tag": d.tag})
    elif case == "bad_proof":
        response = post_claim(control, d, proof="0" * 64)
    elif case == "wrong_tag":
        other = "c" * 64
        response = post_claim(control, SimpleNamespace(id=d.id, tag=other),
                              proof=claim_proof(KEY, d.id, other))
    elif case == "unarmed_storage":
        monkeypatch.setattr(control.ledger.backend, "batch",
                            lambda s: (_ for _ in ()).throw(RuntimeError("secret")))
        response = post_claim(control, d)
    else:
        response = post_claim(control, d)
    assert response.status_code == 403
    assert response.json() == {"detail": "Not admitted."}
    assert "secret" not in response.text


def test_control_rejects_malformed_and_extra_fields(control):
    d = dispatch_for(control.ledger, 1)
    control.ledger.reserve(d.id, d.tag)
    assert post_claim(control, d, message="leak attempt").status_code == 422
    bad = control.client.post(CLAIM_PATH, json={"dispatch_id": "x", "tag": "y"},
                              headers={PROOF_HEADER: "0" * 64})
    assert bad.status_code == 422 and "leak" not in bad.text
    assert control.client.get(CLAIM_PATH).status_code == 405


def test_control_route_absent_from_default_app_and_docs():
    client = TestClient(create_app())
    assert client.post(CLAIM_PATH, json={}).status_code == 404
    assert CLAIM_PATH not in client.get("/openapi.json").text


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
def test_transport_single_submit_header_credentials_and_no_root_key(ledger, error, caplog):
    created, calls = [], []

    def factory(**kwargs):
        created.append(kwargs)

        def submit(*args, **options):
            calls.append((args, options))
            ledger.claim(kwargs["headers"]["X-MM-Dispatch-ID"], kwargs["headers"]["X-MM-Dispatch-Tag"])
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
        ledger.reserve("a" * 32, "b" * 64)


# ---------------- Space app (fake gradio/spaces/torch/transformers) ----------------

class FakeTransformers:
    """Records loads. Fails the test if anything generates during startup."""

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

        def load(kind, cls):
            def from_pretrained(model_id, **kwargs):
                outer.loads.append((kind, model_id, kwargs))
                if outer.fail:
                    raise OSError("synthetic secret load failure")
                return cls()
            return from_pretrained

        self.module = SimpleNamespace(
            AutoModelForCausalLM=SimpleNamespace(from_pretrained=load("model", Model)),
            AutoTokenizer=SimpleNamespace(from_pretrained=load("tokenizer", Tokenizer)),
        )
        self.torch = SimpleNamespace(
            float16="float16", inference_mode=lambda: nullcontext())


@pytest.fixture
def load_space(monkeypatch, ledger, clock):
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

    def factory(*, init=False, execute=True, fail=False, with_sdk=True):
        fake = FakeTransformers(fail=fail)
        monkeypatch.setitem(sys.modules, "spaces", SimpleNamespace(GPU=decorate))
        monkeypatch.setitem(sys.modules, "gradio", SimpleNamespace(
            Blocks=lambda **kwargs: nullcontext(), Markdown=Element, Textbox=Element,
            Number=Element, Button=Element, Request=object, Error=FakeGradioError))
        if with_sdk:
            monkeypatch.setitem(sys.modules, "torch", fake.torch)
            monkeypatch.setitem(sys.modules, "transformers", fake.module)
        monkeypatch.setenv("ZEROGPU_BACKEND_KEY", KEY)
        monkeypatch.setenv("ZEROGPU_CONTROL_URL", CONTROL_URL)
        for name, on in (("SPACE_MODEL_INIT_APPROVED", init), ("SPACE_EXECUTION_APPROVED", execute)):
            if on:
                monkeypatch.setenv(name, "true")
            else:
                monkeypatch.delenv(name, raising=False)
        namespace = runpy.run_path(str(SPACE_APP), run_name="offline_space")
        # Route the Space's one admission POST into the REAL control router in-process.
        control_client = TestClient(create_app(extra_routers=(build_control_router(ledger, KEY),)))

        def claim(url, key, dispatch_id, tag):
            assert url == CONTROL_URL
            status = control_client.post(
                CLAIM_PATH, json={"dispatch_id": dispatch_id, "tag": tag},
                headers={PROOF_HEADER: claim_proof(key, dispatch_id, tag)}).status_code
            if status != 200:
                raise AdmissionError()

        namespace["authorize"].__globals__["_claim"] = claim
        return SimpleNamespace(ns=namespace, events=events, decorations=decorations,
                               fake=fake, error=FakeGradioError)

    return factory


def request_for(dispatch):
    return SimpleNamespace(headers={
        "x-mm-dispatch-id": dispatch.id, "x-mm-dispatch-time": str(dispatch.issued_at),
        "x-mm-dispatch-tag": dispatch.tag})


@pytest.fixture(autouse=True)
def space_clock(monkeypatch, clock):
    # The Space validates ticket age against wall time; align it with the test clock.
    monkeypatch.setattr(time, "time", lambda: clock[0])


def test_default_startup_loads_nothing_and_registers_real_handler(load_space):
    space = load_space(init=False, execute=False)
    assert space.decorations == [{"duration": 30, "size": "large"}]
    event = space.events[0]
    assert event["fn"] is space.ns["generate"] and event["validator"] is space.ns["authorize"]
    assert event["api_name"] == "generate" and event["concurrency_limit"] == 1
    assert space.ns["_model"] is space.ns["_tokenizer"] is None
    assert space.fake.loads == [] and space.fake.moves == [] and space.fake.generations == []


def test_init_flag_loads_once_at_startup_only_and_never_warms_up(load_space, ledger):
    space = load_space(init=True, execute=True)
    kinds = sorted(kind for kind, *_ in space.fake.loads)
    assert kinds == ["model", "tokenizer"]
    for _, model_id, kwargs in space.fake.loads:
        assert model_id == "Qwen/Qwen2.5-1.5B-Instruct"
        assert kwargs["revision"] == "989aa7980e4cf806f80c7fef2b1adb7bc71aa306"
        assert kwargs["trust_remote_code"] is False and kwargs["token"] is False
    assert space.fake.moves == ["cuda"]          # emulated placement at startup
    assert space.fake.generations == []          # no warm-up generation
    d = dispatch_for(ledger, 1)
    ledger.reserve(d.id, d.tag)
    request = request_for(d)
    assert space.ns["authorize"]("synthetic message", 128, request) == ("synthetic message", 128)
    assert space.ns["generate"]("synthetic message", 128, request) == "offline fake reply"
    assert len(space.fake.loads) == 2            # the handler never loads a model
    assert len(space.fake.generations) == 1
    assert space.fake.generations[0]["max_new_tokens"] == 128
    assert space.fake.generations[0]["do_sample"] is False


def test_failed_startup_load_fails_closed_without_error_text(load_space, ledger):
    space = load_space(init=True, execute=True, fail=True)
    assert space.ns["_model"] is None
    d = dispatch_for(ledger, 1)
    ledger.reserve(d.id, d.tag)
    request = request_for(d)
    space.ns["authorize"]("synthetic message", 128, request)
    with pytest.raises(space.error) as caught:
        space.ns["generate"]("synthetic message", 128, request)
    assert "secret" not in str(caught.value)
    assert len(space.fake.loads) == 1            # no retry


def test_inference_flag_is_independent_of_init_flag(load_space, ledger):
    space = load_space(init=True, execute=False)
    assert len(space.fake.loads) == 2            # init approved, inference not
    d = dispatch_for(ledger, 1)
    ledger.reserve(d.id, d.tag)
    request = request_for(d)
    with pytest.raises(space.error):
        space.ns["authorize"]("synthetic message", 128, request)
    with pytest.raises(space.error):
        space.ns["generate"]("synthetic message", 128, request)
    assert space.fake.generations == []
    # Inference approved but init not approved: admitted, then refused (no lazy load).
    space = load_space(init=False, execute=True)
    assert space.ns["_model"] is None
    assert space.fake.loads == []


@pytest.mark.parametrize("case", [
    "wrong_key", "no_headers", "tampered_message", "expired", "bad_tokens",
    "too_many_tokens", "fractional_tokens", "nan_tokens", "oversized", "unreserved",
    "replay", "no_control_url", "tag_for_other_message",
])
def test_space_gate_rejects_before_model_or_gpu(load_space, ledger, clock, monkeypatch, case):
    space = load_space(init=True, execute=True)
    message, tokens = "synthetic message", 128
    d = dispatch_for(ledger, 1, message)
    if case not in ("unreserved",):
        ledger.reserve(d.id, d.tag)
    request = request_for(d)
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
    elif case == "replay":
        space.ns["authorize"](message, 128, request)
    elif case == "no_control_url":
        monkeypatch.delenv("ZEROGPU_CONTROL_URL")
    elif case == "tag_for_other_message":
        request.headers["x-mm-dispatch-tag"] = sign_dispatch(KEY, d.id, d.issued_at, 128, "other")
    with pytest.raises(space.error) as caught:
        space.ns["authorize"](message, tokens, request)
    assert "synthetic message" not in str(caught.value)
    assert space.fake.generations == []


def test_handler_independently_rejects_unsigned_requests(load_space, ledger):
    space = load_space(init=True, execute=True)
    with pytest.raises(space.error):
        space.ns["generate"]("synthetic message", 128, SimpleNamespace(headers={}))
    assert space.fake.generations == []


def test_space_runtime_failure_leaves_backend_job_quarantined(load_space, ledger):
    space = load_space(init=True, execute=True)
    d = dispatch_for(ledger, 1)
    ledger.reserve(d.id, d.tag)
    request = request_for(d)
    space.ns["authorize"]("synthetic message", 128, request)

    def broken(*args):
        raise TimeoutError("synthetic message and credential must not escape")

    space.ns["generate"].__globals__["_generate_qwen"] = broken
    with pytest.raises(space.error) as caught:
        space.ns["generate"]("synthetic message", 128, request)
    assert "credential" not in str(caught.value)
    with sqlite3.connect(ledger.backend.path) as db:
        assert db.execute("SELECT attempts_left, active_job FROM budget").fetchone() == (5, d.id)


def test_space_module_has_no_database_or_quota_code():
    source = SPACE_APP.read_text()
    for forbidden in ("sqlite3", "libsql", "LIBSQL", "turso", "QuotaBudget", "SPACE_BUDGET_PATH"):
        assert forbidden not in source


# ---------------- entrypoint ----------------

def has_control(app):
    return TestClient(app).post(CLAIM_PATH, json={}).status_code != 404


def test_future_entrypoint_stays_disabled_by_default(monkeypatch):
    monkeypatch.delenv("ZEROGPU_EXECUTION_APPROVED", raising=False)
    assert importlib.import_module("approved_main").build_app().title == "Masari Chat API"


@pytest.mark.parametrize("setting", ["missing_storage", "bad_attempts", "bad_key", "bad_url", "no_token"])
def test_future_entrypoint_bad_configuration_fails_closed(monkeypatch, backend, setting):
    import approved_main

    monkeypatch.setenv("ZEROGPU_EXECUTION_APPROVED", "true")
    monkeypatch.setenv("HF_TOKEN", "synthetic-read-token")
    monkeypatch.setenv("ZEROGPU_BACKEND_KEY", KEY)
    monkeypatch.setenv("LEDGER_LOCAL_PATH", str(backend.path))
    monkeypatch.delenv("LIBSQL_URL", raising=False)
    monkeypatch.delenv("LIBSQL_AUTH_TOKEN", raising=False)
    ok = approved_main.build_app()
    assert has_control(ok)  # control mounted only when configuration is valid
    if setting == "missing_storage":
        monkeypatch.delenv("LEDGER_LOCAL_PATH")
    elif setting == "bad_attempts":
        monkeypatch.setenv("ZEROGPU_MAX_ATTEMPTS", "7")
    elif setting == "bad_key":
        monkeypatch.setenv("ZEROGPU_BACKEND_KEY", "short")
        # A short key makes every dispatch fail closed at use time.
        client = TestClient(approved_main.build_app())
        assert client.post("/chat", json={"message": "x"}, auth=("u", "p")).status_code in (401, 503)
        return
    elif setting == "bad_url":
        monkeypatch.delenv("LEDGER_LOCAL_PATH")
        monkeypatch.setenv("LIBSQL_URL", "http://insecure.invalid")
        monkeypatch.setenv("LIBSQL_AUTH_TOKEN", "synthetic")
    else:
        monkeypatch.delenv("HF_TOKEN")
    degraded = approved_main.build_app()
    assert not has_control(degraded)


def test_offline_end_to_end_with_real_control_endpoint(load_space, ledger, monkeypatch, caplog, no_outbound_network):
    """API + adapter + transport + control endpoint + Space gate, all fake SDK/engine."""
    space = load_space(init=True, execute=True)
    monkeypatch.setenv("CHAT_AUTH_USERS", json.dumps({
        "first": __import__("security").hash_password("synthetic-password"),
        "second": __import__("security").hash_password("synthetic-password")}))
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
        token="synthetic-read-token", execution_approved=True, client_factory=client_factory),
        ledger, dispatch_key=KEY)
    client = TestClient(create_app(generator=generator))
    assert client.post("/chat", json={"message": "synthetic"}).status_code == 401 and not calls
    for i in range(6):
        response = client.post("/chat", json={"message": "synthetic"},
                               auth=(["first", "second"][i % 2], "synthetic-password"))
        assert response.status_code == 200 and response.json() == {"reply": "offline fake reply"}
    assert client.post("/chat", json={"message": "synthetic"},
                       auth=("first", "synthetic-password")).status_code == 503
    assert len(calls) == 6 and len(space.fake.generations) == 6
    assert len(space.fake.loads) == 2             # model loaded once, at startup
    with sqlite3.connect(ledger.backend.path) as db:
        assert db.execute("SELECT attempts_left, active_job FROM budget").fetchone() == (0, None)
        assert db.execute("SELECT COUNT(*) FROM space_admissions").fetchone() == (6,)
    raw = ledger.backend.path.read_bytes()
    assert KEY.encode() not in raw and b"synthetic" not in raw
    assert not no_outbound_network and KEY not in caplog.text
