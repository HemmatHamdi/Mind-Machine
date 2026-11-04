"""Central ledger: one authoritative database, two logical ledgers.

* backend reservation ledger  -> table ``backend_reservations``
* Space admission ledger      -> table ``space_admissions``
Both plus the shared attempt budget live in ONE database and change only through
single atomic, guarded batches (all statements commit together or not at all).

OFFLINE CODE ONLY. Turso/libSQL is the intended production target, but:
  * ``HranaHttpBackend`` is a code-level adapter that has NEVER been run against a
    real Turso service. Remote transaction behaviour is UNVERIFIED.
  * ``SqliteFileBackend`` is a local, temporary-file stand-in for offline tests.
    It is not production Turso behaviour.
No driver/dependency is imported at module import; nothing here creates a database
account, database or credential. The ledger stores no chat text, replies,
passwords or tokens: only opaque IDs, a keyed dispatch tag, states and counters.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
import math
import os
from pathlib import Path
import sqlite3
import stat
import time
from typing import Any, Protocol
from urllib.parse import quote, urlsplit

from dispatch_auth import TICKET_TTL_SECONDS, valid_dispatch_id, valid_tag
from zerogpu import (
    GPU_RESERVE_SECONDS, GPU_SECONDS_PER_ATTEMPT, GenerationUnavailable,
    MAX_ATTEMPTS, ManualQuotaSnapshot, RUN_RESERVE, WINDOW_SECONDS,
)

SCHEMA_VERSION = "1"
_SCHEMA_GUARD = (
    "EXISTS(SELECT 1 FROM meta WHERE key = 'schema_version' AND value = '1')"
)
_TABLES = ("meta", "budget", "backend_reservations", "space_admissions")
Statement = tuple[str, tuple]


class StoreUnavailable(Exception):
    """Storage is down, corrupt, missing, incompatible or unsafe. Fail closed."""


class StoreConflict(StoreUnavailable):
    """A uniqueness/constraint violation rolled the whole batch back."""


@dataclass(frozen=True)
class StatementResult:
    rows_affected: int
    rows: tuple


class LedgerBackend(Protocol):
    def batch(self, statements: Sequence[Statement]) -> list[StatementResult]:
        """Run all statements in ONE atomic transaction, or none of them.

        Parameters are positional and referenced as ?1, ?2, ... Any error rolls
        everything back and raises StoreUnavailable (StoreConflict for constraints).
        """


# --------------------------------------------------------------------------
# Schema (operator-only; never run by the request path)
# --------------------------------------------------------------------------

SCHEMA_STATEMENTS: tuple[Statement, ...] = (
    ("CREATE TABLE meta (key TEXT PRIMARY KEY NOT NULL, value TEXT NOT NULL)", ()),
    ("""CREATE TABLE budget (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        expires_at REAL NOT NULL,
        attempts_left INTEGER NOT NULL CHECK (attempts_left >= 0),
        gpu_seconds_left INTEGER NOT NULL CHECK (gpu_seconds_left >= 0),
        active_job TEXT,
        armed_at REAL NOT NULL)""", ()),
    ("""CREATE TABLE backend_reservations (
        id TEXT PRIMARY KEY NOT NULL,
        tag TEXT NOT NULL,
        state TEXT NOT NULL CHECK (state IN
            ('reserved','claimed','completed','expired_unclaimed','closed_uncertain')),
        reserved_at REAL NOT NULL,
        ticket_expires REAL NOT NULL)""", ()),
    ("""CREATE TABLE space_admissions (
        dispatch_id TEXT PRIMARY KEY NOT NULL,
        admitted_at REAL NOT NULL)""", ()),
    ("INSERT INTO meta VALUES ('schema_version', ?1)", (SCHEMA_VERSION,)),
    # Disarmed: zero attempts until an operator arms it with fresh evidence.
    ("INSERT INTO budget VALUES (1, 0, 0, 0, NULL, 0)", ()),
)


def provision_schema(backend: LedgerBackend) -> None:
    """Operator action. Plain CREATE TABLE: fails if anything already exists, so it
    can never silently recreate or reset an existing ledger."""
    backend.batch(SCHEMA_STATEMENTS)


# --------------------------------------------------------------------------
# Local SQLite stand-in (offline tests only) with file-safety validation
# --------------------------------------------------------------------------

def _check_owned_private(st: os.stat_result, *, directory: bool) -> None:
    kind_ok = stat.S_ISDIR(st.st_mode) if directory else stat.S_ISREG(st.st_mode)
    if (
        not kind_ok or st.st_uid != os.geteuid() or st.st_mode & 0o077
        or (not directory and st.st_nlink != 1)
    ):
        raise StoreUnavailable()


def validate_ledger_path(path) -> tuple[Path, tuple[int, int]]:
    """Absolute, symlink-free, owner-only regular file; returns (path, (dev, ino)).

    The parent must be an owner-only directory (0700). The file must be owner-only
    (no group/other bits), a regular file, and not hard-linked. Existing SQLite
    sidecars (-wal/-shm/-journal) must satisfy the same rules. A residual TOCTOU
    window between validation and open is narrowed by an inode re-check.
    """
    try:
        candidate = Path(path)
        if not candidate.is_absolute() or ".." in candidate.parts:
            raise StoreUnavailable()
        current = Path(candidate.anchor)
        for part in candidate.parts[1:]:
            current = current / part
            if stat.S_ISLNK(os.lstat(current).st_mode):
                raise StoreUnavailable()
        _check_owned_private(os.lstat(candidate.parent), directory=True)
        file_stat = os.lstat(candidate)
        _check_owned_private(file_stat, directory=False)
        for suffix in ("-wal", "-shm", "-journal"):
            sidecar = Path(str(candidate) + suffix)
            if os.path.lexists(sidecar):
                _check_owned_private(os.lstat(sidecar), directory=False)
        return candidate, (file_stat.st_dev, file_stat.st_ino)
    except StoreUnavailable:
        raise
    except Exception:
        raise StoreUnavailable() from None


class SqliteFileBackend:
    """TEST-ONLY local database. Never creates the file; opens mode=rw only."""

    def __init__(self, path):
        self.path, self._identity = validate_ledger_path(path)

    def batch(self, statements: Sequence[Statement]) -> list[StatementResult]:
        path, identity = validate_ledger_path(self.path)
        if identity != self._identity:
            raise StoreUnavailable()
        db = None
        try:
            db = sqlite3.connect(
                f"file:{quote(str(path))}?mode=rw", uri=True, timeout=5,
                isolation_level=None,
            )
            db.execute("PRAGMA trusted_schema = OFF")
            after = os.stat(path)
            if (after.st_dev, after.st_ino) != identity:
                raise StoreUnavailable()
            results: list[StatementResult] = []
            db.execute("BEGIN IMMEDIATE")
            try:
                for sql, params in statements:
                    cursor = db.execute(sql, params)
                    if cursor.description is not None:
                        results.append(StatementResult(0, tuple(cursor.fetchall())))
                    else:
                        results.append(StatementResult(max(cursor.rowcount, 0), ()))
                db.execute("COMMIT")
            except BaseException:
                db.execute("ROLLBACK")
                raise
            return results
        except StoreUnavailable:
            raise
        except sqlite3.IntegrityError:
            raise StoreConflict() from None
        except Exception:
            raise StoreUnavailable() from None
        finally:
            if db is not None:
                db.close()


def create_local_test_database(path) -> SqliteFileBackend:
    """TEST ONLY: create an isolated temporary database. Refuses to overwrite."""
    candidate = Path(path)
    if not candidate.is_absolute():
        raise StoreUnavailable()
    descriptor = os.open(
        candidate, os.O_CREAT | os.O_EXCL | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0),
        0o600,
    )
    os.close(descriptor)
    backend = SqliteFileBackend(candidate)
    provision_schema(backend)
    return backend


# --------------------------------------------------------------------------
# Turso/libSQL adapter (Hrana-over-HTTP). UNVERIFIED against a real service.
# --------------------------------------------------------------------------

def _hrana_value(value: Any) -> dict:
    if value is None:
        return {"type": "null"}
    if isinstance(value, bool):
        return {"type": "integer", "value": str(int(value))}
    if isinstance(value, int):
        return {"type": "integer", "value": str(value)}
    if isinstance(value, float):
        return {"type": "float", "value": value}
    if isinstance(value, str):
        return {"type": "text", "value": value}
    raise StoreUnavailable()


def _from_hrana(value: dict) -> Any:
    kind = value.get("type")
    if kind == "null":
        return None
    if kind == "integer":
        return int(value["value"])
    if kind in ("float", "text"):
        return float(value["value"]) if kind == "float" else str(value["value"])
    raise StoreUnavailable()


class HranaHttpBackend:
    """Sends each ledger batch as ONE conditional Hrana batch request:
    BEGIN, statements chained on success, COMMIT, and ROLLBACK if COMMIT did not run.

    Request/response shapes follow the published Hrana-over-HTTP v2 pipeline
    format but are UNVERIFIED here: no real endpoint is contacted and none is
    authorised. The URL/token are injected by the operator after separate approval;
    the token is never logged or included in an exception. ``post`` is injectable so
    tests never touch the network.
    """

    def __init__(self, *, url: str, auth_token: str,
                 post: Callable[[str, dict, bytes, float], tuple[int, bytes]] | None = None,
                 timeout: float = 10.0):
        parts = urlsplit(url.replace("libsql://", "https://", 1)
                         if isinstance(url, str) else "")
        if (
            parts.scheme != "https" or not parts.hostname or parts.username
            or parts.password or parts.query or parts.fragment
            or not isinstance(auth_token, str) or not auth_token
            or not 0 < timeout <= 30
        ):
            raise StoreUnavailable()
        self._endpoint = f"https://{parts.netloc}/v2/pipeline"
        self._token = auth_token
        self._post = post or _urllib_post
        self._timeout = timeout

    def batch(self, statements: Sequence[Statement]) -> list[StatementResult]:
        import json

        count = len(statements)
        steps: list[dict] = [{"stmt": {"sql": "BEGIN IMMEDIATE"}}]
        for index, (sql, params) in enumerate(statements):
            steps.append({
                "stmt": {"sql": sql, "args": [_hrana_value(p) for p in params]},
                "condition": {"type": "ok", "step": index},
            })
        steps.append({"stmt": {"sql": "COMMIT"},
                      "condition": {"type": "ok", "step": count}})
        steps.append({"stmt": {"sql": "ROLLBACK"}, "condition": {
            "type": "not", "cond": {"type": "ok", "step": count + 1}}})
        body = json.dumps({"requests": [
            {"type": "batch", "batch": {"steps": steps}}, {"type": "close"},
        ]}).encode()
        try:
            status, raw = self._post(
                self._endpoint,
                {"Authorization": f"Bearer {self._token}",
                 "Content-Type": "application/json"},
                body, self._timeout,
            )
            if status != 200 or len(raw) > 1_000_000:
                raise StoreUnavailable()
            result = json.loads(raw)["results"][0]
            if result.get("type") != "ok":
                raise StoreUnavailable()
            payload = result["response"]["result"]
            step_results, step_errors = payload["step_results"], payload["step_errors"]
            for error in step_errors[: count + 2]:
                if error is not None:
                    message = str(error.get("message", "")).upper()
                    code = str(error.get("code", "")).upper()
                    if "CONSTRAINT" in message or "CONSTRAINT" in code:
                        raise StoreConflict()
                    raise StoreUnavailable()
            if step_results[count + 1] is None:
                raise StoreUnavailable()  # COMMIT did not run
            out = []
            for entry in step_results[1: count + 1]:
                rows = tuple(
                    tuple(_from_hrana(cell) for cell in row)
                    for row in entry.get("rows", [])
                )
                out.append(StatementResult(int(entry.get("affected_row_count", 0)), rows))
            return out
        except StoreUnavailable:
            raise
        except Exception:
            raise StoreUnavailable() from None


def _urllib_post(url: str, headers: dict, body: bytes, timeout: float):
    """Default transport; only reachable after separate live-execution approval."""
    import urllib.error
    import urllib.request

    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs):
            return None

    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.build_opener(NoRedirect).open(request, timeout=timeout) as r:
            return r.status, r.read(1_000_001)
    except urllib.error.HTTPError as error:
        return error.code, b""


# --------------------------------------------------------------------------
# The ledger
# --------------------------------------------------------------------------

def _expire_unclaimed(now: float) -> list[Statement]:
    """A never-claimed ticket can no longer reach the GPU once it expires (claims
    are judged by the backend clock), so releasing the single-job lock is safe.
    This NEVER refunds the attempt."""
    return [
        ("UPDATE backend_reservations SET state = 'expired_unclaimed' "
         "WHERE state = 'reserved' AND ticket_expires <= ?1", (now,)),
        ("UPDATE budget SET active_job = NULL WHERE id = 1 AND active_job IN "
         "(SELECT id FROM backend_reservations WHERE state = 'expired_unclaimed')", ()),
    ]


class CentralLedger:
    """Atomic reservation/admission/finish over any LedgerBackend. Fails closed."""

    def __init__(self, backend: LedgerBackend, *, clock: Callable[[], float] = time.time,
                 max_attempts: int = MAX_ATTEMPTS):
        if type(max_attempts) is not int or not 1 <= max_attempts <= MAX_ATTEMPTS:
            raise ValueError("Invalid local attempt ceiling.")
        self.backend = backend
        self.clock = clock
        self.max_attempts = max_attempts

    def _run(self, statements: Sequence[Statement]) -> list[StatementResult]:
        try:
            return self.backend.batch(statements)
        except Exception:
            raise GenerationUnavailable() from None

    def _now(self) -> float:
        now = self.clock()
        if not math.isfinite(now):
            raise GenerationUnavailable()
        return now

    def verify(self) -> None:
        """Startup readiness check: schema version, tables and budget row exist."""
        results = self._run([
            ("SELECT value FROM meta WHERE key = 'schema_version'", ()),
            ("SELECT COUNT(*) FROM budget WHERE id = 1", ()),
            ("SELECT COUNT(*) FROM sqlite_master WHERE type = 'table' AND name IN "
             "('meta','budget','backend_reservations','space_admissions')", ()),
        ])
        if (
            results[0].rows != ((SCHEMA_VERSION,),) or results[1].rows != ((1,),)
            or results[2].rows != ((len(_TABLES),),)
        ):
            raise GenerationUnavailable()

    def arm(self, snapshot: ManualQuotaSnapshot) -> None:
        """Operator action with fresh manual evidence. Never replenishes while a job
        is active or the previous window is live, and never accepts an older
        snapshot than the last one (no restoring old state)."""
        now = self._now()
        if (
            not isinstance(snapshot, ManualQuotaSnapshot)
            or type(snapshot.observed_at) not in (int, float)
            or not math.isfinite(snapshot.observed_at)
            or not 0 <= now - snapshot.observed_at <= 60
            or snapshot.personal_free_account_confirmed is not True
            or snapshot.paid_usage_disabled_confirmed is not True
            or type(snapshot.overquota_used) is not int or snapshot.overquota_used != 0
            or type(snapshot.gpu_seconds_remaining) is not int
            or type(snapshot.runs_remaining) is not int
            or not 0 <= snapshot.gpu_seconds_remaining <= 300
            or not 0 <= snapshot.runs_remaining <= 8
        ):
            raise GenerationUnavailable()
        attempts = min(
            self.max_attempts, max(0, snapshot.runs_remaining - RUN_RESERVE),
            max(0, (snapshot.gpu_seconds_remaining - GPU_RESERVE_SECONDS)
                // GPU_SECONDS_PER_ATTEMPT),
        )
        if attempts == 0:
            raise GenerationUnavailable()
        results = self._run([
            *_expire_unclaimed(now),
            ("UPDATE budget SET expires_at = ?1, attempts_left = ?2, "
             "gpu_seconds_left = ?3, armed_at = ?4 "
             "WHERE id = 1 AND active_job IS NULL AND expires_at <= ?5 "
             f"AND armed_at < ?4 AND {_SCHEMA_GUARD}",
             (snapshot.observed_at + WINDOW_SECONDS, attempts,
              attempts * GPU_SECONDS_PER_ATTEMPT, snapshot.observed_at, now)),
        ])
        if results[2].rows_affected != 1:
            raise GenerationUnavailable()

    def reserve(self, dispatch_id: str, tag: str) -> None:
        """Charge ONE attempt before dispatch. Replayed IDs roll the whole batch back.
        Errors or cancellation later never refund the attempt."""
        if not valid_dispatch_id(dispatch_id) or not valid_tag(tag):
            raise GenerationUnavailable()
        now = self._now()
        results = self._run([
            *_expire_unclaimed(now),
            ("UPDATE budget SET attempts_left = attempts_left - 1, "
             f"gpu_seconds_left = gpu_seconds_left - {GPU_SECONDS_PER_ATTEMPT}, "
             "active_job = ?1 WHERE id = 1 AND expires_at > ?2 AND attempts_left > 0 "
             f"AND attempts_left <= ?3 AND gpu_seconds_left >= {GPU_SECONDS_PER_ATTEMPT} "
             f"AND active_job IS NULL AND {_SCHEMA_GUARD}",
             (dispatch_id, now, self.max_attempts)),
            ("INSERT INTO backend_reservations "
             "(id, tag, state, reserved_at, ticket_expires) "
             "SELECT ?1, ?2, 'reserved', ?3, ?4 "
             "WHERE EXISTS (SELECT 1 FROM budget WHERE id = 1 AND active_job = ?1)",
             (dispatch_id, tag, now, now + TICKET_TTL_SECONDS)),
        ])
        if results[2].rows_affected != 1 or results[3].rows_affected != 1:
            raise GenerationUnavailable()

    def claim(self, dispatch_id: str, tag: str) -> None:
        """Space admission: one use only, only for the live active reservation whose
        tag matches, only before the ticket expires."""
        if not valid_dispatch_id(dispatch_id) or not valid_tag(tag):
            raise GenerationUnavailable()
        now = self._now()
        results = self._run([
            ("UPDATE backend_reservations SET state = 'claimed' "
             "WHERE id = ?1 AND tag = ?2 AND state = 'reserved' AND ticket_expires > ?3 "
             "AND EXISTS (SELECT 1 FROM budget WHERE id = 1 AND active_job = ?1)",
             (dispatch_id, tag, now)),
            ("INSERT INTO space_admissions (dispatch_id, admitted_at) "
             "SELECT ?1, ?2 WHERE EXISTS (SELECT 1 FROM backend_reservations "
             "WHERE id = ?1 AND state = 'claimed')", (dispatch_id, now)),
        ])
        if results[0].rows_affected != 1 or results[1].rows_affected != 1:
            raise GenerationUnavailable()

    def finish(self, dispatch_id: str) -> None:
        """Release concurrency only for a claimed dispatch with a valid reply. No refund."""
        if not valid_dispatch_id(dispatch_id):
            raise GenerationUnavailable()
        results = self._run([
            ("UPDATE backend_reservations SET state = 'completed' "
             "WHERE id = ?1 AND state = 'claimed'", (dispatch_id,)),
            ("UPDATE budget SET active_job = NULL WHERE id = 1 AND active_job = ?1 "
             "AND EXISTS (SELECT 1 FROM backend_reservations "
             "WHERE id = ?1 AND state = 'completed')", (dispatch_id,)),
        ])
        if results[0].rows_affected != 1 or results[1].rows_affected != 1:
            raise GenerationUnavailable()

    def close_uncertain(self, dispatch_id: str, *, acknowledged: bool) -> None:
        """Operator-only, after manual review. Frees the job lock; NEVER refunds."""
        if acknowledged is not True or not valid_dispatch_id(dispatch_id):
            raise GenerationUnavailable()
        results = self._run([
            ("UPDATE backend_reservations SET state = 'closed_uncertain' "
             "WHERE id = ?1 AND state IN ('reserved','claimed')", (dispatch_id,)),
            ("UPDATE budget SET active_job = NULL WHERE id = 1 AND active_job = ?1 "
             "AND EXISTS (SELECT 1 FROM backend_reservations "
             "WHERE id = ?1 AND state = 'closed_uncertain')", (dispatch_id,)),
        ])
        if results[0].rows_affected != 1 or results[1].rows_affected != 1:
            raise GenerationUnavailable()
