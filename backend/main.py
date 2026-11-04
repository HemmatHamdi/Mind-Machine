"""Provider-free chat API: retain access controls, disable AI generation."""

import time
from collections.abc import Callable

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator

from security import ChatSecurity

load_dotenv()

MAX_MESSAGE_LENGTH = 4_000
AI_UNAVAILABLE_MESSAGE = (
    "AI generation is currently unavailable because no AI service is configured."
)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=MAX_MESSAGE_LENGTH)

    @field_validator("message")
    @classmethod
    def reject_whitespace_only(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("message must not be empty")
        return value.strip()


def create_app(*, clock: Callable[[], float] = time.monotonic) -> FastAPI:
    app = FastAPI(
        title="Masari Chat API",
        description=(
            "Provider-free chat endpoint. Authentication and per-user limits remain "
            "active; AI generation is unavailable and not configured."
        ),
        version="1.0.0",
    )
    security = ChatSecurity(clock=clock)

    @app.middleware("http")
    async def protect_chat(request, call_next):
        # Authenticate and reserve a per-user slot before parsing the body,
        # including malformed JSON. Never trust a client-supplied user/IP header.
        path = request.scope["path"]
        root_path = request.scope.get("root_path", "").rstrip("/")
        if root_path and path.startswith(root_path + "/"):
            path = path[len(root_path):]
        if request.method == "POST" and path.rstrip("/") == "/chat":
            try:
                await security.check_request(request)
            except HTTPException as exc:
                return JSONResponse(
                    status_code=exc.status_code,
                    content={"detail": exc.detail},
                    headers={**(exc.headers or {}), "Cache-Control": "no-store"},
                )
            response = await call_next(request)
            response.headers["Cache-Control"] = "no-store"
            return response
        return await call_next(request)

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request, exc: RequestValidationError):
        # Never echo submitted message text in validation responses.
        return JSONResponse(
            status_code=422,
            content={
                "detail": [
                    {"loc": list(error["loc"]), "msg": error["msg"], "type": error["type"]}
                    for error in exc.errors()
                ]
            },
        )

    # Preserve route-level defense in depth and HTTP Basic documentation.
    # Request state prevents a second password check or quota reservation.
    @app.post(
        "/chat",
        dependencies=[Depends(security.scheme), Depends(security.check_request)],
        responses={
            401: {"description": "Invalid or missing credentials."},
            429: {"description": "Per-user request limit reached. See Retry-After."},
            503: {"description": AI_UNAVAILABLE_MESSAGE},
        },
    )
    async def chat(request: ChatRequest) -> dict[str, str]:
        # Deliberately no provider, network client, credential lookup, or fallback.
        # Keep the existing JSON error envelope instead of fabricating a reply.
        raise HTTPException(status_code=503, detail=AI_UNAVAILABLE_MESSAGE)

    return app


app = create_app()
