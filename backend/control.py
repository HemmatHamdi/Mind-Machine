"""Narrow Space-admission control route. Mounted only by the approved entrypoint.

The Space calls this with a purpose-bound proof; it never receives database
credentials. Every refusal is the same content-free 403.
"""

from fastapi import APIRouter, Header
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from dispatch_auth import PROOF_HEADER, verify_claim_proof

CLAIM_PATH = "/internal/zerogpu/claim"


class ClaimRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    dispatch_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    tag: str = Field(pattern=r"^[0-9a-f]{64}$")


def build_control_router(ledger, key) -> APIRouter:
    router = APIRouter()

    def deny():
        return JSONResponse(
            status_code=403, content={"detail": "Not admitted."},
            headers={"Cache-Control": "no-store"},
        )

    @router.post(CLAIM_PATH, include_in_schema=False)
    def claim(
        request: ClaimRequest,
        proof: str = Header(default="", alias=PROOF_HEADER, max_length=64),
    ):
        # Sync handler: runs in the threadpool, so storage I/O never blocks the loop.
        if not verify_claim_proof(key, request.dispatch_id, request.tag, proof):
            return deny()
        try:
            ledger.claim(request.dispatch_id, request.tag)
        except Exception:
            return deny()
        return JSONResponse(
            status_code=200, content={"admitted": True},
            headers={"Cache-Control": "no-store"},
        )

    return router
