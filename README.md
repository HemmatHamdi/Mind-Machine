# Masari — provider-free chat backend

AI generation is **unavailable and not configured**. This backend makes no AI
provider calls, requires no AI API key, and has no fallback provider or model.
It does not use Replit-managed model access, subscribe to a service, or change billing.

The existing FastAPI `POST /chat` endpoint, HTTP Basic authentication, per-user
rate limits, input validation, and privacy protections are retained. No frontend
code is present in this repository or changed here. Clients can keep sending the
same JSON request but must handle the deliberate HTTP 503 response.

## API behavior

Send `{ "message": "..." }` with the user's own HTTP Basic credentials.
The message must be a non-whitespace string of 1–4,000 characters; surrounding
whitespace is trimmed. Authentication and quota reservation happen before body
parsing, including behind a configured proxy root path or mounted app.

For an authenticated, within-limit request with valid input:

```http
HTTP/1.1 503 Service Unavailable
Content-Type: application/json
Cache-Control: no-store
```

```json
{
  "detail": "AI generation is currently unavailable because no AI service is configured."
}
```

The API does not fabricate a successful `{ "reply": "..." }` response. That former
success path is disabled. The existing JSON error envelope (`detail`) is preserved.
No new provider can be enabled by setting an environment variable.

| Condition | Response |
| --- | --- |
| Missing, incorrect, unknown, or malformed HTTP Basic credentials | 401 with `WWW-Authenticate: Basic` |
| Authenticated user's local quota exceeded | 429 with numeric `Retry-After` seconds |
| Authenticated invalid input or malformed JSON | 422 without echoing submitted input |
| Authenticated, valid, within-limit chat | 503 with the AI-unavailable message above |
| Missing/invalid authentication or rate-limit configuration | 503 with a generic security-configuration message; fail closed |

Chat responses have `Cache-Control: no-store`. Passwords, password hashes,
Authorization headers, and message text must never be logged. Validation error
details exclude input/context values. The application does not store chat history.

## Architecture and dependencies

```text
POST /chat → authenticate → reserve per-user quota → validate input
           → HTTP 503: AI generation unavailable
```

There is no outbound AI request, HTTP client, model selection, provider credential
lookup, retry, or paid fallback in runtime code. The old Groq and Gemini runtime
integration/configuration has been removed. Original coursework/planning files
and Git history are retained as historical documents, not executable integrations.

```text
backend/
  main.py                 Provider-free endpoint and sanitized validation
  security.py             Unchanged authentication and per-user limiter
  create_chat_user.py      Unchanged private account provisioning helper
  .env.example            Authentication/rate settings only; no credentials
  requirements.txt        Runtime: FastAPI, python-dotenv, Uvicorn
  requirements-dev.txt    Test-only HTTPX and pytest, plus runtime requirements
  tests/
    conftest.py           Fail-on-outbound-network guard for the entire suite
    test_main.py          Unavailability, input, no-key/no-egress regressions
    test_security.py      Authentication, quota, concurrency, enrollment, privacy
```

HTTPX is test-only for the in-memory FastAPI TestClient; it is not a runtime
dependency or an AI integration. Python 3.10+ is required.

## Setup and account provisioning

From `backend/`:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
.venv/bin/python create_chat_user.py --username your-user
```

The helper prompts privately for a password and confirmation. It writes a salted
hash into the untracked `backend/.env`, with owner-only permissions (`0600`),
without printing passwords or hashes. No default account/password is shipped.

Passwords must contain 12–256 ASCII characters; prefer a unique random password
of at least 16 characters. Usernames are case-sensitive and contain 1–64 ASCII
letters, digits, underscores, dots, or hyphens. Password hashes use PBKDF2-SHA256
with 600,000 iterations and independent random 16-byte salts. Digest comparison
is constant-time; unknown usernames still perform a real hash check. Hashing
runs in a thread pool instead of blocking the event loop.

## Configuration

| Setting | Default | Purpose |
| --- | --- | --- |
| `CHAT_AUTH_USERS` | Required; no default | Secret JSON map of usernames to salted password hashes |
| `CHAT_RATE_LIMIT_REQUESTS` | `10` | Per-user attempts per rolling window; integer 1–10,000 |
| `CHAT_RATE_LIMIT_WINDOW_SECONDS` | `60` | Window duration; integer 1–86,400 seconds |

These are the only runtime environment settings read by the application.
No provider API key, model ID, timeout, free-plan acknowledgement, or billing flag
is required. Leftover `GROQ_*` or `GEMINI_*` settings are ignored and cannot enable
AI generation. Remove obsolete provider settings from your own deployment
configuration; this PR does not delete workspace secrets or revoke external keys.

For deployment, transfer the account-hash setting directly into the hosting
platform's secure Secrets interface—not source code, screenshots, or chat.
Environment settings take precedence over `.env`. Settings are loaded when the
application is created; restart after changing accounts or limits.

Rerun the helper to rotate a password. To revoke a user, remove their JSON entry.
Update the deployment secret as applicable and restart. Run the helper with one
operator at a time. Keep password hashes private, even though they are not plaintext.

## Run and exercise the endpoint

```bash
cd backend
source .venv/bin/activate
uvicorn main:app --host 127.0.0.1 --port 8000 --workers 1
```

In another terminal:

```bash
curl -i --user your-user http://127.0.0.1:8000/chat \
  -H 'Content-Type: application/json' \
  -d '{"message":"Hello"}'
```

`curl --user your-user` prompts privately; do not put real passwords in arguments
or URLs. The expected authenticated response is **503**, not a generated reply.
Without credentials it is **401**. After consuming the user's request allowance,
it is **429** with `Retry-After`. The local HTTP address is for loopback development
only; **HTTPS is mandatory for remote access**.

Swagger is available at `/docs`, and the schema at `/openapi.json`. Use Swagger's
Authorize control with a local user's credentials, never an AI provider key.
The docs explicitly describe AI unavailability. There is no persistent public
test server or newly provisioned real user from this change.

## Rate limits and deployment limitations

- Verified usernames define independent quotas; identity/IP headers and request
  bodies cannot choose the quota identity.
- Authenticated requests reserve a slot before validation. Invalid inputs and
  deliberate 503 responses count. Failed logins do not consume another user's
  quota. Rejected 429 attempts do not extend the window.
- `Retry-After` is rounded up to the seconds until the oldest slot expires
  (minimum 1). A monotonic clock and a lock enforce atomic reservations.
- Counters are in memory, reset on restart, and are not shared across workers or
  instances. Use one process until coordinated storage/ingress limits are added.
- HTTP Basic is encoding, not encryption. Use a correctly configured HTTPS
  hosting endpoint/reverse proxy. Protect login attempts, request/header/body
  sizes, and concurrency at ingress. Failed-login floods can consume hashing CPU.
- There is no session logout, self-service account management, or MFA.
  `/docs` and `/openapi.json` remain public but contain no configured secrets.
- Neither local use nor deployment enables AI. `/chat` remains deliberately
  unavailable for generation until a separately authorized implementation exists.

## Tests and verification

```bash
cd backend
source .venv/bin/activate
pip install -r requirements-dev.txt
python -m pytest -q
python -m pip check
```

The previous provider success/error/timeout/model tests are obsolete and replaced
by provider-free regressions. All authentication/rate-limit security scenarios
are retained and adapted to expect the deliberate 503 instead of model output.

The entire suite blocks outbound socket/DNS connections and external HTTPX
requests; only in-memory TestClient dispatch is allowed. It records only attempt
counts and fails even if application code catches the blocking exception.
Tests cover absent and leftover provider settings, no outbound calls, sanitized
responses/logs, input validation, auth rejection, independent quotas, window
expiry, concurrency, spoofed identity headers, proxy/mounted paths, fail-closed
configuration, enrollment permissions, and credential-free OpenAPI.

No live model integration is claimed or tested. The historical inference result
belongs to the removed architecture and is not evidence of current AI capability.
This follow-up belongs in a new PR from `main`; merged PRs #1 and #2 are unchanged.

### Verified for this change

- **56 tests passed**: all 40 security scenarios plus 16 provider-free regressions.
- `pip check` and `git diff --check` passed. The existing Starlette TestClient
  deprecation warning remains; it does not affect runtime behavior.
- A short-lived actual Uvicorn HTTP server, with no provider configured, returned
  **401 → 503 → 429** for missing credentials, valid credentials, and a subsequent
  request at a one-request test limit. `Retry-After` was `60`; all chat responses
  used `no-store`. No non-loopback connection attempt occurred.
- Smoke credentials existed only in memory and were not printed. The server was
  stopped after verification. No real model call, billing change, or deployment
  was performed.
