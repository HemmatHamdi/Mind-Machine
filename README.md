# Masari — protected Qwen ZeroGPU integration, review only

> Setup, configuration and a `curl` example for the minimal demo: see [`backend/README.md`](backend/README.md).

Production AI generation is **unavailable and not configured**. The default
`main:app` makes no AI calls, requires no AI API key, and has no fallback provider.
This branch prepares the **real private Gradio transport, genuine Qwen ZeroGPU
handler, and persistent quota guards**, tested using fakes only. No Space files
are uploaded, no model is downloaded or loaded, no inference/GPU job is executed,
and no hardware, visibility, billing or token permissions are changed.

**Do not enable execution, arm budgets, deploy this bundle or run a live prompt
without separate approval.** `main:app` remains disabled regardless of optional
configuration. The prepared operator-selected `approved_main:app` also defaults
to disabled and never initializes a network client or model at startup.

The existing FastAPI `POST /chat` endpoint, HTTP Basic authentication, per-user
rate limits, input validation, and privacy protections are retained. No frontend
code is present in this repository or changed here. The unchanged default app
returns HTTP 503. The future approved path preserves `{"message": "..."}` →
`{"reply": "..."}`, HTTP Basic authentication, per-user limits and generic errors.

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

The production API does not fabricate a successful `{ "reply": "..." }` response.
Its default success path remains disabled. Offline tests explicitly inject a fake adapter
through `create_app(generator=...)` to exercise that response contract. The
existing JSON error envelope (`detail`) is preserved. No provider can be enabled
in `main:app` by setting an environment variable, including `HF_TOKEN` or
`ZEROGPU_ENABLED`. Only explicitly selecting the separate operator entrypoint
can use the prepared transport after execution approval and manual arming.

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

The default runtime performs no outbound AI request or credential lookup.
The optional runtime targets only the fixed private Space and has no inference
retry or paid fallback. The old Groq and Gemini runtime
integration/configuration has been removed. Original coursework/planning files
and Git history are retained as historical documents, not executable integrations.

```text
backend/
  main.py                 Unchanged disabled default; authenticated chat factory
  approved_main.py        Separate future opt-in entrypoint, disabled by default
  space_transport.py      Lazy private Gradio client; one submit, header credentials
  security.py             Unchanged authentication and per-user limiter
  zerogpu.py              Offline client contract and persistent quota reservations
  create_chat_user.py      Unchanged private account provisioning helper
  .env.example            Authentication/rate settings only; no credentials
  requirements.txt        Runtime: FastAPI, python-dotenv, Uvicorn
  requirements-dev.txt    Test-only HTTPX and pytest, plus runtime requirements
  requirements-zerogpu.txt Optional future Gradio client, not default dependencies
  tests/
    conftest.py           Fail-on-outbound-network guard for the entire suite
    test_main.py          Unavailability, input, no-key/no-egress regressions
    test_security.py      Authentication, quota, concurrency, enrollment, privacy
    test_zerogpu.py        Fake-client integration, durable budgets and fail-closed jobs
    test_protected_space.py Fake Space/GPU/model; transport and CPU-gate tests
space_app/                 Review-only Space bundle (not uploaded)
```

HTTPX is test-only for default dependencies. The optional Gradio client uses HTTP
for the private Space only. Do not install the GPU/model requirements into the
backend. Space Python is pinned to 3.12.12; backend Python 3.10+ is required.

## Prepared architecture — not deployed or live-tested

The approved future architecture is:

```text
Frontend → HTTPS POST /chat → Basic auth → per-user limit → validation
         → shared quota reservation → private Gradio ZeroGPU Space
         → local Transformers generation → {"reply": "..."}
```

The existing private Space is **not modified** by this PR. The prepared bundle
and client require deployment/access review and separate execution approval.
The fixed model is `Qwen/Qwen2.5-1.5B-Instruct`, pinned to revision
`989aa7980e4cf806f80c7fef2b1adb7bc71aa306`. No weights have been downloaded.
The real production entrypoint never constructs `ZeroGPUAdapter`, creates a
budget database, reads `HF_TOKEN`, or arms a quota window.

Prepared request flow:

```text
POST /chat → existing Basic auth → per-user rate limit → input validation
  → backend SQLite reservation (one active, at most 6 attempts)
  → one private Client.submit("/generate"), HF_TOKEN + backend key in headers
  → Space CPU validator: execution flag, backend key, bounds, Space reservation
  → genuine Gradio-bound @spaces.GPU(duration=30, size="large")
  → lazy Qwen initialization → ≤512 input tokens → ≤128 output tokens
  → validate reply → complete reservations without refund → {"reply": "..."}
```

HF read-token authentication protects the private Space. A separate minimum
32-character `ZEROGPU_BACKEND_KEY` protects the inference operation from other
Space viewers; the CPU validator rejects unauthorized/disabled requests before
GPU scheduling. Hidden controls/API documentation are NOT the security boundary.
`api_open=False` disables the queue-bypassing direct prediction route. No load
events, timers, example caching, readiness inference, warmups or automatic jobs.

The backend uses only `HF_TOKEN`; `HF_WRITE_TOKEN` is never used by runtime code.
The model loader explicitly uses `token=False` for this public model and does
not send backend/HF credentials as model inputs. Tokens and message contents
must not appear in logging; deploy without HTTP header/body debug logging.

The future operator entrypoint requires `ZEROGPU_EXECUTION_APPROVED=true`,
an absolute existing `ZEROGPU_BUDGET_PATH`, `HF_TOKEN`, and
`ZEROGPU_BACKEND_KEY`. The Space independently defaults disabled and requires
`SPACE_EXECUTION_APPROVED=true`, the matching backend key, and its own existing
`SPACE_BUDGET_PATH`. Neither ledger is automatically armed. For a later approved
deployment, an operator must supply fresh manually verified account evidence to
`QuotaBudget.arm(ManualQuotaSnapshot(...))` on each side. No public reset/arming
endpoint is included. The current account quota must be checked again then.

See [Space bundle, exact manifest and prerequisites](space_app/README.md).
Do not upload these files during review.

### Quota policy implemented offline

- A fresh manual snapshot must explicitly confirm a personal Free account,
  disabled paid usage, zero recorded over-quota usage, and both remaining counters.
  These are operator assertions, not an authoritative account/billing check.
- Accept at most the reported Free-tier ceilings of 300 GPU-seconds and 8 runs.
  Reject stale/future/nonfinite snapshots and invalid numeric values.
- Allow **at most six attempts**, leaving **two runs and at least 60 GPU-seconds**
  outside the local allowance. Lower snapshots reduce the allowance further.
- Configurable ceilings `ZEROGPU_MAX_ATTEMPTS` and `SPACE_MAX_ATTEMPTS` accept
  integers 1–6. Lowering a ceiling below an already-armed remaining balance fails
  closed; it does not silently re-arm. Each ledger is shared across users/workers.
- Dispatch IDs are persistently recorded and cannot be replayed after completion.
- Reserve **30 GPU-seconds per attempt**, cap output at **128 new tokens**, and
  permit only one active job. The future Space itself must enforce a 30-second
  GPU duration on default `large` hardware; FastAPI cannot enforce that GPU limit
  just by passing a client argument. The offline timeout is a separate 60-second
  client wait limit, not a measured latency or GPU accounting guarantee.
- SQLite transactions coordinate reservations across ledger instances. The
  ledger stores only counters, expiry, and a random reservation ID: no messages,
  replies, usernames, passwords, HF token, or raw upstream errors.
- Spend the reservation before dispatch. There are no automatic retries, refunds,
  or daily resets. A valid completion releases concurrency, not the spent budget.
- Timeout, cancellation, invalid output, or client failure leaves the job
  quarantined across restarts. Future attempts and re-arming are rejected, even
  after expiry. There is deliberately no automatic recovery or public reset API.
  Investigate and confirm the prior job has stopped before separately designing
  an operator recovery action; do not delete the ledger to work around the guard.
- An ordinary completed window expires 24 hours after its manual observation.
  Expiry only stops requests; it does not prove either HF counter has reset.
  A subsequent arm requires fresh evidence for both counters. Re-arming an
  unexpired window is rejected.

Use a trusted, persistent local directory for a future ledger, not a public or
network filesystem or an ephemeral deployment directory. A newly created ledger
is owner-only (`0600`), rejects a symlink at construction, and starts **unarmed**.
Database errors fail closed. Loss of a ledger does not grant an allowance.
The entire ledger path/directory must be trusted against modification or deletion.

### Limits of the no-paid-usage safeguards

All future requests using one HF token would share that account's allowance.
This local ledger cannot detect usage in other Spaces or account/billing changes.
No automatic billing/quota API reads or broader token permissions are used by
runtime code. Manual snapshots do not provide continuous quota verification.
Do not use the account's quota elsewhere during a controlled demo.

HF documents paid quota extension for PRO/Team/Enterprise accounts, not personal
Free accounts. Remain Free, do not buy credits or change hardware, and do not add
fallback inference. There is no claimed per-request HF "free-only" billing switch.
The local guard is **not a provider billing cap** or a guarantee against an
external account change.

### Remaining approvals and blockers

Before any upload, model download or GPU test:

1. Confirm verified email, good standing, account age over 30 days, a free ZeroGPU
   slot, and availability of private ZeroGPU visibility for the account.
2. Approve uploading this exact bundle to the existing private Space.
3. Verify existing READ-token access to that private Space without inference.
   Do not broaden token permissions silently.
4. Review this PR, provision the separate backend key securely, verify persistent
   ledger storage on both sides, and approve configuration/arming separately.
5. Review HF's processing/retention terms before sending sensitive text. Private
   visibility is access control, not a zero-retention guarantee.
6. Obtain a fresh quota snapshot and explicit approval for **one** live prompt
   through FastAPI. Only that successful end-to-end test can establish live
   integration; fake-client test success cannot.

**Cold-start blocker:** the requested lazy loading happens only inside an
approved GPU call. HF recommends startup loading/CUDA placement instead. Initial
download + load + generation may exceed 30 seconds; lazy loading is not claimed
to be HF's recommended or empirically validated deployment pattern. Timeout
quarantines both ledgers conservatively; no automatic retry or duration increase.
Warm worker reuse/cache persistence and private proxy header forwarding have not
been verified live. Dependency pins require installation validation on the target
Space Python before deployment; tests do not import the actual GPU/model SDKs.

Official references:
[ZeroGPU hosting, GPU duration and quotas](https://huggingface.co/docs/hub/en/spaces-zerogpu),
[Space API authentication and quota attribution](https://huggingface.co/docs/hub/en/spaces-api-endpoints),
[Space visibility](https://huggingface.co/docs/hub/en/spaces-overview),
[quota-read permission](https://huggingface.co/docs/huggingface_hub/main/en/guides/manage-spaces).

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
  unavailable for generation until separately approved live transport/Space work.

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
configuration, enrollment permissions, and credential-free OpenAPI. Offline
ZeroGPU tests additionally cover the fake success contract, shared six-attempt
budget, persistence/reopening, atomic concurrency, fresh manual arming, reserve
margins, expiry, timeout/cancellation quarantine, malformed results, client/database
failures, file permissions, and inability to activate through environment settings.

No live model integration is claimed or tested. The historical inference result
belongs to the removed architecture and is not evidence of current AI capability.
This follow-up is a **new PR based on `feat/provider-free-chat` (PR #3)**.
It does not modify PR #3 or merged PRs #1/#2, and it must not be merged automatically.

### Verified for this change

- **102 tests passed**: the original 56 security/provider-free tests plus 46
  offline integration/budget scenarios.
- `pip check` and `git diff --check` passed. The existing Starlette TestClient
  deprecation warning remains; it does not affect runtime behavior.
- In-memory FastAPI requests cover **401 → fake 200 → 429**, default **503**, and
  unavailable/quarantined generation **503**. All fake calls use synthetic text.
- No live model call, Space, GPU job, billing change, permission change, or
  deployment was performed. No live app preview is provided for this offline stage.
