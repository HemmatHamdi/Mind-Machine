"""Minimal server-side Groq integration for the Masari Week 5 deliverable."""

import logging
import os
import re
import time

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator

load_dotenv()

GROQ_CHAT_URL = "https://api.groq.com/openai/v1/chat/completions"
MAX_MESSAGE_LENGTH = 4_000
logger = logging.getLogger(__name__)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=MAX_MESSAGE_LENGTH)

    @field_validator("message")
    @classmethod
    def reject_whitespace_only(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("message must not be empty")
        return value.strip()


def create_app(transport: httpx.AsyncBaseTransport | None = None) -> FastAPI:
    app = FastAPI(
        title="Masari Week 5 AI API",
        description="A minimal backend endpoint that sends a message to Groq.",
        version="1.0.0",
    )
    app.state.groq_transport = transport

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request, exc: RequestValidationError):
        # FastAPI's default response includes the submitted input.
        # Keep validation details useful without echoing user messages.
        return JSONResponse(
            status_code=422,
            content={
                "detail": [
                    {"loc": list(error["loc"]), "msg": error["msg"], "type": error["type"]}
                    for error in exc.errors()
                ]
            },
        )

    @app.post("/chat")
    async def chat(request: ChatRequest) -> dict[str, str]:
        api_key = os.getenv("GROQ_API_KEY", "").strip()
        model = os.getenv("GROQ_MODEL", "").strip()
        timeout_text = os.getenv("GROQ_TIMEOUT_SECONDS", "30")
        max_tokens_text = os.getenv("GROQ_MAX_COMPLETION_TOKENS", "512")

        if not api_key or not model:
            raise HTTPException(
                status_code=503,
                detail="AI service is not configured. Set GROQ_API_KEY and GROQ_MODEL.",
            )
        # This is an operator acknowledgement, not a billing-status API check.
        # Never send inference until the account's Free plan has been confirmed.
        if os.getenv("GROQ_FREE_PLAN_CONFIRMED", "").strip().lower() != "true":
            raise HTTPException(
                status_code=503,
                detail="AI service is disabled until the administrator confirms the Groq Free plan.",
            )
        if len(model) > 200 or not re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9._-]*(?:/[A-Za-z0-9][A-Za-z0-9._-]*)?", model
        ):
            raise HTTPException(
                status_code=503,
                detail="GROQ_MODEL must be a model ID, not a URL or routing policy.",
            )
        try:
            timeout_seconds = float(timeout_text)
            if not 1 <= timeout_seconds <= 120:
                raise ValueError
        except ValueError:
            raise HTTPException(
                status_code=503,
                detail="GROQ_TIMEOUT_SECONDS must be between 1 and 120.",
            ) from None
        try:
            max_tokens = int(max_tokens_text)
            if not 1 <= max_tokens <= 1_024:
                raise ValueError
        except ValueError:
            raise HTTPException(
                status_code=503,
                detail="GROQ_MAX_COMPLETION_TOKENS must be an integer between 1 and 1024.",
            ) from None

        payload = {
            "model": model,
            "messages": [{"role": "user", "content": request.message}],
            "max_completion_tokens": max_tokens,
            "stream": False,
        }
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

        started = time.monotonic()
        try:
            # HTTPX does not retry by default. Do not follow redirects carrying
            # credentials, select another provider, or request paid flex tiers.
            async with httpx.AsyncClient(
                timeout=timeout_seconds,
                transport=app.state.groq_transport,
                follow_redirects=False,
            ) as client:
                response = await client.post(GROQ_CHAT_URL, json=payload, headers=headers)
        except httpx.TimeoutException:
            logger.warning("Groq timeout elapsed_seconds=%.3f", time.monotonic() - started)
            raise HTTPException(
                status_code=504,
                detail="The AI service timed out. No automatic retry was made.",
            ) from None
        except httpx.RequestError:
            logger.warning("Groq network failure elapsed_seconds=%.3f", time.monotonic() - started)
            raise HTTPException(
                status_code=502,
                detail="The AI service could not be reached. No automatic retry was made.",
            ) from None

        # Retain useful status/timing diagnostics, never headers, bodies, or
        # exception strings (which could contain credentials or prompt text).
        logger.info(
            "Groq response status=%d elapsed_seconds=%.3f",
            response.status_code,
            time.monotonic() - started,
        )
        if response.status_code in (401, 403):
            raise HTTPException(
                status_code=503,
                detail="AI service authentication or access failed. Contact the administrator.",
            )
        if response.status_code == 402:
            raise HTTPException(
                status_code=503,
                detail="AI service free allowance is unavailable. Paid fallback is disabled.",
            )
        if response.status_code == 429:
            raise HTTPException(
                status_code=429,
                detail="AI service rate or free usage limit reached. Please try again later.",
            )
        if response.status_code == 404:
            raise HTTPException(
                status_code=503,
                detail="The configured AI model is unavailable. Contact the administrator.",
            )
        if response.status_code == 503:
            raise HTTPException(
                status_code=503,
                detail="The AI provider is temporarily unavailable. Please try again later.",
            )
        if response.status_code != 200:
            raise HTTPException(
                status_code=502,
                detail="The AI service rejected the request or returned an error.",
            )

        try:
            body = response.json()
            choice = body["choices"][0]
            content = choice["message"]["content"]
            reply = content.strip() if isinstance(content, str) else ""
            if choice.get("finish_reason") != "stop":
                reply = ""
        except (ValueError, IndexError, KeyError, TypeError, AttributeError):
            reply = ""

        if not reply:
            raise HTTPException(
                status_code=502,
                detail="The AI service did not return a complete text reply.",
            )

        return {"reply": reply}

    return app


app = create_app()
