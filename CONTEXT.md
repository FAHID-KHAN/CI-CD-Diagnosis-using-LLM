# Project context

What this repository is, where it stands, and what has already been decided.
Read this before changing anything.

## What this is

A master's thesis tool (Fahid Khan, Tampere University). It collects failed
GitHub Actions logs, has a human label the real cause of each failure, then runs
two LLMs over the same cases and compares them.

- **Proprietary condition:** `openai/gpt-5.6-terra`
- **Open-weights condition:** `local/thesis-qwen3.5:9b-24k` via Ollama

Both conditions get identical filtered log text, prompt, response schema and
reasoning effort. Only the model differs. Everything else in the repository
exists to make that comparison trustworthy.

Supervisors: Jussi Rasku, Md Mahade Hasan. Thesis seminar: 9 November 2026.

## Current state

| | |
| --- | --- |
| Code | Complete. 70 tests, lint and type checks pass. |
| Study data | Empty. `data/studies/` was cleared on 22 September 2026. |
| Active config | `configs/thesis_pair_2026.yaml` — django/django and gradle/gradle |
| Blocked on | Supervisor approval of the evaluation method |

Check the live state at any time:

```bash
./run_workflow.sh status
```

## The methodology hold

The kickoff meeting on 21 September 2026 stopped empirical work until the
evaluation method is approved. **Do not run `./run_workflow.sh final` for thesis
evidence until that approval exists.** The roadmap in `docs/thesis/` defines the
gate.

Decisions from that meeting that constrain the code:

- **D2** — start with two contrasting repositories, not six.
- **D3** — the researcher's own judgement cannot be the sole basis for accuracy
  claims. Ground truth needs documented historical fixes, seeded defects, or an
  independent expert. LLM-as-judge is a last resort and must be disclosed.
- **D4** — development, pilot and final cases must be disjoint. The system is
  frozen and evaluated once on unseen cases.
- **D5** — report results per failure category.
- **D6** — categories and metrics justified from literature before the main run.

## What was measured, and why it matters

These numbers came from the collected data and drive several open decisions.

**Log size varies by three orders of magnitude, and the filter saturates.**
Above roughly 3,000 lines the model receives a fixed 12,000-token window
regardless of log length:

| repository | median lines | share the model receives |
| --- | ---: | ---: |
| django/django | 256 | 24.2% |
| gradle/gradle | 2,526 | 10.0% |
| facebook/react | 48,815 | 0.6% |
| rollup/rollup | 34,422 | 0.8% |

**Short logs are lint jobs.** Every repository measured is bimodal: short
static-analysis failures, and a long tail of build and test failures. Selecting
repositories by log size therefore selects away the interesting failures.

**The taxonomy is under-exercised.** A first annotation pass over 12 django cases
populated three of eight categories. `dependency_error`, `test_failure`,
`timeout`, `permission_denied` and `network_error` never occurred.

**Grounding is not accuracy.** The grounding score only checks that a cited line
exists in the extract the model was given. In a five-case pilot it read 97.5%
while evidence-line F1 against annotated lines was about 6%. Report them
separately.

**Cost and time.** Proprietary: 19.4 s and USD 0.038 per case. Open-weights:
17.4 minutes per case, no API cost. A 26-case cohort means roughly 7 hours of
local inference.

## Things that surprised us

- **Cohorts cannot be re-collected.** GitHub drops a run from its failure
  listing once it is re-run successfully. A cohort is a point-in-time sample.
  This is why raw logs and checksums are preserved, and why re-collecting gave
  entirely different django cases hours later.
- **A truncated `statistical_tests.json`** (written per experiment) was caused by `json.dump` hitting a
  NumPy `bool_`. The `float()`/`bool()` normalisation in
  `src/evaluation/evaluation.py` is the fix.
- **Short logs are often bot-generated.** junit5 looked tractable at a 179-line
  median until Dependabot runs were excluded; its real CI failures are 28,235
  lines.

## Open decisions

Six, listed in `docs/thesis/EVALUATION_PLAN.md` §10. The ones that block
annotation:

- Keep eight failure categories and widen the data, or cut the categories down.
- Score root-cause correctness with a rubric, or narrow the primary research
  question to categories and evidence lines.

Two commitments made to supervisors that are not implemented: a **rule-based
baseline**, and **root-cause / suggested-fix quality scoring**.

## Where to look

| Path | What |
| --- | --- |
| `docs/thesis/ACTION_ITEMS.md` | What to do next, in order |
| `docs/thesis/EVALUATION_PLAN.md` | The plan to send to supervisors |
| `docs/architecture/CONTROLLED_STUDY_RUNBOOK.md` | Exact operating procedure |
| `docs/architecture/architecture.png` | The system in one picture |
| `docs/archive/` | Superseded. Describes RAG, ChromaDB and models that are gone |
