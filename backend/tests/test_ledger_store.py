"""Central ledger tests. Local temporary SQLite only: this is NOT Turso behaviour.

Remote libSQL transaction semantics remain UNVERIFIED; the Hrana adapter is only
exercised with a fake transport.
"""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import json
import os
import sqlite3

import pytest

from conftest import KEY, make_snapshot
from dispatch_auth import Dispatch, sign_dispatch
from ledger_store import (
    CentralLedger, HranaHttpBackend, SqliteFileBackend, StatementResult,
    StoreConflict, StoreUnavailable, create_local_test_database,
    provision_schema, validate_ledger_path,
)
from zerogpu import GenerationUnavailable


def new_dispatch(ledger, n=0, message="synthetic offline message"):
    dispatch_id = f"{n:032x}"
    issued = int(ledger.clock())
    return Dispatch(dispatch_id, issued, sign_dispatch(KEY, dispatch_id, issued, 128, message))


def state(ledger):
    with sqlite3.connect(ledger.backend.path) as db:
        return db.execute(
            "SELECT attempts_left, gpu_seconds_left, active_job FROM budget"
        ).fetchone()


def cycle(ledger, n):
    d = new_dispatch(ledger, n)
    ledger.reserve(d.id, d.tag)
    ledger.claim(d.id, d.tag)
    ledger.finish(d.id)
    return d


# ---------------- happy path and privacy ----------------

def test_verify_reserve_claim_finish_and_no_user_data(ledger, backend):
    ledger.verify()
    d = new_dispatch(ledger, 1)
    ledger.reserve(d.id, d.tag)
    assert state(ledger) == (5, 150, d.id)
    ledger.claim(d.id, d.tag)
    ledger.finish(d.id)
    assert state(ledger) == (5, 150, None)  # attempt is spent, never refunded
    raw = backend.path.read_bytes()
    assert b"synthetic offline message" not in raw
    assert KEY.encode() not in raw
    with sqlite3.connect(backend.path) as db:
        assert db.execute("SELECT state FROM backend_reservations").fetchall() == [("completed",)]
        assert db.execute("SELECT dispatch_id FROM space_admissions").fetchall() == [(d.id,)]


def test_six_attempts_across_restarts_then_exhausted(backend, clock, ledger):
    for n in range(6):
        reopened = CentralLedger(SqliteFileBackend(backend.path), clock=lambda: clock[0])
        cycle(reopened, n + 1)
    d = new_dispatch(ledger, 99)
    with pytest.raises(GenerationUnavailable):
        ledger.reserve(d.id, d.tag)
    assert state(ledger) == (0, 0, None)


def test_lower_ceiling_cannot_be_exceeded_or_raised(backend, clock):
    for value in (0, 7, True, 1.5, "6"):
        with pytest.raises(ValueError):
            CentralLedger(backend, max_attempts=value)
    strict = CentralLedger(backend, clock=lambda: clock[0], max_attempts=2)
    with pytest.raises(GenerationUnavailable):  # existing 6-attempt window > ceiling 2
        d = new_dispatch(strict, 1)
        strict.reserve(d.id, d.tag)


# ---------------- replay and one-use claims ----------------

def test_replayed_reservation_rolls_back_atomically(ledger):
    d = cycle(ledger, 1)
    before = state(ledger)
    with pytest.raises(GenerationUnavailable):
        ledger.reserve(d.id, d.tag)
    assert state(ledger) == before  # the charge in the same batch was rolled back


def test_claim_is_single_use_and_bound_to_tag_and_reservation(ledger, clock):
    d = new_dispatch(ledger, 1)
    with pytest.raises(GenerationUnavailable):  # unknown dispatch
        ledger.claim(d.id, d.tag)
    ledger.reserve(d.id, d.tag)
    with pytest.raises(GenerationUnavailable):  # wrong tag
        ledger.claim(d.id, "0" * 64)
    ledger.claim(d.id, d.tag)
    with pytest.raises(GenerationUnavailable):  # duplicate claim
        ledger.claim(d.id, d.tag)
    ledger.finish(d.id)
    with pytest.raises(GenerationUnavailable):  # claim after completion
        ledger.claim(d.id, d.tag)


def test_claim_rejected_after_ticket_expiry(ledger, clock):
    d = new_dispatch(ledger, 1)
    ledger.reserve(d.id, d.tag)
    clock[0] += 91
    with pytest.raises(GenerationUnavailable):
        ledger.claim(d.id, d.tag)


def test_finish_requires_prior_admission(ledger):
    d = new_dispatch(ledger, 1)
    ledger.reserve(d.id, d.tag)
    with pytest.raises(GenerationUnavailable):
        ledger.finish(d.id)
    assert state(ledger)[2] == d.id  # still locked


@pytest.mark.parametrize("bad", ["", "A" * 32, "g" * 32, "a" * 31, None, 7])
def test_malformed_ids_and_tags_are_rejected(ledger, bad):
    for call in (lambda: ledger.reserve(bad, "a" * 64), lambda: ledger.claim(bad, "a" * 64),
                 lambda: ledger.finish(bad), lambda: ledger.reserve("a" * 32, bad)):
        with pytest.raises(GenerationUnavailable):
            call()


# ---------------- concurrency ----------------

def test_concurrent_reservations_admit_exactly_one(backend, clock, ledger):
    def attempt(n):
        mine = CentralLedger(SqliteFileBackend(backend.path), clock=lambda: clock[0])
        d = new_dispatch(mine, n + 1)
        try:
            mine.reserve(d.id, d.tag)
            return d
        except GenerationUnavailable:
            return None

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(attempt, range(8)))
    winners = [r for r in results if r]
    assert len(winners) == 1
    assert state(ledger) == (5, 150, winners[0].id)


def test_concurrent_duplicate_claims_admit_exactly_one(backend, clock, ledger):
    d = new_dispatch(ledger, 1)
    ledger.reserve(d.id, d.tag)

    def claim(_):
        mine = CentralLedger(SqliteFileBackend(backend.path), clock=lambda: clock[0])
        try:
            mine.claim(d.id, d.tag)
            return True
        except GenerationUnavailable:
            return False

    with ThreadPoolExecutor(max_workers=8) as pool:
        assert sum(pool.map(claim, range(8))) == 1
    with sqlite3.connect(backend.path) as db:
        assert db.execute("SELECT COUNT(*) FROM space_admissions").fetchone() == (1,)


# ---------------- stale / uncertain recovery ----------------

def test_expired_unclaimed_ticket_frees_lock_without_refund(ledger, clock):
    a = new_dispatch(ledger, 1)
    ledger.reserve(a.id, a.tag)
    b = new_dispatch(ledger, 2)
    with pytest.raises(GenerationUnavailable):  # still active inside the ticket window
        ledger.reserve(b.id, b.tag)
    clock[0] += 91
    b = new_dispatch(ledger, 2)
    ledger.reserve(b.id, b.tag)  # safe: A can never be claimed now
    assert state(ledger) == (4, 120, b.id)  # A was NOT refunded


def test_claimed_but_unfinished_job_stays_quarantined_until_operator_closes(ledger, clock):
    a = new_dispatch(ledger, 1)
    ledger.reserve(a.id, a.tag)
    ledger.claim(a.id, a.tag)
    clock[0] += 86_400 * 2  # even a whole window later
    with pytest.raises(GenerationUnavailable):
        ledger.arm(make_snapshot(clock[0]))
    b = new_dispatch(ledger, 2)
    with pytest.raises(GenerationUnavailable):
        ledger.reserve(b.id, b.tag)
    with pytest.raises(GenerationUnavailable):
        ledger.close_uncertain(a.id, acknowledged=False)
    ledger.close_uncertain(a.id, acknowledged=True)
    assert state(ledger) == (5, 150, None)  # lock freed, attempt still spent
    ledger.arm(make_snapshot(clock[0]))


def test_restart_preserves_active_uncertain_job(backend, clock, ledger):
    a = new_dispatch(ledger, 1)
    ledger.reserve(a.id, a.tag)
    ledger.claim(a.id, a.tag)
    reopened = CentralLedger(SqliteFileBackend(backend.path), clock=lambda: clock[0])
    b = new_dispatch(reopened, 2)
    with pytest.raises(GenerationUnavailable):
        reopened.reserve(b.id, b.tag)


# ---------------- arming ----------------

@pytest.mark.parametrize("change", [
    {"observed_at": 999_939.0}, {"observed_at": 1_000_001.0},
    {"observed_at": float("nan")}, {"observed_at": True},
    {"gpu_seconds_remaining": 0}, {"gpu_seconds_remaining": 89},
    {"gpu_seconds_remaining": 301}, {"gpu_seconds_remaining": True},
    {"runs_remaining": 2}, {"runs_remaining": 9}, {"runs_remaining": "8"},
    {"overquota_used": 1}, {"personal_free_account_confirmed": False},
    {"paid_usage_disabled_confirmed": False},
])
def test_arming_requires_fresh_conservative_free_quota(backend, clock, change):
    fresh = CentralLedger(backend, clock=lambda: clock[0])
    with pytest.raises(GenerationUnavailable):
        fresh.arm(replace(make_snapshot(clock[0]), **change))
    d = new_dispatch(fresh, 1)
    with pytest.raises(GenerationUnavailable):  # still disarmed
        fresh.reserve(d.id, d.tag)


def test_armed_window_cannot_be_replenished_or_rolled_back(ledger, clock):
    cycle(ledger, 1)
    with pytest.raises(GenerationUnavailable):
        ledger.arm(make_snapshot(clock[0]))
    clock[0] += 86_400  # window over: stops, then only a NEWER snapshot may re-arm
    d = new_dispatch(ledger, 2)
    with pytest.raises(GenerationUnavailable):
        ledger.reserve(d.id, d.tag)
    clock[0] -= 30
    with pytest.raises(GenerationUnavailable):  # stale/older evidence (and clock)
        ledger.arm(make_snapshot(clock[0] - 10))
    clock[0] += 30
    ledger.arm(make_snapshot(clock[0]))
    cycle(ledger, 3)


# ---------------- storage failure, corruption, incompatibility ----------------

def test_storage_outage_fails_closed_without_raw_errors(clock):
    class Down:
        def batch(self, statements):
            raise RuntimeError("synthetic secret host and token")

    down = CentralLedger(Down(), clock=lambda: clock[0])
    d = new_dispatch(down, 1)
    for call in (lambda: down.reserve(d.id, d.tag), lambda: down.claim(d.id, d.tag),
                 lambda: down.finish(d.id), down.verify):
        with pytest.raises(GenerationUnavailable) as caught:
            call()
        assert "secret" not in repr(caught.value)


def test_corrupt_file_fails_closed(ledger):
    ledger.backend.path.write_bytes(b"synthetic invalid sqlite data" * 50)
    os.chmod(ledger.backend.path, 0o600)
    d = new_dispatch(ledger, 1)
    with pytest.raises(GenerationUnavailable):
        ledger.reserve(d.id, d.tag)


def test_missing_file_is_never_recreated(ledger):
    path = ledger.backend.path
    path.unlink()
    d = new_dispatch(ledger, 1)
    with pytest.raises(GenerationUnavailable):
        ledger.reserve(d.id, d.tag)
    assert not path.exists()
    with pytest.raises(StoreUnavailable):
        SqliteFileBackend(path)


def test_empty_database_without_schema_is_rejected(ledger_dir, clock):
    path = ledger_dir / "empty.sqlite3"
    os.close(os.open(path, os.O_CREAT | os.O_RDWR, 0o600))
    empty = CentralLedger(SqliteFileBackend(path), clock=lambda: clock[0])
    with pytest.raises(GenerationUnavailable):
        empty.verify()
    d = new_dispatch(empty, 1)
    with pytest.raises(GenerationUnavailable):
        empty.reserve(d.id, d.tag)


def test_incompatible_schema_version_fails_closed(ledger):
    with sqlite3.connect(ledger.backend.path) as db:
        db.execute("UPDATE meta SET value = '2'")
    d = new_dispatch(ledger, 1)
    with pytest.raises(GenerationUnavailable):
        ledger.reserve(d.id, d.tag)
    with pytest.raises(GenerationUnavailable):
        ledger.verify()


def test_provisioning_never_overwrites_an_existing_ledger(ledger, backend):
    with pytest.raises(StoreUnavailable):
        provision_schema(backend)
    with pytest.raises(FileExistsError):
        create_local_test_database(backend.path)
    assert state(ledger) == (6, 180, None)


# ---------------- local file permissions and symlink attacks ----------------

def test_unsafe_ledger_files_are_rejected(ledger_dir, tmp_path, backend):
    path = backend.path
    validate_ledger_path(path)
    with pytest.raises(StoreUnavailable):
        validate_ledger_path("relative.sqlite3")
    with pytest.raises(StoreUnavailable):
        validate_ledger_path(str(ledger_dir / ".." / "ledger" / "ledger.sqlite3"))
    for mode in (0o660, 0o604, 0o644):
        os.chmod(path, mode)
        with pytest.raises(StoreUnavailable):
            validate_ledger_path(path)
    os.chmod(path, 0o600)
    os.chmod(ledger_dir, 0o770)
    with pytest.raises(StoreUnavailable):
        validate_ledger_path(path)
    os.chmod(ledger_dir, 0o700)
    validate_ledger_path(path)


def test_symlink_hardlink_and_special_files_are_rejected(ledger_dir, tmp_path, backend):
    link = ledger_dir / "link.sqlite3"
    link.symlink_to(backend.path)
    with pytest.raises(StoreUnavailable):
        validate_ledger_path(link)
    linked_dir = tmp_path / "dirlink"
    linked_dir.symlink_to(ledger_dir)
    with pytest.raises(StoreUnavailable):
        validate_ledger_path(linked_dir / "ledger.sqlite3")
    os.link(backend.path, ledger_dir / "second-name")
    with pytest.raises(StoreUnavailable):
        validate_ledger_path(backend.path)
    os.unlink(ledger_dir / "second-name")
    sidecar = ledger_dir / "ledger.sqlite3-journal"
    sidecar.write_bytes(b"x")
    os.chmod(sidecar, 0o666)
    with pytest.raises(StoreUnavailable):
        validate_ledger_path(backend.path)
    sidecar.unlink()
    (ledger_dir / "dir.sqlite3").mkdir()
    with pytest.raises(StoreUnavailable):
        validate_ledger_path(ledger_dir / "dir.sqlite3")


def test_file_swapped_after_validation_is_rejected(ledger, clock):
    path = ledger.backend.path
    path.rename(path.with_name("moved"))
    other = create_local_test_database(path)  # a different, valid-looking database
    assert other.path == path
    d = new_dispatch(ledger, 1)
    with pytest.raises(GenerationUnavailable):
        ledger.reserve(d.id, d.tag)


# ---------------- Turso/libSQL adapter: MOCK transport only ----------------

def hrana_ok(rows_affected, count):
    results = [{"affected_row_count": 0, "rows": []}]
    results += [{"affected_row_count": n, "rows": []} for n in rows_affected]
    results += [{"affected_row_count": 0, "rows": []}, None]
    return {"results": [
        {"type": "ok", "response": {"type": "batch", "result": {
            "step_results": results, "step_errors": [None] * (count + 3)}}},
        {"type": "ok", "response": {"type": "close"}},
    ]}


def test_hrana_request_shape_and_parsing_with_fake_transport(no_outbound_network):
    seen = []

    def post(url, headers, body, timeout):
        seen.append((url, headers, json.loads(body), timeout))
        return 200, json.dumps(hrana_ok([1, 1], 2)).encode()

    backend = HranaHttpBackend(
        url="libsql://synthetic.invalid", auth_token="synthetic-token", post=post,
    )
    result = backend.batch([("UPDATE t SET a = ?1", ("x",)), ("INSERT INTO t VALUES (?1)", (3,))])
    assert [r.rows_affected for r in result] == [1, 1]
    url, headers, body, timeout = seen[0]
    assert url == "https://synthetic.invalid/v2/pipeline"
    assert headers["Authorization"] == "Bearer synthetic-token"
    assert "synthetic-token" not in json.dumps(body)
    steps = body["requests"][0]["batch"]["steps"]
    assert steps[0]["stmt"]["sql"] == "BEGIN IMMEDIATE"
    assert steps[1]["condition"] == {"type": "ok", "step": 0}
    assert steps[2]["condition"] == {"type": "ok", "step": 1}
    assert steps[3]["stmt"]["sql"] == "COMMIT"
    assert steps[4]["stmt"]["sql"] == "ROLLBACK"
    assert steps[1]["stmt"]["args"] == [{"type": "text", "value": "x"}]
    assert steps[2]["stmt"]["args"] == [{"type": "integer", "value": "3"}]


@pytest.mark.parametrize("url", [
    "http://synthetic.invalid", "https://user:pw@synthetic.invalid", "https://",
    "https://synthetic.invalid?token=x", "", None,
])
def test_hrana_rejects_insecure_or_credentialed_urls(url):
    with pytest.raises(StoreUnavailable):
        HranaHttpBackend(url=url, auth_token="synthetic-token", post=lambda *a: (200, b""))
    with pytest.raises(StoreUnavailable):
        HranaHttpBackend(url="https://synthetic.invalid", auth_token="", post=lambda *a: (200, b""))


def test_hrana_errors_are_sanitized_and_constraint_maps_to_conflict():
    def failing(status, payload):
        return HranaHttpBackend(
            url="https://synthetic.invalid", auth_token="synthetic-token",
            post=lambda *a: (status, payload),
        )

    conflict = hrana_ok([0], 1)
    conflict["results"][0]["response"]["result"]["step_errors"][1] = {
        "message": "UNIQUE constraint failed", "code": "SQLITE_CONSTRAINT"}
    stmts = [("UPDATE t SET a = 1", ())]
    with pytest.raises(StoreConflict):
        failing(200, json.dumps(conflict).encode()).batch(stmts)
    for status, payload in ((500, b"synthetic-token leaked"), (200, b"not json"),
                            (200, json.dumps({"results": []}).encode())):
        with pytest.raises(StoreUnavailable) as caught:
            failing(status, payload).batch(stmts)
        assert "synthetic-token" not in repr(caught.value)
    not_committed = hrana_ok([1], 1)
    not_committed["results"][0]["response"]["result"]["step_results"][-1] = None
    not_committed["results"][0]["response"]["result"]["step_results"][-2] = None
    with pytest.raises(StoreUnavailable):
        failing(200, json.dumps(not_committed).encode()).batch(stmts)

    def boom(*args):
        raise OSError("synthetic-token connection detail")

    with pytest.raises(StoreUnavailable) as caught:
        HranaHttpBackend(url="https://synthetic.invalid", auth_token="synthetic-token",
                         post=boom).batch(stmts)
    assert "synthetic-token" not in repr(caught.value)
