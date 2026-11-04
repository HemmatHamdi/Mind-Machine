"""Stdlib-only signed dispatch shared by the backend and the Space bundle.

The shared secret (ZEROGPU_BACKEND_KEY) is never sent. Each request carries an ID,
an issue time and an HMAC tag binding ID, time, token limit and message. The Space
verifies the tag locally; the tag expires after TICKET_TTL_SECONDS. Importing this
module performs no I/O.
"""

from dataclasses import dataclass
import hashlib
import hmac
import re

TICKET_TTL_SECONDS = 90
MAX_CLOCK_SKEW_SECONDS = 5
ID_HEADER = "X-MM-Dispatch-ID"
TIME_HEADER = "X-MM-Dispatch-Time"
TAG_HEADER = "X-MM-Dispatch-Tag"
_HEX32 = re.compile(r"[0-9a-f]{32}")
_HEX64 = re.compile(r"[0-9a-f]{64}")


class AuthError(Exception):
    """Content-free; never carries keys or message text."""


@dataclass(frozen=True)
class Dispatch:
    id: str
    issued_at: int
    tag: str


def valid_dispatch_id(value) -> bool:
    return isinstance(value, str) and _HEX32.fullmatch(value) is not None


def sign_dispatch(key, dispatch_id: str, issued_at: int, max_new_tokens: int,
                  message: str) -> str:
    raw = key.encode() if isinstance(key, str) else key
    if (
        not isinstance(raw, bytes) or len(raw) < 32 or not valid_dispatch_id(dispatch_id)
        or type(issued_at) is not int or not isinstance(message, str)
    ):
        raise AuthError()
    fields = (dispatch_id.encode(), str(issued_at).encode(),
              str(int(max_new_tokens)).encode(), message.encode())
    data = b"mm-dispatch-v1\0" + b"".join(len(f).to_bytes(4, "big") + f for f in fields)
    return hmac.new(raw, data, hashlib.sha256).hexdigest()


def verify_dispatch(key, dispatch_id, issued_at, max_new_tokens, message, tag,
                    now: float) -> bool:
    """False (never raises) for any malformed, expired, future or forged dispatch."""
    try:
        if (
            not valid_dispatch_id(dispatch_id) or type(issued_at) is not int
            or not isinstance(tag, str) or _HEX64.fullmatch(tag) is None
            or not -MAX_CLOCK_SKEW_SECONDS <= now - issued_at <= TICKET_TTL_SECONDS
        ):
            return False
        expected = sign_dispatch(key, dispatch_id, issued_at, max_new_tokens, message)
        return hmac.compare_digest(expected.encode(), tag.encode())
    except Exception:
        return False
