"""Future operator-selected entrypoint; NEVER used for default main:app.

Code preparation only. Do not enable execution or arm ledgers before approval.
Single worker / single replica only: the per-process chat rate limiter and the
in-flight guard assume it. No automatic POST retries at the ingress.
"""

import os
from pathlib import Path

from main import create_app
from control import build_control_router
from ledger_store import CentralLedger, HranaHttpBackend, SqliteFileBackend
from space_transport import PrivateSpaceClient
from zerogpu import ZeroGPUAdapter


def _backend():
    """Production: libSQL over HTTPS (operator-supplied secrets, after approval).
    LEDGER_LOCAL_PATH selects a validated local file for offline rehearsal only."""
    local = os.environ.get("LEDGER_LOCAL_PATH")
    if local:
        return SqliteFileBackend(Path(local))
    return HranaHttpBackend(
        url=os.environ["LIBSQL_URL"], auth_token=os.environ["LIBSQL_AUTH_TOKEN"],
    )


def build_app():
    if os.getenv("ZEROGPU_EXECUTION_APPROVED") != "true":
        return create_app()
    try:
        key = os.environ["ZEROGPU_BACKEND_KEY"]
        attempts = int(os.getenv("ZEROGPU_MAX_ATTEMPTS", "6"))
        ledger = CentralLedger(_backend(), max_attempts=attempts)
        client = PrivateSpaceClient(token=os.environ["HF_TOKEN"], execution_approved=True)
        adapter = ZeroGPUAdapter(client, ledger, dispatch_key=key)
        return create_app(
            generator=adapter, extra_routers=(build_control_router(ledger, key),),
        )
    except Exception:
        return create_app()


app = build_app()
