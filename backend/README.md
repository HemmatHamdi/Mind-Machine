# Masari backend — Gemini API

FastAPI `POST /chat` keeps HTTP Basic authentication and a per-user, in-process
rate limit. Its opt-in model adapter calls Google's **Gemini 3.5 Flash-Lite**
(`gemini-3.5-flash-lite`) once per request.

**Important:** this is a model connection, not a Baccalaureate knowledge system.
No verified-source retrieval is implemented yet. The adapter instructs Gemini not
to present current rules or pathways as verified facts and to refer users to an
official source or school counselor. Do not use real student or personal data.

## Setup

```bash
cd backend
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python create_chat_user.py --username demo
```

## Configuration

Set these in the backend runtime's secrets/configuration; never commit `.env`:

| Name | Required value | Purpose |
| --- | --- | --- |
| `CHAT_AUTH_USERS` | Created by `create_chat_user.py` | HTTP Basic accounts |
| `GEMINI_API_KEY` | Key for a Google AI Studio **Free Tier** project | Authenticates Gemini API requests |
| `GEMINI_EXECUTION_APPROVED` | Keep unset/`false` until a separately approved live test | Explicitly enables model calls |
| `CHAT_RATE_LIMIT_REQUESTS` | Optional; default `10` | Per-user request limit |
| `CHAT_RATE_LIMIT_WINDOW_SECONDS` | Optional; default `60` | Rate-limit window |

Use a Free Tier project with billing/paid usage disabled. This code does not detect
the Google project tier or prevent paid usage if the key is attached to a billed
project. Google may use Free Tier prompts and responses to improve its products;
`store=False` disables interaction-history storage but does not change that Free
Tier data-use policy. Keep tests fictional and do not send personal information.
The model's availability and quotas depend on Google's current account limits.

The default `main:app` remains disabled. After separate approval for a live model
request, enable `GEMINI_EXECUTION_APPROVED=true` and run one process:

```bash
uvicorn approved_main:app --host 0.0.0.0 --port 8000
```

The adapter makes one model request, without retry or paid fallback. No request is
made at startup.

## Test the API

```bash
curl -s -u demo:YOUR_PASSWORD \
  -H 'Content-Type: application/json' \
  -d '{"message":"ما هي مسارات البكالوريا المصرية؟"}' \
  http://localhost:8000/chat
```

With the execution flag off, the endpoint returns `503`. With it on, a valid
authenticated request returns `{"reply":"..."}`. Until verified-source retrieval
is added, the system instruction asks the model to say it cannot verify current
Baccalaureate facts; this response is not yet a source-grounded answer.

## Offline tests

```bash
pip install -r requirements-dev.txt
python -m pytest tests -q
```

Tests use fake Gemini responses and blocked outbound networking. They verify
request wiring only; they do not prove the real API key, model access, free-tier
status, quota, or a live response.

Official references:
- [Gemini 3.5 Flash-Lite model](https://ai.google.dev/gemini-api/docs/models/gemini-3.5-flash-lite)
- [Gemini API getting started](https://ai.google.dev/gemini-api/docs/quickstart)
- [Gemini API pricing and Free Tier terms](https://ai.google.dev/gemini-api/docs/pricing?model=gemini-3.5-flash-lite)
