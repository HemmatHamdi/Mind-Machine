"""Operator tool: create and arm the local quota ledger from numbers YOU read off your
Hugging Face quota page. Not run by the app. It never contacts any network service.

  python init_ledger.py --path /abs/dir/.zerogpu-budget.sqlite3 \
      --gpu-seconds-remaining 300 --runs-remaining 8 \
      --confirm-free-account --confirm-no-paid-usage
"""

import argparse
import os
from pathlib import Path
import sys
import time

from zerogpu import GenerationUnavailable, ManualQuotaSnapshot, QuotaBudget


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--path", required=True)
    parser.add_argument("--gpu-seconds-remaining", type=int, required=True)
    parser.add_argument("--runs-remaining", type=int, required=True)
    parser.add_argument("--confirm-free-account", action="store_true")
    parser.add_argument("--confirm-no-paid-usage", action="store_true")
    args = parser.parse_args(argv)
    path = Path(args.path)
    if not path.is_absolute() or not path.parent.is_dir() or path.is_symlink():
        print("Path must be absolute, in an existing directory, and not a symlink.")
        return 2
    budget = QuotaBudget(path)
    os.chmod(path, 0o600)
    try:
        budget.arm(ManualQuotaSnapshot(
            observed_at=time.time(), gpu_seconds_remaining=args.gpu_seconds_remaining,
            runs_remaining=args.runs_remaining, overquota_used=0,
            personal_free_account_confirmed=args.confirm_free_account,
            paid_usage_disabled_confirmed=args.confirm_no_paid_usage,
        ))
    except GenerationUnavailable:
        print("Not armed: evidence invalid, window still active, or a job is unresolved.")
        return 1
    print("Ledger armed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
