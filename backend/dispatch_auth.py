"""Stdlib-only dispatch authentication shared by the backend and the Space bundle.

Offline code only. Importing this module performs no I/O. The root secret is the
existing ZEROGPU_BACKEND_KEY; it is never sent over the network. Each derived value
uses its own domain-separated purpose, so a dispatch tag cannot be replayed as a
claim proof. The tag binds the dispatch ID, issue time, token limit and message,
but is stored by the ledger only as an opaque keyed tag (never the message).
"""

from dataclasses import dataclass
import hashlib
import hmac
import json
import re
import urllib.error
import urllib.request

TICKET_TTL_SECONDS = 90
MAX_CLOCK_SKEW_SECONDS = 5
ID_HEADER = "X-MM-Dispatch-ID"
TIME_HEADER = "X-MM-Dispatch-Time"
TAG_HEADER = "X-MM-Dispatch-Tag"
PROOF_HEADER = "X-MM-Claim-Proof"
_HEX32 = re.compile(r"[0-9a-f]{32}")
_HEX64 = re.compile(r"[0-9a-f]{64}")


class AdmissionError(Exception):
    """Content-free failure; never carries credentials, messages or upstream text."""


@dataclass(frozen=True)
class Dispatch:
    id: str
    issued_at: int
    tag: str


def valid_dispatch_id(value) -> bool:
    return isinstance(value, str) and _HEX32.fullmatch(value) is not None


def valid_tag(value) -> bool:
    return isinstance(value, str) and _HEX64.fullmatch(value) is not None


def _key_bytes(key) -> bytes:
    raw = key.encode() if isinstance(key, str) else key
    if not isinstance(raw, bytes) or len(raw) < 32:
        raise AdmissionError()
    return raw


def _mac(key, purpose: bytes, *parts: bytes) -> str:
    # Length-prefixed framing: no ambiguity between adjacent fields.
    data = purpose + b"".join(len(p).to_bytes(4, "big") + p for p in parts)
    return hmac.new(_key_bytes(key), data, hashlib.sha256).hexdigest()


def sign_dispatch(key, dispatch_id: str, issued_at: int, max_new_tokens: int,
                  message: str) -> str:
    if not valid_dispatch_id(dispatch_id) or type(issued_at) is not int:
        raise AdmissionError()
    return _mac(
        key, b"mm-dispatch-v2\0", dispatch_id.encode(), str(issued_at).encode(),
        str(int(max_new_tokens)).encode(), message.encode(),
    )


def verify_dispatch(key, dispatch_id, issued_at, max_new_tokens, message, tag,
                    now: float) -> bool:
    """Return False (never raise) for any malformed, expired or forged dispatch."""
    try:
        if (
            not valid_dispatch_id(dispatch_id) or not valid_tag(tag)
            or type(issued_at) is not int
            or not -MAX_CLOCK_SKEW_SECONDS <= now - issued_at <= TICKET_TTL_SECONDS
        ):
            return False
        expected = sign_dispatch(key, dispatch_id, issued_at, max_new_tokens, message)
        return hmac.compare_digest(expected.encode(), tag.encode())
    except Exception:
        return False


def claim_proof(key, dispatch_id: str, tag: str) -> str:
    if not valid_dispatch_id(dispatch_id) or not valid_tag(tag):
        raise AdmissionError()
    return _mac(key, b"mm-claim-v2\0", dispatch_id.encode(), tag.encode())


def verify_claim_proof(key, dispatch_id, tag, proof) -> bool:
    try:
        if not valid_tag(proof):
            return False
        return hmac.compare_digest(
            claim_proof(key, dispatch_id, tag).encode(), proof.encode()
        )
    except Exception:
        return False


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def _https_post(url: str, headers: dict, body: bytes, timeout: float) -> int:
    opener = urllib.request.build_opener(_NoRedirect)
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with opener.open(request, timeout=timeout) as response:
            return response.status
    except urllib.error.HTTPError as error:
        return error.code


def claim_admission(control_url: str, key, dispatch_id: str, tag: str, *,
                    post=_https_post, timeout: float = 10.0) -> None:
    """Space-side: one POST to the backend control endpoint, no retries.

    Raises AdmissionError unless the backend answers 200. The Space holds no
    database credential; the backend ledger decides whether to admit.
    """
    if not isinstance(control_url, str) or not control_url.startswith("https://"):
        raise AdmissionError()
    try:
        status = post(
            control_url,
            {"Content-Type": "application/json",
             PROOF_HEADER: claim_proof(key, dispatch_id, tag)},
            json.dumps({"dispatch_id": dispatch_id, "tag": tag}).encode(),
            timeout,
        )
    except Exception:
        raise AdmissionError() from None
    if status != 200:
        raise AdmissionError()
