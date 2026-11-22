# Source review — 22 November 2026

The corpus contains **15 reviewed summaries**, not full documents, a web crawler,
or a guarantee that every current regulation is covered. No model call was made
to ingest these sources. All source URLs, publication dates, review dates and
provenance notices are stored in `knowledge.json`.

## Decree 150/2026: reviewed copy

The team supplied `lawhub.info-eg-dec-150-2026_1795308986221.pdf`: eight scanned,
LawHub-branded pages showing Egyptian Gazette issue 228, 15 October 2026,
pages 14–21, decree 150 dated 18 August 2026. All eight pages were visually read.
The official DSpace catalogue confirms the issue date/publisher, but its file
requires a copy request; it does not authenticate the supplied scan.
EGyin's report of decree 150 was read and corroborates the subject choices.
The scan itself is not redistributed here; the team must retain its review copy.

Five enabled summaries:

| Passage | Decree location | Scope |
| --- | --- | --- |
| `DEG150_G2_ALL_TRACKS` | Article 2, Gazette p.16 | One elective per grade-two track, all four pairs |
| `DEG150_G2_PATHS` | Article 2, pp.16–17 | Three common subjects plus one Engineering/CS elective |
| `DEG150_G2_ACTIVITIES` | Article 2, pp.16–17 | Financial culture and sports are outside the total |
| `DEG150_G3_PATHS` | Article 3, pp.18–19 | Two grade-three specializations; religious education condition |
| `DEG150_PATH_SWITCH` | Article 6, p.20 | Grade-three pathway-change study condition |

These use `reviewed_copy`, not `verified` source status. The source notice makes
the copy's provenance visible in every answer. Newer rules take priority over
older grade-two/three lists; no conflicting old list was enabled.
No university placement guarantee, specific school procedure, retake fee, or
automatic application of these rules to every individual case is inferred.

## Other supplied URLs

- **Youm7, 12 September 2025:** reviewed transcription of decree 213/2025.
  `DEG213_SYSTEM` summarizes Article 1's optional/free/three-year framework;
  `DEG213_G1_SUBJECTS` records the six subjects added to the first-year total,
  three subjects outside that total, and the religion passing condition.
  Both are labeled `reviewed_report`; the article is not an original Gazette PDF.
- **Ministry, 17 September 2025 and 1 September 2026:** search indexing of the
  official pages shows the same six first-year core subjects and says the subject
  map is unchanged in 2026, including Integrated Science. Direct page fetches
  returned 403, so these links are cross-checks only; the enabled list is based
  on Youm7's full transcription, not on search snippets.
- **Cairo Governorate, 3 August 2026:** reviewed English article explicitly
  attributes its university admission overview to **Al-Ahram Gate**.
  `CAIRO_UNIVERSITY_ADMISSIONS` preserves that attribution. The 90% figure is an
  illustration, not an actual program cutoff. It cannot answer which college
  a particular student can enter or what next year's cutoff will be.
- **Ministry `baccalau` page:** direct access returned HTTP 403. Search indexing
  identifies a January 2025 discussion of a proposal. Recorded but excluded;
  neither snippets nor a historical proposal become current rules.
- **EGyin:** used as corroboration of decree 150, not a duplicate passage set.

## Existing source

The seven Maspero FAQ summaries remain explicitly attributed reports. Their
scope and exceptions are preserved. In particular, the financial-culture FAQ
describes assessment details, while decree 150 describes the subject's status;
neither substitutes for the other.

## Neutral counselor-question helper

Requests for questions to discuss with a school counselor use a deterministic
three-question template and do not call Gemini. The questions may repeat an
interest stated by the student, but do not recommend a path or claim that any
track is a good fit. `FAQ_GUIDANCE` is cited only for the report's statement that
the counselor supports students in understanding paths and choosing; the template
itself is team-authored conversational scaffolding, not a Ministry rule.

## Retrieval and testing limitations

The simple Arabic lexical/BM25 matcher can miss paraphrases and can retrieve
related but insufficient passages. The model must answer only from evidence,
with passage IDs; the backend validates IDs and adds reviewed URLs/notices.
This checks source wiring, not factual entailment of every generated sentence.
Offline tests verify the team's exact Engineering/CS question and an authenticated
API request with a **fake model**, plus out-of-scope refusal and provenance labels.
No new live Gemini inference is authorized by this source update.
