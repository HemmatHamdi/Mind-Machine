# Masari: Week 5 System Architecture (Deliverables 2 to 6)

Status of everything below: **planned** (Week 4 Tool Choices, team sign-off pending). Nothing is implemented yet. Items marked *proposed* are not yet in Week 4.

## Deliverable 2: Component explanation

| Component | Responsibility | Technology | Internal/External | Status |
|---|---|---|---|---|
| Interface (SPA) | Screens, session state, disclosure, fallback message, Arabic RTL with English option, accessibility | React (Vite) | Internal | Planned (W4) |
| Role selector | Changes wording and examples only | Frontend only | Internal | Proposed (Flow v2) |
| FastAPI app | Receives requests, routes to the three parts, returns results or errors | Python, FastAPI | Internal | Planned (W4) |
| Scoring engine | Deterministic rules, fit bands, matched factors, mismatches, uncertainty; re-runs on edits | Python | Internal | Planned (W4) |
| Guide endpoint | Input check, BM25 retrieval, prompt building, model call, output check | Python, FastAPI | Internal | Planned (W4) |
| Model adapter | Single entry to the model, one automatic retry, time-out, fallback model | Python | Internal | Planned (W4); retry and time-out values TBD |
| Gemini API | Writes guide answers and Simple wording rewrites only, never ranks | Google Gemini, Flash-class, free tier | **External** | Planned (W4); exact model ID in Week 6 |
| Flash-Lite | Fallback if quota is cut | Google Gemini | **External** | Planned (W4) |
| Pathway data | Pathway records with article, source link, date checked, verification flag | JSON | Internal data store | Planned (W4); verification pending |
| Passages and BM25 index | Short passages with Source IDs for the guide | BM25 | Internal data store | Planned (W4) |
| Logging | Anonymous feedback and test logs only | Python, FastAPI | Internal | Planned (W4) |
| Distress check | Rule-based, inside the Guide endpoint | Python rules | Internal | Proposed (Flow v2), pending W4 update |
| Offline evaluation | Runs the 30+ prompt test set and scripted edit cases | Python scripts | Offline | Planned (W4, Brief 3.1.5) |
| Decrees 150/2026 and 213/2025 | Source of the data | Documents | **External** | Verification pending |

## Deliverable 3: Data and communication flow

1. **Cards and overview:** the interface requests content, the FastAPI app reads the pathway data (JSON) and returns it.
2. **Assessment:** answers go to the FastAPI app, then the Scoring engine, which reads the JSON and returns suggestions with reasons. The model is not involved.
3. **Edit:** edited answers or factor weights go to the same path and re-run the scoring. This is the Principle Feature path.
4. **Guide question:** input check (decide, predict, distress) then BM25 search over the passages. With evidence, the prompt builder sends the passages to the adapter and Gemini. The output check rejects any Source ID that does not exist. Without evidence, the answer is "I am not sure" with a referral to the counselor or the Ministry.
5. **Simple wording:** goes through the same guide path with a style option.
6. **Feedback:** the interface sends it to the FastAPI app, which stores it anonymously in Logging.
7. **Errors:** time-out or error returns to the interface fallback message. Scoring, cards, comparison and reasons keep working if the model is down.
8. **Session state** (answers, weights, notes) stays in browser memory only. There is no database and no login.

## Deliverable 4: Principle Feature (User Control and Agency)

- **What it does:** the user's edits (answers, factor importance, skips, undo) really change the output. The Simple wording switch changes the response style.
- **Where it lives:** (1) the **Scoring engine** in the backend, which recomputes from the edited inputs; (2) the **prompt builder** in the Guide endpoint, which applies the Simple wording style; (3) the **interface controls** that send the edits.
- **Why there:** Brief 3.1.3 requires the feature in the AI pipeline, not only on screen. Because the scoring is deterministic and separate from the model, AQ3 can test that edits change results exactly as the rules predict.
- **Highlighted in the diagram:** thick yellow nodes SE, G3, UI5 and the thick arrows.

## Deliverable 5: Week 5 compliance checklist

| Required element | Covered | Where in the diagram |
|---|---|---|
| Interface | Yes | INTERFACE LAYER |
| Backend | Yes | BACKEND LAYER |
| Model | Yes, separate from the backend | MODEL LAYER |
| Knowledge source or tools | Yes | KNOWLEDGE SOURCES, source decrees |
| Safeguards | Yes, at several layers | Interface notice and fallback, input check, system prompt, output check, verification flags, API key in environment variable |
| Principle Feature location | Yes | Scoring engine, prompt builder, edit controls |

## Deliverable 6: Consistency report

**Consistent with:**
- **Week 4 Tool Choices:** React, FastAPI in three parts, Gemini behind one adapter, JSON plus BM25, listed safeguards, Arabic default.
- **Conversation Flow v2:** hub paths, assessment, guide Q and A, error recovery, feedback, role skip. Every flow interaction maps to a component.
- **Brief:** 3.1 requirements 1 to 5 and 7 are represented; 3.3 principle feature is in the pipeline.
- **Use Case Diagram:** **not available**, so not checked.

**Not drawn, by your decision:** PII masking filter, prompt versions file, hosting location, protocol names.

**Unresolved issues:**
1. **Grounding:** Week 4 describes the JSON as compared with the Official Gazette, but Week 3 shows LawHub (9 of 11 articles) and the Gazette copy is still a to-do.
2. **User roles:** the flow treats student, parent and counselor as primary; Week 3 "Target users" still says parents and counselors are secondary, and the Week 4 journey maps still use the old personas.
3. **Distress check** (and "Report wrong information") are in Flow v2 but not in Week 4 Safeguards or features.
4. **Retry counts** in the error subflow (1 automatic, 2 manual, 3 for connection) and the **time-out in seconds** are not in Week 4. The fallback model switch is not drawn in the flow.
5. **Brief 3.1.4 and Week 4 tests:** testers must also role-play parents and counselors.
6. Week 4 sign-off by the whole team is still pending, so every component is "planned".
