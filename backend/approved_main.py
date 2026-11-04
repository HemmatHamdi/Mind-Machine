"""Future operator-selected entrypoint; NEVER used for default main:app.

Code preparation only. Do not enable execution or arm ledgers before approval.
"""

import os
from pathlib import Path

from main import create_app
from space_transport import PrivateSpaceClient
from zerogpu import QuotaBudget, ZeroGPUAdapter


def build_app():
    if os.getenv("ZEROGPU_EXECUTION_APPROVED") != "true":
        return create_app()
    try:
        path = Path(os.environ["ZEROGPU_BUDGET_PATH"])
        if not path.is_absolute() or not path.is_file() or path.is_symlink():
            return create_app()
        attempts = int(os.getenv("ZEROGPU_MAX_ATTEMPTS", "6"))
        budget = QuotaBudget(path, max_attempts=attempts)
        client = PrivateSpaceClient(
            token=os.environ["HF_TOKEN"],
            backend_key=os.environ["ZEROGPU_BACKEND_KEY"],
            execution_approved=True,
        )
        return create_app(generator=ZeroGPUAdapter(client, budget))
    except Exception:
        return create_app()


app = build_app()
