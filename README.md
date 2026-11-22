# Masari — Egyptian Baccalaureate chatbot demo

Masari is a student project for helping students and families understand the
Egyptian Baccalaureate. The current implementation is a **local, API-first
prototype**, not a complete educational adviser or a deployed production service.

## What works now

- FastAPI `POST /chat`: `{"message":"..."}` → `{"reply":"..."}`.
- HTTP Basic authentication and single-process per-user rate limiting.
- Local Arabic keyword/BM25 retrieval over **seven reviewed FAQ summaries**.
- Gemini **3.5 Flash-Lite** (`gemini-3.5-flash-lite`) receives the question and
  matching evidence, with a 512-token output cap and no automatic retry/fallback.
- Replies require retrieved source IDs; the backend adds source links, review
  dates and a visible attribution notice.
- Missing evidence returns an Arabic referral without calling the model.

The active source is a Maspero / National Media Authority report dated
12 November 2026, attributing its FAQs to the Ministry of Education. This is a
reviewed media report, **not a reviewed original Ministry decree**. Topics cover
financial culture assessment, second-language restrictions, guidance meetings,
exam Arabization, attendance, projects and transfer after failing second-year
General Secondary. Original Ministry/Gazette records remain pending and excluded.

## Current request flow

`/chat → authentication + rate limit → local FAQ retrieval → Gemini → citation
check → answer with source notice/link`

There is no vector database, Turso, model-weight download, local inference,
Hugging Face/ZeroGPU request path or automatic paid fallback.

## Setup and API testing

The only supported runtime is [`backend/`](backend/README.md):

```bash
cd backend
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python create_chat_user.py --username demo
```

Keep the generated `.env` private. Configure `GEMINI_API_KEY` using a runtime
secrets manager or untracked `.env`; never put it in source code or browser code.
Use a Google AI Studio Free Tier project with billing disabled. The application
does not verify or enforce Google's account billing tier.

By default, model execution is disabled. Only after explicitly approving live
usage, enable `GEMINI_EXECUTION_APPROVED=true` in the runtime and start:

```bash
uvicorn approved_main:app --host 127.0.0.1 --port 8000 --workers 1
```

Do not start multiple workers: limits are held in process memory. Starting the
server does not itself send a model request. `uvicorn main:app` always leaves
generation disabled. Interactive API documentation is at `/docs`; no current
integrated chat UI is served.

After approving a live request, this curl prompts for the demo account password
without including it in the command:

```bash
curl -sS -u demo \
  -H 'Content-Type: application/json' \
  -d '{"message":"متى لقاءات المرشد التعليمي في أولى ثانوي؟"}' \
  http://127.0.0.1:8000/chat
```

See [backend configuration, source review and error behavior](backend/README.md).
Use fictional questions, not student personal information. Google's Free Tier
data-use terms still apply even with interaction-history storage disabled.

## Verification and limits

A separately approved **single live request** at `6afd480` returned HTTP 200
through the local FastAPI TestClient and from Gemini. It answered the question
above with “during the second term”, cited `[FAQ_GUIDANCE]`, included the Maspero
notice/link and did not invent a registration deadline. There was no retry,
fallback or deployment. This is a local integration test, not a public-server test.

Offline tests use fake model responses and block outbound networking:

```bash
cd backend
. .venv/bin/activate
pip install -r requirements-dev.txt
python -m pytest tests -q
```

The prototype does not cover every pathway, subject, fee or admission rule.
Lexical retrieval and valid citation IDs do not guarantee factual correctness.
There is no conversation memory, personalized assessment, automated human
handover or full product UI. The present handover is a text referral.

## Submission files and historical work

Week 2–4 documents, the Week 5 prompt log, Mermaid flow/architecture diagrams,
Golden Rules checklist and earlier demo recording are preserved. These capture
the team's design and earlier milestones; planned features and the older demo
do not prove the current Gemini integration.

`masari_week5_backend/` retains only the earlier HTML demo and its historical
README. Its obsolete Groq runtime and the unused ZeroGPU/SQLite quota code were
removed. Git history preserves those experiments. No Hugging Face Space,
external account, remote database or secret was deleted or changed.
