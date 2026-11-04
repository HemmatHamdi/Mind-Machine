# Masari chatbot backend — minimal demo setup

A FastAPI `POST /chat` endpoint (HTTP Basic login, per-user rate limit) that calls a
**private Hugging Face ZeroGPU Space** running `Qwen/Qwen2.5-1.5B-Instruct`.
Quota is limited by one local SQLite file: at most 6 generations, one at a time.

> Status: tested **offline with fakes only**. No live response has been produced yet.
> The default `main:app` still returns 503 until you deliberately enable the demo
> entrypoint below.

## How it works
`client → FastAPI (login, rate limit) → local ledger charges 1 attempt → private Space
(checks a signed tag, runs the already-loaded model on a 30 s GPU slot) → reply`.
The shared key is never sent; each request carries a short-lived signed tag.

## Setup
```bash
cd backend
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt          # add requirements-dev.txt to run tests
python create_chat_user.py --username demo   # prompts for a password, writes backend/.env
```

## Configuration (environment / secrets — never commit)
| Name | Where | Purpose |
| --- | --- | --- |
| `CHAT_AUTH_USERS` | backend | set by `create_chat_user.py` |
| `HF_TOKEN` | backend | **read**-scope token for the private Space |
| `ZEROGPU_BACKEND_KEY` | backend **and** Space | random string, 32+ chars |
| `ZEROGPU_EXECUTION_APPROVED=true` | backend | turns the demo entrypoint on |
| `ZEROGPU_BUDGET_PATH` | backend | absolute path of the ledger file |
| `SPACE_MODEL_INIT_APPROVED=true` | Space | load Qwen at Space startup |
| `SPACE_EXECUTION_APPROVED=true` | Space | accept signed requests |

All flags are off by default. Create and arm the ledger once, using the numbers on
your Hugging Face quota page (no network use):
```bash
python init_ledger.py --path /abs/path/.zerogpu-budget.sqlite3 \
  --gpu-seconds-remaining 300 --runs-remaining 8 \
  --confirm-free-account --confirm-no-paid-usage
```
Run **one** process only: `uvicorn approved_main:app --host 0.0.0.0 --port 8000`.

## Try the API
```bash
curl -s -u demo:YOUR_PASSWORD -H 'Content-Type: application/json' \
  -d '{"message": "Say hello in one sentence."}' http://localhost:8000/chat
# -> {"reply": "..."}   (503 = disabled, quota used, or needs operator review)
```
Each request, including failures, spends one of the 6 attempts. A timeout or error
locks further generations until the ledger is reviewed; there is no auto-retry.

## Tests (offline, network blocked)
```bash
pip install -r requirements-dev.txt && python -m pytest tests -q
```
See `space_app/README.md` for the Space bundle and its first-run steps.
