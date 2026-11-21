# Masari — backend prototype

This branch wires the FastAPI chat endpoint to Google's Gemini 3.5 Flash-Lite
(`gemini-3.5-flash-lite`) behind an explicit opt-in flag. HTTP Basic authentication
and the per-user rate limit remain in place.

**Current scope:** one user message is sent to the model and one reply is returned.
There is not yet a Baccalaureate knowledge base or source retrieval, so this is
not yet a grounded Masari guide. The system instruction tells the model not to
present current rules or pathways as verified facts.

## Run and configure

See [`backend/README.md`](backend/README.md) for setup, secrets, the free-tier
warning, API example, and offline tests. The default `main:app` makes no model
calls. The explicit `approved_main:app` entrypoint requires
`GEMINI_EXECUTION_APPROVED=true` and `GEMINI_API_KEY`.

No Gemini request is made on startup. The adapter makes one request per valid
`POST /chat`, with no automatic retry or paid fallback. Keep Google billing/paid
usage disabled; this code does not enforce the account's tier.

The existing private Hugging Face Space files are still in this repository from
the earlier Qwen experiment; this backend path does not call that Space. Its
deployment and settings are unchanged by this Gemini backend change.
