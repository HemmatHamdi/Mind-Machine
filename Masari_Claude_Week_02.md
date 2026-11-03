# Concept Draft: Masar, the Transparent Pathway Guide

**Note on verification tags.** Any detail about the Egyptian Baccalaureate that comes from official sources is marked **[VERIFY-MoE]**. These details must be confirmed against current Ministry of Education and Technical Education (MoETE) publications before use. This includes pathway names, subject lists, grade structure, examination rules, number of attempts, scoring, and university admission links. This draft does not assert any of them. Descriptive labels such as "Pathway A" are placeholders for official data that the team will load from a verified source file.

---

## 1. Concept Name

**Masar** (Arabic for "path"). Tagline: _"See the paths. See the reasons. Choose for yourself."_

---

## 2. Problem and Target Users

**Target users:** Grade 9 students (about 14–15 years old) in Egypt who are preparing to move into the Baccalaureate system. Parents and teachers may sit beside them, but the interface is designed for students.

**Student needs**

- Understand in plain language what changes when they move to the new system.
- Learn what pathways exist and how they differ in subjects, workload, and the kinds of future study they connect to.
- Reflect on their own interests, strengths, and goals, which many students have not yet put into words.
- Get suggestions they can understand and question, not a verdict.

**The problem.** Information about the new system is scattered and changes over time. Students often rely on rumors, family pressure, or the perceived prestige of a path. Many have never been asked what they enjoy or how they like to work. A generic chatbot answer ("you should choose X") would hide its reasoning and could be wrong or outdated. It could also discourage a student unfairly.

**What Masar does.** It explains the system, lets students explore pathways, runs a short reflective assessment, offers _suggestions to consider_ with visible reasons, and supports follow-up discussion. The student keeps control of every input and every decision.

---

## 3. Core Features

| Stage          | Feature                       | Description                                                                                                                                                                                                        |
| -------------- | ----------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **Understand** | System Explainer              | Short, illustrated cards ("How the system works," "What changes in Grade 10," "What a pathway is"). Each card has a plain-language summary, an optional "more detail" layer, and a source and last-verified label. |
|                | Glossary Pop-ups              | Tap any term (e.g., "credit," "attempt") for a simple definition. **[VERIFY-MoE]**                                                                                                                                 |
| **Explore**    | Pathway Cards                 | One card per pathway with a plain summary, typical subjects, kinds of work, and related future study areas. Official facts are tagged with sources.                                                                |
|                | Side-by-Side Comparison       | Choose 2–3 pathways to compare on the same attributes.                                                                                                                                                             |
| **Assess**     | Interest & Strengths Check-in | About 15–20 short questions mixing "which activity do you prefer?" choices, sliders, and a few open prompts. Includes a "Not sure" option on every question.                                                       |
|                | Live Answer Summary           | A sidebar shows what the system has understood so far, in the student's own terms.                                                                                                                                 |
| **Recommend**  | Suggested Paths to Explore    | Two or three pathways shown as "Worth exploring," ordered by fit, each with a plain-language reason, a confidence note, and a "what could change this" note.                                                       |
|                | "Why this?" Panel             | Shows which answers influenced the suggestion, in which direction, and by how much.                                                                                                                                |
| **Guide**      | Conversational Guide          | Chat that answers follow-up questions using only the verified knowledge base and the student's own results.                                                                                                        |
|                | "What if?" Controls           | Students edit answers, adjust importance weights, or hide factors, then watch suggestions update.                                                                                                                  |
|                | Decision Notebook             | Students record pros, cons, questions for parents or teachers, and a private "current thinking" note. They can export it as a PDF to discuss with family or a counselor.                                           |

**Cross-cutting features:** a persistent "How Masar works" link, a source label on every factual claim, a "Report a problem" button, and a data and privacy panel.

---

## 4. Core Interaction Flow

**Step 1: Welcome and Expectations**

- _Student action:_ Opens Masar and taps "Start."
- _Screen:_ A short welcome card: "I help you understand the system and explore options. I give suggestions, not decisions. You stay in charge." Three buttons: **Start with the system**, **Jump to pathways**, **Take the check-in**. A small link reads "What I can and can't do."
- _System response:_ Briefly explains its role and shows the data notice (no name required; answers are stored only if the student chooses to save).
- _Next:_ Choose any starting point. Navigation is not locked to a linear order.

**Step 2: Understand the System**

- _Student action:_ Taps "Start with the system."
- _Screen:_ A swipeable set of 5–6 cards, each with a headline, three short sentences, an illustration, a "Source: MoETE, verified [date]" tag **[VERIFY-MoE]**, and "Explain it simpler" and "Tell me more" buttons.
- _System response:_ The simple version is shown by default. "Explain it simpler" produces a shorter rewrite grounded in the same source text. If the knowledge base has no verified answer to a question, the card shows "Not confirmed yet. Please check with your school or the official Ministry source."
- _Next:_ Continue to the next card, ask a question via "Ask Masar," open the glossary, or move to Explore.

**Step 3: Explore Pathways**

- _Student action:_ Opens the Pathways screen and taps a card.
- _Screen:_ A grid of pathway cards. Each opens a detail view with "What you study," "What it's like," "Where it can lead," and "What's still unconfirmed." Fields come from the verified data file; unverified fields show a yellow "Verify" badge.
- _System response:_ Answers "What's the difference between X and Y?" with a structured comparison, not free-form opinion.
- _Next:_ Select up to three pathways and tap **Compare**, ask a question in chat, or start the check-in.

**Step 4: Compare Pathways (available at any time)**

- _Student action:_ Selects 2–3 pathway cards and taps "Compare."
- _Screen:_ A table with one column per pathway and rows such as subjects, kinds of tasks, skills practised, related study areas, and open questions **[VERIFY-MoE]**.
- _System response:_ Highlights differences only where the data supports them. It never adds "better" or "harder" labels unless an official source states a fact.
- _Next:_ Save the comparison to the Notebook, return to cards, or start the check-in.

**Step 5: Begin the Interest Check-in**

- _Student action:_ Taps "Take the check-in."
- _Screen:_ A screen explaining the purpose ("This helps me suggest paths to explore, not decide for you"), the time required (about 8–10 minutes), a progress bar, and a note saying "You can skip any question, go back, or stop anytime."
- _System response:_ Shows the question categories (activities you enjoy, subjects you feel curious about, how you like to work, goals you're thinking about) and why each is asked.
- _Next:_ Start, or choose "Skip the check-in and keep exploring."

**Step 6: Answer Questions**

- _Student action:_ Answers one question at a time (choice cards, sliders, or short text).
- _Screen:_ One question per screen, with a **"Why am I asked this?"** link, a **"Not sure / Skip"** button, a Back button, and a live **"What I understand so far"** side panel (e.g., "You said you enjoy: building things, solving puzzles").
- _System response:_ Updates the summary after each answer. If answers conflict (e.g., high interest in two opposite activities), it says so neutrally and does not force a pick.
- _Next:_ Edit any earlier answer from the summary panel, skip, or continue to the end.

**Step 7: Review Profile Before Recommendations**

- _Student action:_ Reaches the final check-in screen.
- _Screen:_ **"Your Profile Summary"**: interests, preferred ways of working, and goals in the student's own words, with an Edit button on each item and a slider for "How important is each of these to you?"
- _System response:_ Asks, "Is this a fair picture? Change anything that doesn't feel right before I suggest paths."
- _Next:_ Edit items, set importance weights, or tap **"Show suggestions."**

**Step 8: Receive Suggestions**

- _Student action:_ Taps "Show suggestions."
- _Screen:_ Two or three cards titled **"Paths worth exploring."** Each card has the pathway name, a fit indicator (Strong / Moderate / Some overlap), a two-sentence reason, a "What this doesn't tell us" line, and buttons **Why this?**, **Compare**, and **Save**. A banner reads: _"These are suggestions based on what you told me. They are not a judgment of your ability or your future."_
- _System response:_ Orders cards by fit but shows a clear note if the differences are small ("These two are close. Your answers fit both.").
- _Next:_ Open "Why this?" on any card, compare, or ask questions.

**Step 9: Inspect the Reasons**

- _Student action:_ Taps "Why this?"
- _Screen:_ The **Reasoning Panel** (see Section 5, Screen 6). It lists the answers that raised the fit, the answers that lowered it or didn't match, the weights used, and a "what could change this" list.
- _System response:_ Explains in plain language and offers a "Show me the exact rule" link. The student can remove any factor and see the recalculation.
- _Next:_ Adjust weights, hide a factor, or return to the suggestion list.

**Step 10: Ask Follow-up Questions**

- _Student action:_ Opens "Ask Masar" and types questions such as "Why wasn't Pathway C suggested?" or "What if I like drawing more than I said?"
- _Screen:_ A chat window beside the student's current results, with quick-reply chips ("Why not C?", "What would change this?", "What should I ask my teacher?") and source tags on factual answers.
- _System response:_ Answers using only the verified knowledge base and the student's profile. For anything outside that scope, it says so and points to an official source or a human counselor.
- _Next:_ Continue chatting, edit the profile, compare, or save to the Notebook.

**Step 11: Test "What If?" Scenarios**

- _Student action:_ Changes a slider, edits an answer, or hides a factor (e.g., "ignore my score in X").
- _Screen:_ Suggestions update live, with a before-and-after indicator showing what moved and why.
- _System response:_ States which changes mattered and which did not, e.g., "Changing this made little difference."
- _Next:_ Keep exploring, reset to the original profile, or save the scenario.

**Step 12: Reflect and Record**

- _Student action:_ Opens the Decision Notebook.
- _Screen:_ Sections for "Pathways I'm considering," "Reasons for," "Concerns," "Questions for my parents/teacher," and "Where I stand now." Each can be edited freely. The student chooses which items from the session to import.
- _System response:_ Offers prompts ("What would you want to find out before deciding?") but never fills in a decision.
- _Next:_ Export as PDF, delete notes, or return to any earlier stage.

**Step 13: Close the Session**

- _Student action:_ Taps "Finish."
- _Screen:_ A closing card: "You decide. Before choosing, check the official sources and talk to your school counselor," with official-source link placeholders **[VERIFY-MoE]**, plus **Save my session**, **Delete my data**, and **Start over**.
- _System response:_ Confirms what is stored and for how long (per the privacy design in Section 8).
- _Next:_ Save, delete, or leave.

---

## 5. Key Screens

**Navigation:** a bottom bar with five items matching the stages (Understand, Explore, Check-in, Suggestions, Ask/Notebook). A fixed "How Masar works" link and a "Privacy" link appear in the header. The student can move between any stages at any time.

**Screen 1: Home**

```
+--------------------------------------------+
|  Masar                  [How it works][🔒] |
|--------------------------------------------|
|  Welcome! I help you understand the        |
|  system and explore your options.          |
|  I give suggestions, not decisions.        |
|                                            |
|  [ Understand the system ]                 |
|  [ Explore pathways      ]                 |
|  [ Take the check-in     ]                 |
|                                            |
|  What I can / can't do  >                  |
+--------------------------------------------+
```

**Screen 2: System Explainer Card**

```
+--------------------------------------------+
|  Understand  2 of 6                        |
|  What is a "pathway"?                      |
|  [illustration]                            |
|  - Short sentence 1                        |
|  - Short sentence 2                        |
|  - Short sentence 3                        |
|  Source: MoETE [VERIFY-MoE] | Checked: date|
|  [Explain simpler] [Tell me more] [Next >] |
+--------------------------------------------+
```

**Screen 3: Pathway Comparison**

```
+---------------------------------------------------+
| Compare (choose up to 3)                          |
|              | Pathway A | Pathway B | Pathway C  |
| Subjects     | [VERIFY]  | [VERIFY]  | [VERIFY]   |
| Typical work | ...       | ...       | ...        |
| Skills used  | ...       | ...       | ...        |
| Leads toward | [VERIFY]  | [VERIFY]  | [VERIFY]   |
| Still unclear| ...       | ...       | ...        |
|  [Save to Notebook]    [Ask about differences]    |
+---------------------------------------------------+
```

_(Column headings use placeholders. Official names are loaded from verified data.)_

**Screen 4: Check-in Question**

```
+--------------------------------------------+
| Question 7 of 18  [=======>      ]          |
| Which would you rather do for a weekend?   |
| [ Build or fix something   ]               |
| [ Read or write something  ]               |
| [ Plan or organize an event]               |
| [ Not sure / Skip ]                        |
| Why am I asked this?  >                    |
|--------------------------------------------|
| What I understand so far:                  |
|  • Enjoys: building, puzzles  [edit]       |
+--------------------------------------------+
```

**Screen 5: Suggestions**

```
+--------------------------------------------------+
| Paths worth exploring                            |
| These are suggestions, not judgments of ability. |
| 1. Pathway B   Fit: Strong                       |
|    You enjoy X and Y, which this path uses.      |
|    Not covered: your goals after school.         |
|    [Why this?] [Compare] [Save]                  |
| 2. Pathway A   Fit: Moderate  ...                |
| (Close results: your answers fit both.)          |
+--------------------------------------------------+
```

**Screen 6: Reasoning Panel ("Why this?")**

```
+--------------------------------------------------+
| Why Pathway B?                                   |
| Raised the fit:                                  |
|   ▲▲ "Enjoys building"      weight: High [slider]|
|   ▲  "Likes solving puzzles" weight: Med [slider]|
| Did not match / lowered:                         |
|   ▼  "Prefers writing tasks" weight: Low [slider]|
| Skipped / unsure: 3 questions (not counted)      |
| What could change this:                          |
|   • If you rate "teamwork" higher                |
|   • If you add a goal after school               |
| [Hide a factor]  [Reset]  [Show exact rule]      |
| Confidence: Medium (several "not sure" answers)  |
+--------------------------------------------------+
```

**Screen 7: Ask Masar (Chat)**

```
+--------------------------------------------+
| You: Why wasn't Pathway C suggested?       |
| Masar: Your answers matched fewer of C's   |
|  activity areas. Here are the three main   |
|  factors... [Source tags] [See in panel]   |
| [Why not C?] [What would change this?]     |
| [What should I ask my teacher?]            |
| Type a question...                [Send]   |
+--------------------------------------------+
```

**Screen 8: Decision Notebook and Privacy**

- Notebook: editable sections plus **Export PDF** and **Delete notes**.
- Privacy panel: what is stored, a toggle for "Save my session," a **Delete all my data** button, and a plain-language explanation of how data is used.

---

## 6. Assessment and Recommendations

**Question design.** The check-in uses about 15–20 questions in four groups. Each question maps to one or more _dimensions_.

1. **Activity interests:** which kinds of activities the student enjoys (e.g., building, analyzing, writing, helping people, organizing, creating).
2. **Subject curiosity:** how curious the student feels about broad subject areas **[VERIFY-MoE: align with actual Baccalaureate subject areas]**.
3. **Working style:** individual or team work, practical or theoretical tasks, structured or open-ended work.
4. **Aspirations:** future study or work areas the student is curious about, with "I don't know yet" as a fully valid answer.

Questions are written about _enjoyment and preference_, not ability. Self-reported strengths are collected as "things I feel confident doing," labeled as self-perception, not measured skill.

**Analysis method (transparent and rule-based for the MVP).**

- The team builds a **Pathway Profile Table**: for each pathway, a set of dimensions with relevance values (e.g., High/Medium/Low) assigned by the team from verified subject and curriculum descriptions **[VERIFY-MoE]**. The table is documented, versioned, and viewable in the app.
- Each answer maps to a dimension score. The student's dimension scores are multiplied by pathway relevance values and by the student's own importance weights, then summed into a **fit score** for each pathway.
- Fit scores are shown as bands (Strong / Moderate / Some overlap), not numbers, to avoid false precision. If the top two bands are within a small margin, the system labels them "close."
- Skipped and "Not sure" answers are excluded from scoring, not guessed. They reduce the **confidence indicator** (Low/Medium/High), which is based on how many questions were answered and how consistent the answers are.

**Role of the language model.** The LLM does _not_ decide the ranking. It does three things:

1. Turns the rule-based results into plain-language explanations using a fixed template.
2. Answers follow-up questions using retrieval from the verified knowledge base and the student's profile.
3. Rewrites explanations more simply on request.

Keeping scoring deterministic makes explanations faithful to the actual calculation and makes testing straightforward.

**Justification format.** Every recommendation card contains:

- _Matching reasons:_ the 2–3 strongest answer-to-pathway links, in the student's own words.
- _Mismatches or gaps:_ any answers that did not fit.
- _Unknowns:_ what was skipped and what the check-in cannot measure.
- _Next steps:_ what to verify officially and who to ask.

**Example reason text (illustrative only):** "You said you enjoy building things and solving puzzles. Pathway B includes many tasks like these. You also said you prefer writing, which fits Pathway B less. You skipped questions about future goals, so this suggestion may change once you think more about them."

---

## 7. Transparency and User Control

| Principle                     | Where it appears                                                                | What the student can do                                                       |
| ----------------------------- | ------------------------------------------------------------------------------- | ----------------------------------------------------------------------------- |
| **See what the system knows** | "What I understand so far" panel; Profile Summary                               | Edit or delete any interpretation                                             |
| **See why**                   | "Why this?" Reasoning Panel with raised, lowered, and unused factors            | Inspect answer-to-pathway links and the exact rule                            |
| **See how sure it is**        | Confidence indicator; "close results" notices; "What this doesn't tell us" line | Add answers to raise confidence, or accept the uncertainty                    |
| **See where facts come from** | Source and last-verified tag on every factual statement; "Verify" badges        | Open the source link; flag a possible error                                   |
| **Test alternatives**         | Importance sliders; Hide a Factor; What-if edits                                | Re-run suggestions and view before/after changes                              |
| **Compare**                   | Side-by-side table; "Why not C?" explanation                                    | Compare any 2–3 pathways, including ones not suggested                        |
| **Ask**                       | Chat with quick questions                                                       | Ask anything; receive grounded answers or an honest "I can't confirm that"    |
| **Decide**                    | Decision Notebook; closing screen                                               | Record their own reasoning; no "Select this path" button exists in the system |
| **Leave or erase**            | Skip any question; stop anytime; Delete my data                                 | Exit without penalty                                                          |

**Design rule:** the system never uses language such as "You should choose," "You are suited for," or "You are not suited for." Approved phrasing includes "worth exploring," "your answers overlap with," and "based on what you told me."

---

## 8. Responsible Guidance

**Handling uncertainty**

- Confidence indicator based on answer count and consistency.
- "Not sure" is treated as valid information, never forced.
- When fit results are close or confidence is low, the system says so directly and recommends exploring more or speaking with a counselor.
- When facts are unverified or likely to change, the card shows "Not confirmed. Check official sources **[VERIFY-MoE]**."

**Avoiding bias and unsupported conclusions**

- Questions measure interests and preferences only. The system does not infer ability, intelligence, or future success, and does not use grades, gender, family income, region, or family background to score pathways.
- No pathway is labeled "best," "easiest," or "most prestigious." Comparisons use neutral, source-based attributes.
- Pathway Profile Table values are reviewed by at least two team members and, ideally, by an educator, and are shown to students on request.
- Wording is checked for gender and social stereotypes (e.g., activities are not phrased in gendered ways).
- The team tests the same answer sets with varied names, phrasing, and demographics in the prototype to check that outputs do not shift unexpectedly.
- The chatbot is restricted by retrieval to the verified knowledge base. When asked about unsupported topics (admissions cutoffs, job-market predictions, individual school policies), it responds that it cannot confirm and names where to look.

**Protecting student information**

- No login, name, phone number, or national ID is required.
- Data minimization: only answers needed for the session are processed. Session saving is **off by default** and requires an explicit opt-in.
- Plain-language privacy notice at the start, with a "Delete all my data" button always visible.
- For a university prototype involving minors, the team obtains institutional ethics approval, uses guardian or school consent where required, and does not collect identifiable data during testing. **[VERIFY: university ethics board and Egyptian data-protection requirements for minors]**
- If an external LLM service is used, personal identifiers are never sent, and the team verifies the provider's data-retention terms.

**Communicating limitations.** A persistent "What I can and can't do" page states:

- Masar is an exploration tool, not an official Ministry service and not a counselor.
- Suggestions reflect only the student's answers and the team's documented pathway descriptions.
- Policies may change, and students should confirm details with their school and official sources.
- Masar cannot predict exam results, admission outcomes, or career success.

**Wellbeing safeguard.** If a student expresses distress or pressure (e.g., "my parents will be angry"), Masar responds supportively, avoids giving family advice beyond neutral suggestions, and encourages talking to a trusted adult or school counselor.

---

## 9. MVP and Evaluation

### 9.1 Prototype Scope (realistic for a small student team)

**Included**

- A web-based or clickable prototype (e.g., a Figma prototype for the interface plus a simple working web app for the check-in and suggestions).
- **Verified knowledge base:** a structured file (JSON or spreadsheet) with system explainer text and pathway details, each entry carrying a source and verification date. Fields that cannot be verified are marked and shown with "Verify" badges.
- **Check-in module:** 15–20 questions with scoring rules and the Pathway Profile Table.
- **Recommendation screen** with the Reasoning Panel, importance sliders, and the confidence indicator.
- **Comparison screen** for 2–3 pathways.
- **Constrained chat:** an LLM with retrieval over the knowledge base and the student's profile, with refusal behavior for out-of-scope questions.
- **Decision Notebook** with PDF export (basic).
- Privacy notice and delete function.

**Excluded from the MVP:** accounts, parent/teacher dashboards, grade or exam-score integration, live Ministry data feeds, career-prediction features, multilingual support beyond a possible Arabic/English toggle, and a mobile app.

**Suggested team roles and sequence:** (1) source gathering and verification of Ministry information; (2) content and question writing; (3) scoring logic and explanation templates; (4) interface; (5) chat integration and testing.

### 9.2 Evaluation Plan

Evaluation has not yet been conducted. The following are planned measures, and the targets are proposed goals, not results.

| Area                                           | Method                                                                                 | Metric                                                          | Proposed target                                                                       |
| ---------------------------------------------- | -------------------------------------------------------------------------------------- | --------------------------------------------------------------- | ------------------------------------------------------------------------------------- |
| **Understanding of the system**                | Short pre/post quiz (5–8 items) with Grade 9–10 students or age-appropriate volunteers | Change in correct answers                                       | Improvement from pre to post                                                          |
| **Transparency comprehension**                 | After viewing a suggestion, ask: "Why did Masar suggest this?"                         | % who correctly identify at least two reasons                   | ≥ 80%                                                                                 |
| **Perceived explainability**                   | Post-task questionnaire (Likert 1–5)                                                   | Mean rating on "I understand why I got these suggestions"       | ≥ 4.0                                                                                 |
| **Perceived control**                          | Post-task questionnaire (Likert 1–5)                                                   | Mean rating on "I felt in control of the process and decision"  | ≥ 4.0                                                                                 |
| **Appropriate trust**                          | Ask whether students think suggestions are "final" or "to explore"                     | % who describe them as explorable rather than definitive        | ≥ 80%                                                                                 |
| **Use of control features**                    | Interaction logs (anonymous, with consent)                                             | % who open "Why this?"; % who edit an answer or adjust a slider | Reported descriptively; aim for a majority opening "Why this?"                        |
| **Usability**                                  | Task-completion observation; System Usability Scale (SUS)                              | Completion rate; SUS score                                      | ≥ 85% completion; SUS ≥ 70                                                            |
| **Accuracy of facts**                          | Expert or team audit of the knowledge base and chat answers against official sources   | % of statements matching sources; number of unsupported claims  | 100% of knowledge-base entries sourced; zero unsupported claims in the audited sample |
| **Chat safety/grounding**                      | Test set of 30–50 questions including out-of-scope and leading prompts                 | % correctly refused or flagged; % of answers with a source      | ≥ 90%                                                                                 |
| **Bias check**                                 | Run identical answer sets with varied names or wording; review wording of all items    | Differences in outputs; flagged biased phrases                  | No unexplained differences; all flagged items revised                                 |
| **Student reflection**                         | Open-ended question: "What did you learn about your preferences?"                      | Qualitative coding                                              | Themes reported                                                                       |
| **Decision confidence (not decision outcome)** | Likert before and after: "I feel ready to think about my choice"                       | Change in mean                                                  | Positive shift                                                                        |

**Ethical note for testing.** Studies with minors require institutional approval and appropriate consent **[VERIFY]**. Evaluation measures understanding, transparency, and control, and does not treat a student's agreement with a suggestion as a measure of success.

**Open items to verify before the build (all [VERIFY-MoE])**

- Official Baccalaureate structure, grade levels, and pathway names.
- Subjects per pathway, including compulsory and optional subjects.
- Examination rules, number of attempts, scoring, and their link to university admission.
- Timing and rules for choosing or changing pathways.
- Official source links to cite in the app.
