# University Term Project Concept Draft: Masari (مساري)

**An Explainable AI Transition Guide for the Egyptian Baccalaureate**

---

## 1. Concept Name

**Masari** (مساري – _My Pathway_): An explainable, step-by-step AI guidance system designed to help Grade 9 students navigate their transition into the Egyptian Baccalaureate system.

---

## 2. Problem and Target Users

- **Target Users:** Grade 9 students in Egyptian schools transitioning into upper secondary education, along with their parents and school counselor facilitators.
- **The Problem:** Grade 9 students face a critical academic junction with minimal personalized guidance. The Egyptian Baccalaureate system introduces structured academic pathways, subject choices, and high-stakes examination frameworks. Students often experience decision anxiety, rely on peer bias, or fail to connect current subject interests to long-term career aspirations.
- **System Goal:** Provide an accessible, transparent tool that translates official academic structures into actionable insights while keeping final decision-making authority firmly in the student's hands.

---

## 3. Core Features

The system integrates five sequential stages supported by transparency and user agency mechanisms:

| Stage             | Feature Name                     | Description                                                                                                                                             |
| ----------------- | -------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **1. Understand** | **System Explorer**              | Translates complex secondary school regulations into interactive visual maps, simple language breakdowns, and subject requirement guides.               |
| **2. Explore**    | **Pathway Comparator**           | Allows students to compare academic tracks side-by-side across workload, subject breakdown, and higher-education eligibility.                           |
| **3. Assess**     | **Adaptive Interest Matrix**     | A non-judgmental, interactive survey exploring academic preferences, learning styles, subject enjoyment, and broad career interests.                    |
| **4. Recommend**  | **Explainable Match Engine**     | Generates weighted, non-definitive pathway suggestions accompanied by a visible "Why this recommendation?" breakdown.                                   |
| **5. Guide**      | **Interactive Decision Sandbox** | A conversational, inspectable chat interface where students can test "what-if" scenarios, override weights, and generate exportable decision summaries. |

---

## 4. Core Interaction Flow

1. **System Overview & Exploration:** Stage 1: Understand.

- **Student Action:** Launches _Masari_, selects their preferred interface language (Arabic or English), and clicks "Explore the Baccalaureate System."
- **On-Screen Elements:** A high-level infographic showing the structure of the Egyptian Baccalaureate system, key milestone markers for Grade 10–12, and verified subject domain categories.
- **AI Response:** Displays verified structure data; flags topics requiring official school or Ministry verification with a clear indicator tag (`[Requires Ministry Verification]`).
- **Next Steps:** Click on individual subject blocks to read simplified descriptions or proceed to "Compare Pathways."

2. **Side-by-Side Pathway Comparison:** Stage 2: Explore.

- **Student Action:** Selects two or three pathways (e.g., Scientific/STEM Focus vs. Humanities/Arts Focus) to compare.
- **On-Screen Elements:** Side-by-side comparative table highlighting core subjects, elective spaces, general assessment formats, and sample university faculty destinations.
- **AI Response:** Generates a direct contrast highlighting key differences without rating one track over another.
- **Next Steps:** Select "Start My Assessment" or bookmark specific pathways for later review.

3. **Interactive Self-Assessment:** Stage 3: Assess.

- **Student Action:** Completes a 12-question interactive survey answering questions about subject preferences, project types enjoyed, and self-perceived skill strengths.
- **On-Screen Elements:** Single-question cards featuring Likert scales, drag-and-drop subject sorting, and optional short text inputs (e.g., "What is your favorite topic outside of school?").
- **AI Response:** Tracks real-time completion confidence; provides neutral encouragement without steering choices toward specific tracks.
- **Next Steps:** Submit answers to view the generated match profile.

4. **Review Explainable Recommendations:** Stage 4: Recommend.

- **Student Action:** Views the personalized match results screen.
- **On-Screen Elements:** A ranked breakdown of pathways displaying percentage affinity scores (e.g., 85% Match), alongside prominent "Inspect Logic" buttons and factor breakdown charts.
- **AI Response:** Displays transparent matching logic explaining exactly which user answers contributed to each score component (e.g., "+30% due to strong interest in Mathematics and Problem Solving").
- **Next Steps:** Click "Inspect Recommendation Logic," adjust answer weightings manually, or jump into the "Guidance Sandbox."

5. **Interactive Guidance & Decision Control:** Stage 5: Guide.

- **Student Action:** Types a query in the guidance workspace (e.g., "What if I want to study Economics but I don't like advanced calculus?").
- **On-Screen Elements:** Split-screen layout featuring a conversational interface on the left and a dynamic "Decision Summary Card" on the right.
- **AI Response:** Provides balanced explanations highlighting trade-offs, relevant elective combinations, and official verification disclaimers. Updates the decision card dynamically as options are explored.
- **Next Steps:** Save, print, or export the final "Pathways Exploration Report" for discussions with parents and school guidance counselors.

---

## 5. Key Screens & Interface Layouts

### Screen 1: Explainable Recommendation Dashboard

This screen presents assessment results using clear visual breakdowns rather than opaque scores.

```
+-----------------------------------------------------------------------------------+
|  MASARI | Baccalaureate Pathway Guide                       [ Arabic | English ]  |
+-----------------------------------------------------------------------------------+
|                                                                                   |
|  YOUR PATHWAY MATCH BREAKDOWN                                                     |
|  Based on your self-assessment, here are pathways that align with your inputs.    |
|                                                                                   |
|  +-----------------------------------------------------------------------------+  |
|  | 1. Scientific & Technological Track                   85% Match              |  |
|  |    Key Alignments: High interest in Physics, preference for lab work.       |  |
|  |    [ Why this match? ]  [ Compare Track ]  [ Explore Electives ]            |  |
|  +-----------------------------------------------------------------------------+  |
|                                                                                   |
|  +-----------------------------------------------------------------------------+  |
|  | 2. Business & Social Sciences Track                    72% Match              |  |
|  |    Key Alignments: Strong interest in Data Analysis and Economics.          |  |
|  |    [ Why this match? ]  [ Compare Track ]  [ Explore Electives ]            |  |
|  +-----------------------------------------------------------------------------+  |
|                                                                                   |
|  +-----------------------------------------------------------------------------+  |
|  | EXPLANATION PANEL (Expanded for Track 1)                                    |  |
|  | • Subject Alignment:  [====================......] 70% Math/Science preference|  |
|  | • Activity Style:     [========================..] 85% Problem-solving     |  |
|  | • Long-Term Goals:    [=================.........] 60% Engineering interest |  |
|  |                                                                             |  |
|  | [ Edit My Assessment Inputs ]  [ Open Decision Sandbox ]                    |  |
|  +-----------------------------------------------------------------------------+  |
+-----------------------------------------------------------------------------------+

```

---

### Screen 2: Interactive Guidance Sandbox

Allows conversational exploration with full visibility into source data and decision tags.

```
+-----------------------------------------------------------------------------------+
|  MASARI | Guidance Sandbox                                    [ Export Summary ]  |
+-----------------------------------------------------------------------------------+
|  CONVERSATION PANEL                       | DECISION SUMMARY CARD                 |
|                                           |                                       |
|  User: What happens if I choose           | Selected Focus:                       |
|  Humanities but still want to study       | Scientific / Data Track               |
|  Digital Media in university?             |                                       |
|                                           | Key Strengths Identified:             |
|  AI: You can combine core Humanities      | • Analytical reasoning                |
|  modules with Applied Computer Science    | • Visual project preferences          |
|  electives [Subject to MoE availability]. |                                       |
|                                           | Verified Policy Note:                 |
|  Key Trade-Offs:                          | [!] Specific subject track requirements|
|  • Stronger focus on essay writing        |     must be confirmed with your       |
|  • Requires specific math electives for   |     school counselor.                 |
|    tech-focused media programs            |                                       |
|                                           |                                       |
|  [ Ask a follow-up...           ] [Send]  | [ Adjust Weights ] [ Finalize Plan ]  |
+-----------------------------------------------------------------------------------+

```

---

## 6. Assessment & Recommendation Logic

The matching system processes student inputs through an explicit rule matrix rather than a black-box model.

```
+---------------------+      +---------------------+      +------------------------+
| Student Self-Report | ---> | Rule-Based Match    | ---> | Transparent Affinity   |
| (Interests/Skills)  |      | Scoring Engine      |      | Profile & Explanations |
+---------------------+      +---------------------+      +------------------------+

```

### Matching Algorithm & Mechanics

1. **Feature Vectoring:** Student survey responses are categorized into three feature vectors:

- **Subject Preference Vector ($S$):** Scores across basic domain areas (e.g., Mathematics, Natural Sciences, Humanities, Languages, Arts).
- **Learning Style Vector ($L$):** Weights for project-based work, theoretical analysis, memorization/writing, and practical lab work.
- **Career Orientation Vector ($C$):** Broad functional areas (e.g., Healthcare, Technology, Business/Finance, Public Policy, Creative Media).

2. **Pathway Mapping:** Each official pathway option ($P_k$) is represented by an ideal baseline vector across the same dimensions.
3. **Similarity Score Calculation:** A weighted dot product calculates the raw affinity score:

$$\text{Affinity}(P_k) = w_s (S \cdot P_{k,s}) + w_l (L \cdot P_{k,l}) + w_c (C \cdot P_{k,c})$$

_Default Weights:_ $w_s = 0.50$, $w_l = 0.25$, $w_c = 0.25$. 4. **Justification Generation:** The engine extracts top-contributing positive and negative components to build the human-readable explanation card automatically.

---

## 7. Transparency and User Control

- **Visible Reasoning Panels:** Every recommendation card includes an editable "Why this match?" section that lists precisely which user inputs increased or decreased the alignment score.
- **Manual Preference Sliders:** Students can dynamically alter category weights (e.g., increasing the weight of "Career Interest" over "Current Subject Grades") to observe how recommendations adjust in real time.
- **Direct Input Editing:** Students can revisit and modify their survey answers at any time without resetting their entire profile history.
- **Decoupled AI Output:** The conversational AI in the sandbox step operates under strict system instructions: it must never declare a path "best" or " mandatory," framing outputs instead as "Options to consider based on your preferences."

---

## 8. Responsible Guidance & Safety Protocols

```
               +------------------------------------------------+
               |            STUDENT INPUT / QUERY               |
               +------------------------------------------------+
                                       |
                                       v
               +------------------------------------------------+
               |        SYSTEM GROUNDING & CHECK LAYER          |
               +------------------------------------------------+
                                       |
             +-------------------------+-------------------------+
             |                                                   |
             v                                                   v
+-------------------------+                         +-------------------------+
| Unverified Policy Query |                         | Definitive Capability   |
| (e.g., Exam Rule)       |                         | Assessment Query        |
+-------------------------+                         +-------------------------+
             |                                                   |
             v                                                   v
+-------------------------+                         +-------------------------+
| Output Response with    |                         | Refusal & Re-framing:   |
| Verification Flag:      |                         | "AI cannot measure your |
| [Requires MoE           |                         | future potential. Here  |
| Verification Tag]       |                         | are factors to weigh."  |
+-------------------------+                         +-------------------------+

```

- **Uncertainty & Verification Flagging:** Official policy details, minimum admission percentages, and specific exam regulations vary over time. The system marks unverified parameters with clear visual indicators: `[Requires verification with Ministry of Education rules or school administration]`.
- **Bias Mitigation & Non-Determinism:**
- The system explicitly avoids linking academic tracks to gender, socioeconomic indicators, or rigid intelligence assumptions.
- No language declaring absolute outcomes (e.g., "You are not suited for Science") is permitted. The system uses supportive, open-ended phrasing (e.g., "Students who prefer less math-intensive modules often explore...").

- **Data Privacy & Ethics:**
- Zero storage of personally identifiable information (PII) like national IDs or full legal names.
- Session data is stored locally in the client browser session memory (`sessionStorage`) and purged upon session termination.

- **Boundaries of AI Advice:**
- The system includes a persistent banner stating: _"Masari is an educational exploration assistant, not an official school advisory or university admissions authority."_

---

## 9. MVP Definition and Prototype Evaluation

### Prototype Scope (University Term Project)

- **Technology Stack:** React frontend interface connected to a lightweight Python FastAPI backend using a deterministic scoring script alongside an LLM endpoint (e.g., Gemini API) with strict system instructions for the conversational sandbox.
- **Knowledge Base:** Hardcoded dataset covering 3 primary Baccalaureate tracks, 12 core/elective subject modules, and broad higher-education destination categories based on current public Egyptian Ministry of Education frameworks.

### Measurable Evaluation Metrics

| Metric Category         | Target Criterion                                                                                | Evaluation Method                                                |
| ----------------------- | ----------------------------------------------------------------------------------------------- | ---------------------------------------------------------------- |
| **System Transparency** | $\ge 85\%$ of test users correctly explain _why_ the AI recommended a specific pathway.         | Structured post-task interview with 15 test students.            |
| **User Agency**         | $\ge 90\%$ of users successfully adjust weights or edit inputs to explore alternative pathways. | Observational task success rate during user testing.             |
| **Factual Safety**      | 0 unflagged claims regarding official Ministry exam policies or entry requirements.             | Red-teaming audit of 50 standard guidance prompts.               |
| **Interface Usability** | System Usability Scale (SUS) score $\ge 78/100$.                                                | Post-test SUS survey administered to Grade 9 pilot participants. |

---
