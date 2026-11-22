# Masari — Week 5: First Model Call From Our Backend

## What this package does
- `GET /` serves a minimal demo chat UI (same-origin).
- `GET /health` verifies the backend is reachable without contacting Groq.
- `POST /chat` accepts `{ "message": "..." }`, verifies HTTP Basic authentication, sends an HTTPS request to Groq, and returns `{ "reply": "..." }`.
- The Groq API key stays on the server, not in browser JavaScript.
- This backend is a first-call demonstration; it does not yet implement the project's complete specialized features, grounding, fallback or human handover.

## Set up in Replit
1. Put all files together in your backend project folder. Keep `.env` private; do **not** publish it or your secrets.
2. In Replit Secrets (environment variables), set `GROQ_API_KEY` to your real Groq API key and `GROQ_MODEL` to a valid model ID available to your account (e.g. `openai/gpt-oss-20b` if available).
3. Confirm the Groq organization is on the Free plan in the Groq Console, then and only then set `GROQ_FREE_PLAN_CONFIRMED=true`. No paid fallback is used.
4. Create a local user: `python create_chat_user.py --username demo`. The script prompts for a password and adds a salted hash into `.env`. **Note:** on hosted Replit, make sure the generated `CHAT_AUTH_USERS` environment variable is actually loaded by the running server; a local `.env` file in the same directory as `main.py` is sufficient when launched from that directory. Never share the password or hash.
5. Install dependencies: `pip install -r requirements.txt`.
6. Run from the folder containing `main.py`: `uvicorn main:app --host 0.0.0.0 --port 8000` (or change the port to your Replit deployment configuration).
7. Open the Replit web preview at `/`. Enter your demo username/password, type a message, click Send. The reply must appear in the page from `POST /chat`.
8. Screen-record: Replit server running, the chat UI sending a message, the generated reply, and the browser DevTools Network response to `/chat` showing `{ "reply": ... }`. **Do not show secrets or auth headers in the recording.**

## Troubleshooting — inspect POST /chat status in browser Network tab
- 401: wrong or missing demo credentials; run `create_chat_user.py` and restart server so `CHAT_AUTH_USERS` is loaded.
- 422: request body is not `{ "message": "nonempty text" }`.
- 503 `Chat security is not configured`: `CHAT_AUTH_USERS` missing/invalid at app startup.
- 503 `Set GROQ_API_KEY and GROQ_MODEL`: configure both server-side.
- 503 Free plan confirmation: check account tier, then set `GROQ_FREE_PLAN_CONFIRMED=true`.
- 503 AI service authentication/access: invalid API key or access denied.
- 503 configured AI model unavailable: select a currently supported model ID.
- 429: local request rate limit or provider quota reached (detail differentiates).
- 502/504: provider response/network error/timeout; see sanitized server logs.
- Browser cross-origin error: use the included `GET /` demo served by FastAPI from the same origin. For a separate frontend, configure explicit CORS origins; do not expose API keys.

## Offline automated tests (not a real Groq call)
`pytest -q test_backend.py`

## Check-in scope
Successful live demonstration requires a **real key and a network connection**, which are intentionally not provided in this package. A mocked test passing alone is not sufficient for the assignment. Capture a live reply in Replit for Point 4.
