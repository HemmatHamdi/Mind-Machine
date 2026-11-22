# Masari backend — Gemini API

FastAPI `POST /chat` keeps HTTP Basic authentication and a per-user, in-process
rate limit. Its opt-in model adapter can call Google's **Gemini 3.5 Flash-Lite**
(`gemini-3.5-flash-lite`) at most once per request, after local evidence retrieval.

**Current status: reviewed pathway rules and limited reports are enabled.**
The knowledge base contains short team-written summaries, not model-memory answers.
It is a narrow demo corpus, not a complete or legally authoritative guide.
Do not use real student data.

## Grounding and source status

The flow is `/chat` → authentication/rate limit → either a local, deterministic
counselor-question helper (no model call), or Arabic keyword/BM25 search
→ reviewed passages → Gemini → citation-ID check → reply with source links/dates.
No vector database, embeddings, new account, network scraper or paid fallback is
needed. The public request/response shape remains `message` → `reply`.

`data/knowledge.json` records source provenance and review dates:

- [Maspero FAQ report](https://www.maspero.eg/egypt/2026/11/12/1005044/التعليم-تستعرض-الأسئلة-الشائعة-وإجاباتها-حول-نظام-شهادة-البكالوريا-المصرية):
  full text reviewed on 22 November 2026. The publisher's
  [about page](https://www.maspero.eg/page/1) identifies `maspero.eg` as its unified
  website. Seven team-written summaries preserve the report's conditions and
  exceptions: financial culture assessment, second-language restrictions,
  guidance meetings, exam Arabization, attendance, projects and transfer after
  failing second-year General Secondary. No images or full article text are copied.

- Decree 213/2025: the Youm7 transcription was reviewed for the general
  optional/free/three-year system and first-year subject list. The original file
  still requests a copy. Ministry pages from 2025 and 2026 appear to corroborate
  the first-year list in search indexing, but direct fetch returned 403; they are
  labeled cross-checks, not the enabled source text.
- Decree 150/2026, Gazette issue 228 of 15 October 2026: the team's eight-page
  LawHub-branded scan (Gazette pages 14–21) was visually reviewed and the subject
  rules cross-checked against EGyin. Five summaries cover grade-two choices across
  the four tracks, Engineering/Computer Science subject counts, financial culture/
  sports, grade-three specializations, and pathway changes. The catalogue confirms
  issue metadata only. This is
  `reviewed_copy`, not a digital original obtained directly from the Government Press.
- Cairo Governorate, 3 August 2026: one general university-coordination summary;
  the page explicitly cites Al-Ahram Gate. It is not a current admissions cutoff.
- The team's Ministry `baccalau` link is indexed as a January 2025 proposal
  discussion. Direct access returned 403. No current rules were enabled from it.
- Ministry statement of 17 August 2026: direct fetch and browser returned 403.

Reports have `status: reviewed_report`; the scan has `reviewed_copy`. A passage's
`verified: true` means its summary was checked against its named source, not that
the publisher or document copy has been independently authenticated. Every answer
using these sources gets a backend-added provenance notice. The same notice goes
to the model. The later decree is used for grade-two/three subject rules; no
conflicting older subject list is enabled. Pending sources and search snippets
remain excluded. See `data/SOURCE_REVIEW.md` for articles/pages and limitations.

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
reviewed passages (for example, university program cutoffs or retake fees) should
return the handover rather than model-memory answers.
Requests for short questions to ask a school counselor use a separate deterministic
template, cite the reviewed FAQ about counselor guidance, and do not call Gemini.
The helper does not choose a path or claim that an interest fits a particular path.

## Test the API

Open `http://localhost:8000/` for the minimal Arabic browser interface. Enter an
HTTP Basic username/password created with `create_chat_user.py`, type a question
and press **إرسال السؤال**. The page sends one `POST /chat` only on button press;
it does not save chat history or automatically retry. Its password is not saved
by the app. With model execution disabled, the backend returns `503`.

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
corpus and fictional fixtures under `example.invalid`; fictional fixtures
are not shipped as real data. API wiring tests use fake model output.

Official references:
- [Gemini 3.5 Flash-Lite model](https://ai.google.dev/gemini-api/docs/models/gemini-3.5-flash-lite)
- [Gemini API getting started](https://ai.google.dev/gemini-api/docs/quickstart)
- [Gemini API pricing and Free Tier terms](https://ai.google.dev/gemini-api/docs/pricing?model=gemini-3.5-flash-lite)
