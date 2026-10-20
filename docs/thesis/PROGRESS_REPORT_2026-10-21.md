# Progress report — 21 October 2026

Leveraging Large Language Models for Automated Diagnosis of CI/CD Pipeline
Failures. Fahid Khan, Tampere University. Supervisors: Jussi Rasku, Md Mahade
Hasan.

This records what has been built, what has been found, which research questions
changed and why, and what remains. It covers the period since the kickoff
meeting of 21 September 2026, and in particular the three weeks to 21 October.

**AI assistance.** The tooling in this project and the wording of this document
were produced with AI assistance. Methodological decisions — repository
selection, the research-question revisions, the definition of an evidence line,
the decision not to use a second reviewer — were made by the author. No ground
truth was written, edited or suggested by a model at any point; that prohibition
is recorded in `AGENTS.md` and enforced by tests. Disclosed in the terms the
evaluation plan requires, including for working documents.

---

## 1. Where the study stands

| | |
| --- | --- |
| Cohort | `thesis_scrapy_vite_2026`: 131 raw logs, 81 eligible |
| Repositories | `scrapy/scrapy` (Python, pytest), `vitejs/vite` (JavaScript, Vitest) |
| Sampling frame | failed runs created `2026-09-03..2026-10-04` |
| Partitions | 11 development · 11 pilot · 31 held-out · 28 reserve |
| Ground truth | 11 of 53 annotated, all development, single annotator |
| Experiments | one paired development run, three conditions, no failures |
| Code | 170 offline tests, lint and type checks pass |
| Held-out run | **not started** — under methodology hold pending approval |

The apparatus is complete. The remaining work is annotation and writing.

---

## 2. What the system does

Five stages, each communicating through files and each checksummed, so any
stage can be re-run and audited independently.

1. **Collection** — downloads failed GitHub Actions run logs with provenance:
   the config's SHA-256, the resolved sampling window, a checksum per log.
2. **Triage** — applies the scope rules offline: cancelled runs, bot and
   maintenance automation, runs where no job executed, out-of-scope jobs
   (lint, docs, static analysis, administrative checks), umbrella jobs,
   duplicate error signatures and duplicate failure families.
3. **Split** — allocates whole *failure families* to development, pilot and
   held-out, keeping repositories proportional. A family never spans partitions.
4. **Annotation** — blind: no model output is ever shown. Produces the category,
   the root cause in prose, and the evidence lines.
5. **Experiment** — runs three conditions on byte-identical filtered input and
   scores them with one implementation of each metric.

The three conditions are a proprietary model (`openai/gpt-5.6-terra`), a locally
hosted open-weights model (`thesis-qwen3.5:9b-24k`), and a deterministic
keyword-and-pattern baseline whose ruleset is checksummed into every record.

---

## 3. How the research questions changed

The revised wording is in `EVALUATION_PLAN.md` §3, with the originals preserved
beside it in §3.2. **The revision has not yet been sent and needs supervisor
agreement**, particularly for SRQ2, which changed meaning rather than wording.

### Primary

**Was:** How effectively can an LLM-based diagnostic system identify failure
causes in CI/CD pipeline logs?

**Now:** How accurately can an LLM-based system identify the category of a CI/CD
pipeline failure and the log lines evidencing it, relative to a deterministic
rule-based baseline?

**Why.** Two problems. The original asked about failure *causes*, but the system
scores the *category* and the cited evidence lines, not free-text root cause
against the annotated one — a question broader than its measurement. And "how
effectively" had no referent, so any accuracy figure answered nothing. A
baseline now supplies the floor.

### SRQ1

**Was:** How does the diagnostic performance of an LLM-based system differ when
using a proprietary LLM versus an open-weights model?

**Now:** Under identical preprocessed input, how does the diagnostic performance
of a proprietary LLM differ from that of a locally hosted open-weights model,
and at what difference in cost and latency?

**Why.** The local model's 24,576-token context sets the preprocessing budget
for *both* conditions — at the largest observed prompt there were 485 tokens of
headroom. The study therefore compares two models under one deployable
configuration, not each at its best, and the original wording would have
overclaimed past that. Cost and latency are named because they were measured.

### SRQ2

**Was:** Which categories of CI/CD failures is the LLM-based diagnostic system
most and least effective at diagnosing?

**Now:** Which properties of a CI/CD failure log and its pipeline configuration
determine whether the system can diagnose the failure?

**Why.** The cohort cannot answer the original. **78 of 81 eligible cases fail
in a test-execution step**, all eleven annotated development cases are
`test_failure`, and six of the eight categories have no development example. A
per-category F1 over one case is not a finding.

**Why the timing is defensible.** The category distribution is known from triage
and the repository inclusion gate, and **neither involves any model output**.
The revision is made before the held-out run, on evidence about what the cohort
contains. Reformulating after seeing held-out results would not be defensible,
and is not being requested. The alternative, if the questions should not move,
is to keep SRQ2 and answer it only for the categories present, reporting the
rest as not evaluable.

---

## 4. What was found

### 4.1 The preprocessing boundary is about position, not size

The strongest result in the project, and it was found by measuring rather than
assuming.

A stored GitHub Actions run log is a ZIP of one file per job, concatenated under
`=== name ===` headers. A scrapy run produces around eighty sections and **ends
with the runner's own `*/system.txt` files**. The filter kept the last 500
keyword-matching lines, which therefore landed in system logs while the failure
sat in the middle of the archive.

Measured over the eleven annotated development cases:

| stage | mean preprocessing recall | cases losing all evidence |
| --- | --- | --- |
| whole archive, tail heuristic | 4% | 10 of 11 |
| scoped to the failing job | 80% | 0 of 11 |
| terminal escape codes stripped | **91%** | 0 of 11 |

Seven of eleven are now fully preserved. The initial hypothesis — that large
logs defeat the filter — was wrong: vite logs under 5,000 lines lost everything
too. Position was the cause.

### 4.2 Umbrella jobs are not diagnosable, and that is a construct problem

A job that aggregates many independent checks reports many independent failures
under one name, so it has no single root cause and the ground truth would be
ambiguous to a human annotator as well as to a model. In `gradle/gradle`, **25
of 25 umbrella-job cases exceeded 40,000 lines and lost all evidence, while 0 of
11 single-purpose jobs did**. Triage now excludes them on construct-validity
grounds.

### 4.3 JVM monorepo CI is intractable for this approach

Five JVM candidates were measured and none is usable: `netty/netty` at 1,324,878
lines on its one genuine CI sample, `apache/dubbo` at 3.5M, `micronaut-core` at
53,574, `mockito/mockito` at 26,650 with most logs already expired. Large JVM
projects build and test every module in one job — the same structure that made
gradle unusable. This bounds where the artifact applies and is reported as a
finding rather than a limitation.

### 4.4 Both models beat fixed rules; one beats the other clearly

Development set, eleven cases, three conditions:

| condition | category | evidence-line F1 |
| --- | --- | --- |
| keyword rules | 2/11 | 0.01 |
| `local/thesis-qwen3.5:9b-24k` | 11/11 | 0.34 |
| `openai/gpt-5.6-terra` | 11/11 | 0.66 |

Paired Wilcoxon on per-case evidence-line F1: **the hosted model ahead in 11 of
11 cases, p = 0.0010, mean difference +0.33**.

Both models are precise and incomplete — what they cite is usually genuine
evidence, but they mark a fraction of the annotated span. The local model's
deficit is almost entirely recall, 0.23 against 0.56, with precision holding at
0.78.

**Why the baseline fails is itself informative.** It answered `permission_denied`
six times because its rules match the bare string `"403"` and the word
`"forbidden"`, which appear incidentally in test output. A keyword matcher
cannot distinguish a failure from a mention of one. That is precisely the
discrimination the thesis claims an LLM provides, and it can now be
demonstrated.

### 4.5 Cohorts are a point-in-time sample

GitHub removes a run from its failure listing once it has been re-run
successfully, and expires logs at around 90 days. A cohort cannot be
re-collected. This is why raw logs and checksums are preserved and why the
sampling frame is recorded as absolute dates.

### 4.6 Repair traceability depends on the sampling window

A repair is found by looking for a later passing run on the same branch, so it
needs elapsed time. Sampling the newest failed runs — the default — gives the
least traceability:

| window | vitejs/vite | scrapy/scrapy |
| --- | --- | --- |
| 0–7 days old | 5/20 | 11/20 |
| **14–45 days old** | **10/20** | **17/20** |
| 45–80 days old | 8/20 | 4/20 |

The cohort is drawn from the 14–45 day window accordingly. This roughly doubles
the share of cases whose annotation can be checked against a documented repair,
which matters more now that there is no second reviewer.

---

## 5. Defects found and corrected

Each is covered by a test naming the decision it protects.

| Defect | Consequence | Status |
| --- | --- | --- |
| Filter kept the head, then the tail, of a multi-job archive | Every verified evidence line discarded in 10 of 11 cases | Fixed: scoped to the failing job's section |
| Terminal escape codes never stripped | One prompt reached 24,246 tokens against a 12,000 budget; recall suppressed | Fixed: stripped per line, budget now a hard invariant |
| `compute_error_signature` ignored commit SHAs, elapsed times and parallel-build ordering | One fault entered the cohort **19 times**, spanning development (3), pilot (2) and held-out (9) | Fixed: normalised; cohort re-triaged and re-split |
| Evidence line numbers read in a job's local frame | Six annotations recorded against the wrong matrix entry | Fixed: annotator prints the failing job's line range; cases redone |
| Statistical test ran only on category accuracy | Reported the two models as "identical" (p = 1.0) where they differ at p = 0.001 | Fixed: paired test on evidence-line F1 added |
| `is_bot_run` lived in `tools/`, invisible to triage | 45 bot runs reached an eligible cohort | Fixed: moved to shared scope module |
| Static-analysis jobs classified as in-scope | mypy jobs admitted because `"check"` matched | Fixed: excluded; cohort re-triaged |
| Held-out partition absorbed all surplus cases | A 77-case held-out set from a target of 30 | Fixed: explicit reserve bucket, outside the confirmatory analysis |

Two predictions of mine were wrong and are recorded as such in `CONTEXT.md`:
narrowing the evidence-line definition did **not** raise the models' scores, and
the baseline did **not** saturate category accuracy. Both corrections are in the
project's favour.

---

## 6. Methodological decisions taken

| Decision | Date | Basis |
| --- | --- | --- |
| `django/django` replaced by `scrapy/scrapy` | 18 Oct | 15 of 18 cases were PR-metadata checks; no build or test ran |
| `gradle/gradle` replaced by `vitejs/vite` | 18 Oct | 25 of 36 cases were umbrella jobs; ~6 diagnosable cases remained |
| Ecosystem contrast is Python/JavaScript, not Python/JVM | 18 Oct | No JVM candidate tractable across five measured projects |
| Cohort sampled from a 14–45 day age window | 18 Oct | Repair traceability roughly doubles |
| Partition targets 10/10/30 with an explicit reserve | 18 Oct | Annotation capacity; a held-out set larger than can be annotated is undefined |
| No second reviewer | 18 Oct | Author's decision; substitutes in §7 |
| Evidence lines defined narrowly | 21 Oct | Recall was measuring the annotator's marking style as much as the models |
| Evidence belongs to the job in `failing_job` | 21 Oct | Triage, the filter and the scoring all key on it |
| Filter scoped to the failing job's section | 21 Oct | Recall 4% → 80% |
| Baseline runs as a third condition | 21 Oct | The primary question is worded relative to it |

---

## 7. Ground truth with a single annotator

Independent verification was a supervisor condition and will not be met. This is
disclosed rather than omitted, with four substitutes:

1. **Documented repair as the anchor.** In the chosen window roughly 85% of
   scrapy and 50% of vite cases have a findable repair, so for most of the
   cohort the ground truth rests on an artefact the projects' own developers
   produced. Accuracy will be reported separately for repair-anchored and
   judgement-only cases; if the two are close, that is evidence the annotation
   is not driving the result.
2. **Blind annotation**, already implemented — no model output is ever shown.
   This closes contamination, not reliability; the two are not conflated.
3. **Intra-rater re-annotation** of a subset after a gap, reported as
   self-consistency and explicitly not as inter-rater agreement. **Kappa is not
   yet implemented.**
4. **A written codebook** plus publication of the full annotation set with
   checksums, so a reader can check labels against stated rules.

**What cannot be claimed:** inter-rater reliability, or that the ground truth is
independently verified.

**Why the revised questions tolerate this.** SRQ1 is a paired contrast, so any
labelling bias applies to both models and cancels. SRQ2 as reworded rests on
mechanically measured log properties. The primary question is the exposed one,
which is where the baseline earns its place: a relative claim survives weak
ground truth far better than an absolute one.

---

## 8. What remains

**Blocking the held-out run**

- The evaluation plan has not been sent. `./run_workflow.sh final` is under
  methodology hold until the approach is approved.
- No freeze record exists.
- 42 cases remain unannotated (11 pilot, 31 held-out).

**Supervisor conditions: 2 of 11 addressed** (R2, R5). Three partial, six
outstanding — mostly reviewer-procedure items that the single-annotator decision
reshapes rather than removes.

**Outstanding commitments**

- Root-cause and suggested-fix quality scoring (rubric) — not implemented.
- Cohen's kappa — not implemented; needed for the intra-rater check.
- Controlled defects — not started. Only needed if the taxonomy question is
  answered by widening categories rather than narrowing them.

---

## 9. What is next, in order

1. **Send the evaluation plan.** It gates everything downstream, and SRQ2's
   rewording needs explicit agreement.
2. **Read and revise the codebook.** It is the annotation standard and, with no
   second reviewer, the defence for the ground truth.
3. **Annotate the 11 pilot cases** (~3 hours).
4. **Run the paired experiment on pilot**, as the dress rehearsal for a held-out
   run that happens once.
5. **Annotate the 31 held-out cases** (~8 hours).
6. **Create the freeze record**, then run the held-out experiment after approval.
7. **Write up.**

Steps 1 and 2 are the gate. Steps 3 and 5 are roughly 11 hours of log reading
and cannot be parallelised or delegated.

---

## 10. Assessment

The apparatus is complete and the engineering risk is largely retired. The
remaining risk is calendar: 42 annotations, a document to write, and 19 days.

The centre of gravity has shifted. The model comparison is thinner than planned
— a single failure category, a small sample, a local model that underperforms
clearly. The **artifact characterisation is strong**: where this approach works,
where it fails, and why, measured across two ecosystems and five rejected
projects. For a Design Science thesis that is a legitimate contribution, and
weighting the report toward it is honest rather than a retreat.

The most useful single sentence the project has produced is that an LLM-based
log diagnosis system is bounded not by model capability but by whether
preprocessing delivers the evidence at all — and that this depends on where the
failure sits in the log, not how large the log is.
