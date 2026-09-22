# Meeting Notes — 11 March 2026

**Meeting:** Thesis Meeting — Fahid Khan
**Participants:** Fahid Khan, Jussi Rasku (supervisor), Mahade Hasan (advisor)
**Duration:** 43 minutes
**Next meeting:** 25 March 2026

---

## 1. Research Questions — Refinement Needed

### Current state

| | Question | Status |
|---|---|---|
| **Primary RQ** | How effectively can LLMs automate the diagnosis of CI/CD pipeline failure causes and assist developers? | Approved |
| **Sub-RQ1** | How well can LLMs interpret CI/CD pipeline logs to identify underlying causes of failures? | Approved — close to primary RQ, straightforward |
| **Sub-RQ2** | How feasible is it to integrate an LLM-based diagnostic system into CI/CD tools (Jenkins, GitHub Actions) in real-world scenarios? | **Problematic — needs rework** |

### The RQ2 problem

Both Jussi and Mahade agreed: **just implementing the integration does not prove feasibility.** To answer a feasibility question, you need:

- **Risk identification** — What could go wrong when integrating LLM diagnosis into a CI/CD pipeline?
- **Challenge categorisation** — Systematic mapping of technical, operational, and cost challenges
- **Mitigation strategies** — How each risk can be addressed
- **Metrics** — Measurable criteria that define "feasible" (e.g., latency, cost per diagnosis, false positive rate)
- Possibly a **developer experience** component

Jussi shared an IEEE article on feasibility studies and recommended searching Google Scholar for academic feasibility study methodologies in software engineering.

### Two options for RQ2

| Option | RQ2 Formulation | What it requires |
|---|---|---|
| **A: Feasibility study** (preferred by both supervisors) | "How feasible is it to integrate LLM-based diagnosis into CI/CD pipelines?" | Risk analysis, challenge mapping, effort estimation, developer perspective |
| **B: Comparative analysis** (fallback) | "How do different LLMs compare in diagnosing CI/CD pipeline failures?" | Multi-model experiments (open-source vs proprietary), accuracy comparison |

**Decision:** Try Option A first. Fall back to Option B if feasibility study proves too difficult.

---

## 2. Multi-LLM Comparison (Required Regardless of RQ2)

Mahade was clear: **using only one GPT model has no novelty.** *"You can do it with ChatGPT as well — there is no novelty."*

Regardless of which RQ2 direction is chosen, the evaluation must include **multiple LLMs**:

- At least one **proprietary model** (e.g., GPT-4o-mini, GPT-4o)
- At least one **open-source model** (e.g., Llama 3, Mistral, Mixtral)
- Compare diagnostic accuracy, confidence calibration, error type coverage, and cost

This satisfies RQ1 (which LLM performs better at diagnosis) and provides data for either RQ2 formulation.

---

## 3. Evaluation Design

Mahade framed the evaluation: *"You have a question, you write your answers, the teacher checks it against the correct answers."*

### Required components

1. **Golden standard (ground truth)** — Created by a domain expert (you). For each log: correct error type, root cause, and recommended fix.
2. **LLM output** — The system's diagnosis for the same log.
3. **Evaluation criteria** — Metrics to compare LLM output against ground truth:
   - Error type accuracy
   - Root cause correctness (exact match, partial, incorrect)
   - Usefulness rating (would this help a developer?)
   - Confidence calibration (does the model know when it's wrong?)
4. **Baseline comparison** — Regex-based and heuristic baselines already exist in the pipeline.

---

## 4. Current Progress Acknowledged

Both supervisors confirmed these are done and solid:

| Step | Status |
|---|---|
| Log pruning/filtering (keyword-based, context windows) | Done |
| Context enrichment (repository, workflow, CI system metadata) | Done |
| Single-LLM diagnosis pipeline | Done |
| Basic evaluation framework | In place, needs refinement |

Mahade: *"Now LLM has a clear context."*

---

## 5. Thesis Writing Guidance

### Template and tools

- **Template:** TAU ITC CS template (2019) — confirmed correct by Jussi
- **Bibliography:** Use **Zotero** (TAU-recommended) or Mendeley. Install browser plugin + Word plugin.
- **OneDrive:** Share thesis folder with Jussi and Mahade. Put the link in the calendar invite.

### Writing order (from Jussi)

Do NOT write start-to-end. Recommended order:

1. **Empirical work** — Describe the artefact, experiments, results
2. **Research methods** — DSR methodology, evaluation design
3. **Background/Theory** — Related work, CI/CD concepts, LLM background
4. **Introduction** — Frame the research gap, motivation, RQs
5. **Discussion** — What do results mean? Comparison to prior work
6. **Conclusions** — So what? Who should care?
7. **Abstract** — Write this LAST

### Writing approach

**Literate programming style:** Outline each section in plain language first (*"here I will discuss X, then I will show Y"*) before writing academic text. Keeps focus on what each paragraph communicates.

**Abstraction U-shape:**

```
Introduction  ████████████████  (general — motivation, gap)
Background    ██████████████    (moderately specific)
Methods       ████████████      (detailed)
Results       ████████          (very specific — just report facts)
Discussion    ████████████      (back to moderately general)
Conclusions   ████████████████  (general — so what?)
```

Same pattern applies within chapters and within paragraphs: first sentence = topic (general), middle = details (specific), last sentence = bridge to next paragraph (general).

### AI usage warning

Jussi: *"AI has this tendency to produce something that superficially looks like academic text, but then it lacks the coherence and clarity of thought."* Every sentence must carry meaning.

---

## 6. Administrative Actions

- [ ] Set up **OneDrive** folder, share with Jussi and Mahade
- [ ] Install **Zotero** (browser plugin + Word plugin), start collecting papers
- [ ] Send **calendar invite** for March 25 meeting with:
  - Agenda / questions to discuss
  - Link to OneDrive folder with thesis draft
- [ ] Prepare a **loose agenda** and questions before each meeting going forward

---

## 7. Task Checklist

### Before next meeting (March 25)

- [ ] Research feasibility study methodology (Google Scholar, IEEE)
- [ ] Draft revised RQ2
- [ ] Identify 2–3 open-source LLMs for comparison experiments
- [ ] Set up Zotero and start collecting papers
- [ ] Set up OneDrive, share with supervisors
- [ ] Send calendar invite with agenda + OneDrive link
- [ ] Start writing the empirical/artefact chapter (describe the system, pipeline, filtering)

### Near-term

- [ ] Run multi-LLM experiments on the same log set
- [ ] Create golden standard annotations (domain expert evaluation)
- [ ] Design and execute full evaluation
- [ ] Research and draft feasibility analysis (if pursuing Option A for RQ2)

### Ongoing

- [ ] Continue thesis writing following the recommended order
- [ ] Collect and organise papers in Zotero
