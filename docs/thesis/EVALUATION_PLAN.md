# Evaluation Plan

**Leveraging Large Language Models for Automated Diagnosis of CI/CD Pipeline Failures**

Fahid Khan · Master's thesis, Tampere University
Supervisors: Jussi Rasku, Md Mahade Hasan
Prepared for the supervision review following the kickoff meeting of 21 September 2026

---

## 1. Purpose of this document

The kickoff meeting concluded that the prototype is sufficiently advanced to move
from tool construction to research evaluation, and that a defensible ground truth
and a genuinely held-out test design are the two release-blocking requirements.
This document responds to that.

It sets out how the evaluation will be conducted: how cases are selected, how
ground truth is established, which categories and metrics are used, how
development and final data are kept apart, and when the system is frozen.

**I am asking you to approve or redirect six decisions**, listed in Section 10.
The rest of the document is my proposal and the evidence behind it. Two inputs
are still in progress and are noted where they affect a choice: the focused
literature review, and the feasibility check on whether repository history
documents the repairs for failed runs.

No final evaluation data will be collected until this plan is approved.

## 2. Summary of the proposed approach

| | |
| --- | --- |
| **Unit of analysis** | One failed GitHub Actions workflow run |
| **Case selection** | Build and test jobs only; static-analysis, formatting, documentation and commit-message jobs excluded |
| **Ground truth** | Documented historical repair where available; otherwise blind annotation with an independent second reviewer and written adjudication |
| **Repositories** | Two contrasting projects; `django/django` proposed as one, the second contingent on the traceability check |
| **Conditions** | One proprietary model, one open-weights model, and a deterministic keyword baseline |
| **Primary metrics** | Failure-category accuracy and macro F1; evidence-line precision and recall; diagnostic completion rate |
| **Design** | Three disjoint partitions; the system is frozen and the final set evaluated once |

## 3. Research questions

**Primary.** How effectively can an LLM-based diagnostic system identify failure
causes in CI/CD pipeline logs?

**SRQ1.** How does the diagnostic performance of an LLM-based system differ when
using a proprietary LLM versus an open-weights model?

**SRQ2.** Which categories of CI/CD failures is the LLM-based diagnostic system
most and least effective at diagnosing?

One qualification, which is decision (e) in Section 10. The primary question asks
about failure *causes*. The system currently scores the failure *category* and the
log lines the model cites as evidence; it does not score the free-text root cause
against the annotated one. Scoring root-cause correctness properly requires a
written rubric applied by both reviewers, which roughly doubles the annotation
effort per case.

My proposal is to treat category accuracy and evidence-line accuracy as the
measured components of cause identification, to report root-cause and
suggested-fix text qualitatively rather than as an accuracy claim, and to word the
primary question to match. I would rather narrow the claim than make one the
evidence cannot support.

## 4. Case selection

Repository-level selection by log size was investigated and rejected. Sampling
recent non-bot failed runs from eleven candidate repositories (Appendix A) shows
that **no repository produces uniformly small logs**. Every candidate is bimodal:
short static-analysis failures, and a long tail of build and test failures.

The reason matters for the study. Short logs are short because they come from
lint, formatting, spell-check and commit-message jobs. Dependency resolution
failures, test failures and timeouts occur in build and test jobs, which are long
by nature. Selecting repositories by log length therefore selects away the
failures the thesis is most interested in.

Selection will instead operate on cases, using two criteria that are observable
before any diagnosis is made:

**Pipeline stage.** Include failures in build and test jobs. Exclude
static-analysis, formatting, documentation and commit-message jobs. Classification
is from the failing step's command — `pytest`, `gradle build`, `npm test` against
`flake8`, `prettier --check` — rather than the workflow name, which is
inconsistent across projects.

**Documented repair.** Prefer cases where repository history shows the fix. This
is a proxy for practical significance, since a maintainer judged the failure worth
repairing, and it simultaneously supplies the strongest class of ground truth
(Section 5).

Cases will **not** be selected by their predicted failure category. Doing so would
make the cohort a function of the classifier under evaluation and would invalidate
the baseline comparison.

**Repositories.** `django/django` is proposed as one member: it has the shortest
median log of the candidates measured and was the only one whose recent failures
contained no bot-generated noise. The second member matters less once selection
operates on cases; `gradle/gradle` gives contrast on language, build tool and log
convention while remaining tractable to annotate. This pairing is contingent on
the traceability check, which may rule out a repository that looks suitable on
log length alone.

## 5. Ground truth

Evidence hierarchy, strongest first:

1. **`historical_fix`** — the failing revision linked to a documented fixing
   commit, pull request or issue.
2. **`seeded_defect`** — a recorded injected change with a known cause and repair.
3. **`expert_review`** — annotation supported by repository evidence.
4. **`combined_adjudicated`** — a documented combination with adjudication rules.

LLM-as-judge is not part of this plan. If it becomes unavoidable it will be
separated from the accuracy claims and reported as a validity limitation.

**Procedure.** Annotation runs in two blind passes. The first reviewer reads a
line-numbered log with no model output visible and records the failure category, a
written root cause, the supporting line numbers, and the evidence method with its
reference. A second reviewer, who must not be the first, labels the same case
without seeing the first answer. The two labels are then compared, and every
disagreement requires a written adjudication before the case is accepted. Raw
agreement before adjudication is reported as the inter-rater measure.

A case is rejected if it has no evidence method, no independent verifier, an
unusable root cause, or an evidence method whose reference is missing. This is
enforced in the tooling rather than left to discipline.

**What is already known.** A first annotation pass over twelve `django` cases
produced only `expert_review` evidence, with me as the sole reviewer. That is the
evaluator-bias risk raised at the kickoff, and it is why the traceability check
matters: it determines how much of the cohort can rest on documented repairs
rather than on my judgement.

## 6. Failure taxonomy

The response schema currently declares eight categories: `dependency_error`,
`test_failure`, `build_configuration`, `timeout`, `permission_denied`,
`syntax_error`, `network_error`, `unknown`.

The twelve annotated `django` cases populated three of them —
`build_configuration` (6), `syntax_error` (3), `unknown` (3). Five never occurred:
`dependency_error`, `test_failure`, `timeout`, `permission_denied`,
`network_error`. This follows directly from those cases being static-analysis
failures, and it is the strongest single argument for stage-based selection.

My proposal is to adopt stage-based selection so that build and test failures
enter the cohort, then fix the taxonomy from what the development partition
actually contains, justified against published CI/CD failure classifications.
Categories that cannot occur in the cohort will be removed rather than reported as
zero. Retaining eight categories while five are unreachable is not defensible.

## 7. Partitions and held-out procedure

Three disjoint partitions, fixed before any prompt, filter or taxonomy
refinement:

| Partition | Purpose | May influence the system | Used in final claims |
| --- | --- | ---: | ---: |
| Development | Refine filtering, prompt, taxonomy, baseline | Yes | No |
| Pilot | Verify the frozen pipeline end to end | No | No |
| Final held-out | One-time evaluation | No | Yes |

Partitioning is by underlying defect rather than by run identifier, so that reruns
and duplicate manifestations of the same fault cannot leak between sets. The
allocation is stored in a versioned manifest with a fixed seed and case checksums.

This is enforced in the tooling: the benchmark refuses to run a held-out
evaluation over any case an exploratory cohort has already used, and triage
excludes such cases with a recorded reason. An override exists, records a written
justification, and is not used for thesis evidence.

## 8. Metrics and analysis

Pre-registered before the final run.

**Primary.** Failure-category macro F1, with per-category precision, recall, F1
and support; exact category accuracy; evidence-line precision, recall and F1
against the annotated supporting lines; diagnostic completion rate, with inference
failures counted as incorrect rather than excluded.

**Secondary.** Grounding score, hallucination rate, latency, token use, estimated
cost.

**Reported but not scored.** Root-cause and suggested-fix text, presented
qualitatively with representative examples, subject to decision (e).

Two metrics are reported separately and must not be conflated. The **grounding
score** checks only that a line the model cited exists in the extract it was
given; it never consults ground truth. **Evidence-line accuracy** compares the
model's cited lines with the annotated ones. In a five-case pilot these diverged
sharply — 97.5% grounding against approximately 6% evidence-line F1 — which is
precisely why both are reported.

**Analysis.** Both conditions diagnose the same cases, so comparison uses paired
methods: McNemar's test, a paired permutation test, and bootstrap confidence
intervals. Per-category support counts accompany every per-category result.

I would value your guidance on statistical power. At the cohort sizes that
annotation effort permits (Section 9), the number of discordant pairs may be small
enough that significance testing is uninformative, in which case reporting effect
sizes with confidence intervals would be the honest presentation.

## 9. Conditions, baseline, and practical limits

| Condition | Model | Access |
| --- | --- | --- |
| Proprietary | `openai/gpt-5.6-terra` | API |
| Open-weights | `local/thesis-qwen3.5:9b-24k` | Ollama, fixed 24,576-token context |
| Baseline | Deterministic keyword and pattern classifier | Local, no model |

Both model conditions receive identical filtered log text, prompt, response schema
and reasoning effort. Only the model differs, so any measured difference is
attributable to it.

**Baseline.** In earlier correspondence I undertook to compare against baseline
methods, and I intend to keep that. The baseline maps text patterns to the same
failure categories and is scored identically to the model conditions. It will be
written only after the taxonomy is fixed and only against the development
partition, so that it cannot be tuned to the final set. Without it I cannot say
what the LLM adds over a trivial approach, and I would rather report that honestly
whichever way it comes out.

**Practical limits.** Measured per-case cost and latency: the proprietary
condition averages 19.4 seconds and USD 0.038 per diagnosis; the open-weights
condition averages 17.4 minutes and no API cost. Annotation of a single case takes
appreciably longer than either. A cohort of roughly 25 cases implies about 7 hours
of local inference and a comparable amount of annotation for each of two
reviewers; 74 cases implies about 21.5 hours of inference. This is the binding
constraint on cohort size, and decision (f) asks you to set a target.

## 10. Decisions requested

| | Decision | My proposal |
| --- | --- | --- |
| (a) | Case selection by pipeline stage and documented repair | Adopt both criteria |
| (b) | The repository pair | `django/django` plus one contrasting project, confirmed after the traceability check |
| (c) | Ground-truth standard, and who acts as second reviewer | Documented repair where available, otherwise blind annotation with independent verification and adjudication |
| (d) | Failure taxonomy | Fix it from the development partition; remove categories the cohort cannot contain |
| (e) | Whether root-cause correctness is scored | Report qualitatively; measure category and evidence-line accuracy instead; word the primary question to match |
| (f) | Target cohort size | Set against the annotation and inference costs in Section 9 |

## 11. Threats to validity

**Evaluator bias.** Ground truth originates with me. Mitigated by blind
annotation, independent second review with written adjudication, and by preferring
documented repairs over judgement.

**Filter truncation.** On large logs the system receives a fixed token window — as
little as 0.8% of the file for the largest candidates. A model may be penalised
for evidence it never received. Evidence-line metrics are where this becomes
visible, and I propose reporting it as a finding about practical applicability
rather than only as a limitation.

**Sample size.** A small cohort yields few discordant pairs, limiting the power of
paired significance testing.

**Taxonomy coverage.** Categories absent from the cohort cannot be evaluated, and
conclusions do not extend to them.

**Cohort irreproducibility.** GitHub removes a run from its failure listing once
it has been re-run successfully. A cohort is a point-in-time sample and cannot be
reconstructed from the API afterwards. Raw logs, checksums and manifests are
preserved for this reason.

**Model contamination.** Public repository logs may appear in model training data.
This is not controllable and is reported as a limitation.

**Local hardware.** Open-weights latency reflects one machine and is not a general
claim about the model.

## 12. Timeline

| Phase | Work | Target |
| --- | --- | --- |
| 1 | Literature evidence matrix; repository traceability check | in progress |
| 2 | This plan approved or redirected | this review |
| 3 | Tooling changes the approved protocol requires | ~1 week after approval |
| 4 | Case construction and independent verification | ~1 week |
| 5 | System freeze and pipeline pilot | ~3 days |
| 6 | One-time held-out evaluation | ~3 days |
| 7 | Analysis and seminar preparation | before 9 November 2026 |

The methodology and system-design chapters are being written in parallel, so that
the design decisions are documented before any results are analysed.

---

## Appendix A — Candidate repository measurements

Recent non-bot failed runs sampled from each candidate. "Model receives" is the
share of the log surviving filtering at a 12,000-token budget.

| Repository | Real failed runs | Median lines | Model receives |
| --- | ---: | ---: | ---: |
| django/django | 100 | 256 | 24.2% |
| urfave/cli | 84 | 300 | 15.7% |
| prettier/prettier | 83 | 326 | 30.3% |
| jekyll/jekyll | 100 | 799 | 27.0% |
| clap-rs/clap | 83 | 955 | 4.5% |
| gradle/gradle | — | 2,526 | 10.0% |
| sveltejs/svelte | 85 | 3,587 | 1.9% |
| eslint/eslint | 97 | 4,694 | 6.3% |
| google/gson | 78 | 5,577 | 4.8% |
| pallets/flask | 100 | 9,352 | 2.9% |
| junit-team/junit5 | 66 | 28,235 | 1.2% |
| rollup/rollup | 64 | 34,422 | 0.8% |

Above roughly 3,000 lines the filter saturates its token budget, so the model
receives a fixed-size window regardless of log length. Bot-generated runs
(Dependabot, Renovate, scheduled scanners) are excluded from these figures: they
produce short, near-identical logs that flatter a median but are removed by
deduplication during triage. `junit-team/junit5` illustrates the effect — its
median was 179 lines before bot runs were excluded and 28,235 after.

## Appendix B — System readiness

Implemented and tested: fixed-list collection with checksums; deterministic triage
with a recorded reason for every exclusion; two-pass blind annotation with
independent verification and adjudication; a ground-truth audit that rejects
unverified or unevidenced cases; partition guards preventing exploratory cases
from entering a held-out run; per-category and evidence-line scoring; paired
statistical tests; and run metadata recording the git commit, prompt hash,
response schema, model identifiers, model digest and input checksums.

Not yet implemented, pending the decisions above: the keyword baseline, the
split manifest for three partitions, a clean-worktree check before a final run,
and a root-cause rubric if decision (e) requires one.
