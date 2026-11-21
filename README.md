# Masari — backend prototype

This branch wires the FastAPI chat endpoint to Google's Gemini 3.5 Flash-Lite
(`gemini-3.5-flash-lite`) behind an explicit opt-in flag. HTTP Basic authentication
and the per-user rate limit remain in place.

**Current scope:** local Arabic/BM25 retrieval, evidence-only prompts and source-ID
checks are implemented. However, the verified Baccalaureate corpus is still
empty: Ministry pages were inaccessible and Gazette PDFs require a copy request.
Only pending source records are included. Until official text is reviewed,
`/chat` returns a clear Arabic referral **without calling Gemini**. This is not
yet a working source-grounded educational demo.

## Run and configure

See [`backend/README.md`](backend/README.md) for setup, secrets, the free-tier
warning, API example, and offline tests. The default `main:app` makes no model
calls. The explicit `approved_main:app` entrypoint requires
`GEMINI_EXECUTION_APPROVED=true` and `GEMINI_API_KEY`.

No Gemini request is made on startup. With reviewed evidence, the adapter makes
at most one request per valid `POST /chat`, with no retry or paid fallback. No
evidence means no model request. Keep Google billing/paid
usage disabled; this code does not enforce the account's tier.

The existing private Hugging Face Space files are still in this repository from
the earlier Qwen experiment; this backend path does not call that Space. Its
deployment and settings are unchanged by this Gemini backend change.
