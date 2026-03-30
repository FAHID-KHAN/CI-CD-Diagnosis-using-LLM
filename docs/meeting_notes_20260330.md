# Meeting Notes — 30 March 2026

**Meeting:** Thesis Meeting — Fahid Khan  
**Participants:** Fahid Khan, Jussi Rasku (supervisor), Mahade Hasan (advisor)  
**Duration:** ~33 minutes  
**Previous meeting:** 11 March 2026  

---

## 1. Research Questions — Must Be Testable & Specific

### Core feedback

**Jussi's main message:** RQs must be answerable through experiments that produce tables and numbers.

> "You need to think so that research questions are answerable… you can do something to answer those questions… run some experiments to answer those questions and know just how well."

**Mahade & Jussi feedback on current RQs:**
- Replace vague terms like *"interpret"* with more precise, measurable language
- Break down broad RQs into smaller, specific sub-questions that map to concrete experiments
- Each RQ should steer towards a **comparison-type experiment**

> "If you use that, it steers towards making some kind of comparison type of experiment."

### Alternative RQ formulations proposed by supervisors

| Focus Area | Suggested Direction |
|------------|-------------------|
| LLM performance | How well do proprietary LLMs perform in analyzing CI/CD pipeline logs? |
| Error identification accuracy | How accurately can LLMs identify error types in CI/CD failure logs? |
| Preprocessing impact | What is the impact of preprocessing techniques (filtering, truncation) on diagnosis accuracy? |
| Model comparison | How do different LLMs (proprietary vs open-source) compare on the same diagnosis task? |

**Decision:** Fahid to revise RQs based on this feedback and **send updated set via email** before next meeting.

---

## 2. Seed Known Defects as Ground Truth

**Jussi's suggestion for building rigorous experiments:**

> "Interpretation of these pipeline logs where you potentially seed some kind of known defects or you have the ground rules, and then you can run the kind of computational experiments and get some kind of tables and numbers out of that to answer the actual question."

Two approaches:
1. **Seed known defects** — Inject known failure patterns into CI/CD logs and test if each LLM correctly identifies them (controlled experiment)
2. **Ground rules** — Manually annotated real-world logs with verified root causes (observational study)

---

## 3. Technical Workflow & Tool Demo

Fahid walked through the current tool and pipeline. Supervisors acknowledged the progress and provided alignment feedback.

### What was demonstrated

| Component | Description | Supervisor Feedback |
|-----------|-------------|-------------------|
| **Data collection** | Logs collected from 17 public GitHub repos via Actions API | Solid foundation |
| **Preprocessing** | Duplicate removal, noise filtering, triage by priority | Align with RQ about preprocessing impact |
| **LLM-based analysis** | Logs sent to LLM API in batches → error type, root cause, fix | Core empirical work — needs multi-model comparison |
| **Evaluation (dual)** | (1) LLM self-assessment via grounding check, (2) human annotation with scoring | Ensure evaluation directly addresses finalized RQs |

### Supervisor guidance on alignment

- Tool workflow and evaluation must **directly address the finalized RQs**
- Accuracy measurement needs to be clearly defined (what counts as "correct"?)
- Preprocessing role should be measurable (ablation: with vs without filtering)

---

## 4. Document Sharing & Logistics

### OneDrive issues
- Fahid reported difficulties sharing thesis folder via OneDrive (institutional access restrictions)
- IT support contacted but not resolved yet

### Agreed workaround
- **Email attachments are acceptable** — send static document snapshots for review
- Jussi: sharing static versions is better than constantly updated files for review purposes

---

## 5. Next Steps & Follow-up Tasks

### Fahid's action items (before next meeting)

| Task | Priority | Deadline |
|------|----------|----------|
| **Revise research questions** — incorporate supervisor feedback (specific, testable, comparison-oriented) | 🔴 High | Before next meeting |
| **Email updated RQs** to Jussi and Mahade for feedback | 🔴 High | ASAP |
| **Send thesis document** as email attachment (current version) | 🟡 Medium | This week |
| **Design experiment matrix** — models × datasets × metrics | 🔴 High | This week |
| **Create seeded test set** — 20-30 synthetic logs with known defects | 🟡 Medium | Next 2 weeks |
| **Annotate real-world logs** — build ground truth for 50+ logs | 🟡 Medium | Ongoing |
| **Install Ollama + run benchmark** across multiple models | 🟡 Medium | This week |

### Scheduling
- Next meeting to be coordinated **after** RQs are finalized and shared via email
- Asynchronous communication preferred — send updates by email, supervisors review at their pace

---

## How This Maps to Current Implementation

| Supervisor Direction | What We Have | What's Needed |
|---------------------|--------------|---------------|
| Testable comparison experiments | Multi-LLM benchmark script, Ollama support | Run benchmark on 50+ logs across 3+ models |
| Specific RQs | Broad RQs from March 11 | Rewrite with precise language, map each to an experiment |
| Seed known defects | — | Create synthetic logs with known failure types |
| Ground rules (annotated data) | Annotation pipeline (`make annotate`) | Annotate 50+ real logs |
| Preprocessing impact | Token-aware filtering, smart truncation | Ablation study: diagnosis with vs without filtering |
| Tables and numbers | Evaluation framework (`make evaluate`) | Generate comparison tables, confusion matrices |
| Accuracy measurement | Grounding verification, confidence scores | Define what "correct" means for each metric |

---

## Proposed Revised Research Questions (Draft)

Based on supervisor feedback, here is a starting point for revision:

| | Research Question | Experiment | Key Metrics |
|---|---|---|---|
| **RQ1** | How accurately can LLMs identify error types and root causes in CI/CD pipeline failure logs? | Run multiple LLMs on annotated log set, compare output vs ground truth | Error type accuracy, root cause F1, confidence calibration |
| **RQ2** | How do proprietary LLMs compare to open-source LLMs for CI/CD failure diagnosis? | Benchmark GPT-4o-mini vs Llama3 vs Mistral on identical logs | Per-model accuracy, speed, cost, error-type coverage |
| **RQ3** | What is the impact of log preprocessing on LLM diagnostic accuracy? | Ablation: raw logs vs filtered vs token-truncated | Accuracy delta, grounding score delta |

*These are drafts — to be refined by Fahid and sent to supervisors for approval.*

---

## Supervisor Quotes (For Reference)

**Jussi Rasku:**
- *"You need to think so that research questions are answerable."*
- *"It steers towards making some kind of comparison type of experiment."*
- *"Seed some kind of known defects or you have the ground rules, and then you can run the kind of computational experiments and get some kind of tables and numbers."*
- *"Start building an experiment on that so that you can actually answer on how well those."*

---

*Next step: Revise RQs → email to supervisors → design experiment matrix → run benchmarks.*
