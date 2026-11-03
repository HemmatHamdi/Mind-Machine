"""Minimal server-side Gemini integration for the Masari Week 5 deliverable."""

import os
import re

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, field_validator

load_dotenv()

GEMINI_API_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"
MAX_MESSAGE_LENGTH = 4_000


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
        description="A minimal backend endpoint that sends a message to Gemini.",
        version="1.0.0",
    )
    app.state.gemini_transport = transport

    @app.post("/chat")
    async def chat(request: ChatRequest) -> dict[str, str]:
        api_key = os.getenv("GEMINI_API_KEY", "").strip()
        model = os.getenv("GEMINI_MODEL", "").strip()
        timeout_text = os.getenv("GEMINI_TIMEOUT_SECONDS", "20")

        if not api_key or not model:
            raise HTTPException(
                status_code=503,
                detail="AI service is not configured. Set GEMINI_API_KEY and GEMINI_MODEL.",
            )
        if not re.fullmatch(r"[A-Za-z0-9._-]+", model):
            raise HTTPException(
                status_code=503,
                detail="GEMINI_MODEL must be a model ID, not a URL or path.",
            )
        try:
            timeout_seconds = float(timeout_text)
            if not 1 <= timeout_seconds <= 120:
                raise ValueError
        except ValueError:
            raise HTTPException(
                status_code=503,
                detail="GEMINI_TIMEOUT_SECONDS must be between 1 and 120.",
            ) from None

        url = f"{GEMINI_API_BASE_URL}/{model}:generateContent"
        payload = {"contents": [{"parts": [{"text": request.message}]}]}
        headers = {"x-goog-api-key": api_key, "Content-Type": "application/json"}

        try:
            async with httpx.AsyncClient(
                timeout=timeout_seconds,
                transport=app.state.gemini_transport,
            ) as client:
                response = await client.post(url, json=payload, headers=headers)
        except httpx.TimeoutException:
            raise HTTPException(
                status_code=504,
                detail="The AI service timed out. Please try again.",
            ) from None
        except httpx.RequestError:
            raise HTTPException(
                status_code=502,
                detail="The AI service could not be reached. Please try again.",
            ) from None

        if response.is_error:
            raise HTTPException(
                status_code=502,
                detail="The AI service returned an error. Please try again later.",
            )

        try:
            body = response.json()
            candidates = body.get("candidates", [])
            parts = candidates[0]["content"]["parts"]
            reply = "".join(
                part["text"] for part in parts if isinstance(part.get("text"), str)
            ).strip()
        except (ValueError, IndexError, KeyError, TypeError, AttributeError):
            reply = ""

        if not reply:
            raise HTTPException(
                status_code=502,
                detail="The AI service returned an unexpected response. Please try again.",
            )

        return {"reply": reply}

    return app


app = create_app()
