# Masari backend — Gemini API

FastAPI `POST /chat` keeps HTTP Basic authentication and a per-user, in-process
rate limit. Its opt-in model adapter can call Google's **Gemini 3.5 Flash-Lite**
(`gemini-3.5-flash-lite`) at most once per request, after local evidence retrieval.

**Current status: seven reviewed FAQ summaries from a Maspero report are enabled.**
Maspero is the National Media Authority website; its 12 November 2026 article
attributes these FAQs to the Ministry of Education. This is a Ministry-attributed
government-media report, **not a reviewed original decree**. It is a narrow demo
corpus, not a complete or legally authoritative guide. Do not use real student data.

## Grounding and source status

The flow is `/chat` → authentication/rate limit → local Arabic keyword/BM25 search
→ reviewed passages → Gemini → citation-ID check → reply with source links/dates.
No vector database, embeddings, new account, network scraper or paid fallback is
needed. The public request/response shape remains `message` → `reply`.

`data/knowledge.json` contains one reviewed report and three pending source records:

- [Maspero FAQ report](https://www.maspero.eg/egypt/2026/11/12/1005044/التعليم-تستعرض-الأسئلة-الشائعة-وإجاباتها-حول-نظام-شهادة-البكالوريا-المصرية):
  full text reviewed on 22 November 2026. The publisher's
  [about page](https://www.maspero.eg/page/1) identifies `maspero.eg` as its unified
  website. Seven team-written summaries preserve the report's conditions and
  exceptions: financial culture assessment, second-language restrictions,
  guidance meetings, exam Arabization, attendance, projects and transfer after
  failing second-year General Secondary. No images or full article text are copied.

- Decree 213/2025: the Gazette catalogue identifies the decree, but the PDF link
  requests a copy. The legal text has not been reviewed.
- Gazette issue 228 of 15 October 2026: a candidate for decree 150/2026, not verified
  as its full text.
- Ministry statement of 17 August 2026: direct fetch and browser returned 403.

The report has `status: reviewed_report`, not `verified`. A passage's `verified:
true` means its summary was checked against its named source, not against an
unavailable decree. Every answer citing the report gets a backend-added notice
identifying the publisher, publication date and original-decree limitation.
This notice is also sent with the evidence to the model. The pending decrees
remain excluded. No facts from LawHub, AI memory or search snippets are enabled.

To add evidence, first obtain a public Ministry/Gazette document and review its
relevant text and date. Set its source `status` to `verified` only after this
review. Add short, accurate passages (preferably under 600 characters each):

```json
{
  "id": "DOC213_A1",
  "source_id": "decree_213_2025",
  "title": "Reviewed topic and article number",
  "text": "Replace with the reviewed passage, not an AI guess.",
  "checked_on": "YYYY-MM-DD",
  "verified": false
}
```

This is a schema example, not education content. Use unique passage IDs consisting
of uppercase letters, digits or underscores. Set `verified` to `true` only after
checking the text against the actual official source. Record the article/page in
the title, preserve conditions/exceptions, and restart the backend after changes.
No unreviewed passage should be enabled just to make a demo return a model answer.

Retrieval needs at least two meaningful matching words and at least half the
question's meaningful words in a passage; it returns at most three passages.
Weak/no matches return a fixed Arabic referral to the Ministry or school counselor
before creating a model client. This conservative lexical heuristic is not a
semantic relevance or completeness guarantee.

The prompt limits facts to retrieved evidence. An answer must cite retrieved
`[PASSAGE_ID]` values; missing or unknown IDs and model-written URLs cause the
fixed handover instead. The backend appends only reviewed links and review dates.
Citation validation does **not** prove that every claim follows from its cited
passage. Real answer quality, mixed-topic questions, personal-choice refusals and
prompt injection still need evaluation before using this with students.

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

The adapter makes at most one model request, without retry or paid fallback.
No request is made at startup or when no evidence is found. Questions outside the
seven FAQs (for example, all pathway names, subject counts, fees or admissions)
should return the handover rather than model-memory answers.

## Test the API

```bash
curl -s -u demo:YOUR_PASSWORD \
  -H 'Content-Type: application/json' \
  -d '{"message":"متى لقاءات المرشد التعليمي في أولى ثانوي؟"}' \
  http://localhost:8000/chat
```

With the execution flag off, the endpoint returns `503`. With it on, a valid
authenticated request returns `{"reply":"..."}`. A matched FAQ can produce a model
answer with source IDs, the report attribution, its link and review date. An
unsupported question returns the fixed source-unavailable message without a model
request. The curl above is a **live inference** if execution is enabled; do not
run it until separately approved.

One separately approved live request at commit `6afd480` returned HTTP 200 through
the local FastAPI TestClient and from Gemini. The question was
`متى لقاءات المرشد التعليمي في أولى ثانوي؟`. The answer correctly identified the
second term, cited `[FAQ_GUIDANCE]`, included the report notice/link, and did not
invent an administrative deadline. Exactly one outbound request was observed,
with no retry or fallback. This is local integration evidence, not a deployed
backend test or a full answer-quality evaluation. No further inference is approved.

## Offline tests

```bash
pip install -r requirements-dev.txt
python -m pytest tests -q
```

Tests use fake Gemini responses and blocked outbound networking. They verify
request wiring only; they do not prove the real API key, model access, free-tier
status, quota, or a live grounded response. Retrieval tests use the reviewed
report corpus and fictional fixtures under `example.invalid`; fictional fixtures
are not shipped as real data. API wiring tests use fake model output.

Official references:
- [Gemini 3.5 Flash-Lite model](https://ai.google.dev/gemini-api/docs/models/gemini-3.5-flash-lite)
- [Gemini API getting started](https://ai.google.dev/gemini-api/docs/quickstart)
- [Gemini API pricing and Free Tier terms](https://ai.google.dev/gemini-api/docs/pricing?model=gemini-3.5-flash-lite)
