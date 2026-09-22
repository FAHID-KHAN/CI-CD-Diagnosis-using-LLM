# Evaluation Plan — LLM-Based Diagnosis of CI/CD Pipeline Failures

**Author:** Fahid Khan
**Supervisors:** Jussi Rasku, Md Mahade Hasan
**Status:** Draft for supervision review
**Responds to:** action item A2 from the kickoff meeting, 21 September 2026

Sections marked **[DECISION]** are choices this review is asked to approve or
redirect. Sections marked **[MEASURED]** report numbers already obtained from
the prototype and the collected data; they are evidence, not proposals.

---

## 1. Purpose and scope

This study evaluates whether an LLM-based diagnostic system can identify the
cause of a failed CI/CD pipeline run from its log, and whether a proprietary
model and an open-weights model differ in doing so.

The artifact under evaluation is the diagnostic system: log filtering, a fixed
prompt, a strict response schema, and a grounding check on cited evidence. The
model is one replaceable component inside it. Everything else described in this
plan — collection, triage, annotation, scoring — is evaluation apparatus and is
deliberately independent of the artifact.

**Out of scope for this thesis:** retrieval-augmented comparison, a human-versus
-LLM study, additional model families, and repair generation. Whether a
rule-based baseline is in scope is an open decision (§10).

## 2. Research questions

As agreed in correspondence before the kickoff meeting:

> **Primary research question.** How effectively can an LLM-based diagnostic
> system identify failure causes in CI/CD pipeline logs?
>
> **SRQ1.** How does the diagnostic performance of an LLM-based system differ
> when using a proprietary LLM versus an open-weights model?
>
> **SRQ2.** Which categories of CI/CD failures is the LLM-based diagnostic
> system most and least effective at diagnosing?

### 2.1 What each question currently rests on **[MEASURED]**

Every metric below is implemented and produces output today, except where the
gap column says otherwise.

| Question | Measured by | Gap |
| --- | --- | --- |
| PRQ — identify failure *causes* | Exact failure-category match; evidence-line precision/recall against annotated lines; grounding score | **Root-cause correctness is not scored.** Ground truth records a written root cause, but nothing compares it to the model's. Only the *category* is scored. |
| SRQ1 — proprietary vs open-weights | Paired McNemar, permutation test, bootstrap CIs; grounding; hallucination rate; latency; token use; cost | None. Both conditions share an identical prompt, schema, filter budget and reasoning effort. |
| SRQ2 — categories handled well and poorly | Per-category precision, recall, F1 and support; macro F1; per-condition confusion matrices | Requires categories to actually occur in the cohort. See §5 — the first annotation pass populated three of eight. |

The gap on the primary question is the most consequential item in this plan.
The PRQ asks about *failure causes*; the system currently scores *failure
categories*. Category accuracy is a reasonable proxy but it is not the same
claim, and the difference should be resolved deliberately rather than absorbed
silently. Three options:

1. **Add a root-cause rubric.** A fixed scoring rubric applied by the two
   reviewers, with an inter-rater procedure. This answers the PRQ as written but
   adds a second annotation burden on every case.
2. **Narrow the PRQ** to failure-category identification plus evidence
   localisation, and state that root-cause and fix quality are reported
   qualitatively rather than scored.
3. **Score root cause indirectly** through evidence-line accuracy, arguing that
   correctly locating the failing lines is a measurable component of identifying
   the cause.

**[DECISION]** Choose among these before the cohort is annotated, because
option 1 changes what annotators must record.

### 2.2 Commitments made in correspondence

The pre-meeting email also undertook to report **baseline methods** alongside
the two model conditions, and **root-cause and suggested-fix quality**. Neither
exists in the current system: there is no rule-based or heuristic baseline, and
`suggested_fix` is stored but never compared to anything. Both are carried into
the open decisions in §10 rather than quietly dropped.

Secondary, operational outcomes: cost, latency, and how much of a log the system
can actually use.

## 3. Unit of analysis and case selection **[DECISION]**

The unit of analysis is one failed GitHub Actions workflow run.

Selecting repositories by log size was investigated and does not work. **[MEASURED]**
Sampling recent real (non-bot) failed runs from eleven candidate repositories
gives median log lengths of:

| repository | real failed runs | median lines | share the model receives |
| --- | ---: | ---: | ---: |
| django/django | 100 | 256 | 24.2% |
| urfave/cli | 84 | 300 | 15.7% |
| prettier/prettier | 83 | 326 | 30.3% |
| jekyll/jekyll | 100 | 799 | 27.0% |
| clap-rs/clap | 83 | 955 | 4.5% |
| sveltejs/svelte | 85 | 3,587 | 1.9% |
| eslint/eslint | 97 | 4,694 | 6.3% |
| google/gson | 78 | 5,577 | 4.8% |
| pallets/flask | 100 | 9,352 | 2.9% |
| junit-team/junit5 | 66 | 28,235 | 1.2% |
| rollup/rollup | 64 | 34,422 | 0.8% |

Two findings follow. First, **no repository is uniformly small**: every
candidate is bimodal, with short static-analysis failures and a long tail of
build and test failures. Second, **short logs are short because they are lint,
format, docs or commit-message jobs**. Dependency resolution failures, test
failures and timeouts occur in build and test jobs, which are long by nature.

Selection must therefore operate on cases, not repositories. Two criteria are
proposed, both observable before any diagnosis is made:

1. **Pipeline stage.** Include failures in build and test jobs; exclude
   static-analysis, formatting, documentation and commit-message jobs. Classify
   from the failing step's command (`pytest`, `gradle build`, `npm test` against
   `flake8`, `prettier --check`), not from the workflow name.
2. **Documented repair.** Prefer cases where repository history shows the fix.
   This is a proxy for practical significance — a maintainer cared enough to
   repair it — and it simultaneously supplies tier-one ground truth (§4).

Cases are deliberately **not** selected by predicted failure category. Doing so
would make the cohort a function of the classifier being evaluated, and would
invalidate any rule-based baseline.

**[DECISION]** Approve the two selection criteria, and approve a repository pair
to apply them to. `django/django` is proposed as one member: it has the shortest
median log, and uniquely showed no bot-generated noise in the sample. The second
member matters less under case-level selection; `urfave/cli` (Go) or
`prettier/prettier` (JavaScript) are the closest on log length.

## 4. Ground-truth strategy **[DECISION]**

Evidence hierarchy, strongest first:

1. **`historical_fix`** — the failing revision linked to a documented fixing
   commit, pull request or issue.
2. **`seeded_defect`** — a recorded injected change with a known cause and
   repair.
3. **`expert_review`** — annotation supported by repository evidence.
4. **`combined_adjudicated`** — a documented combination with adjudication rules.

LLM-as-judge is not part of the plan. If it becomes unavoidable it will be
separated from the main accuracy claims and reported as a validity limitation.

Every case records: the evidence method and its reference, the failure category,
a written root cause, supporting log-line numbers, the annotator, the
independent verifier, the agreement outcome, and adjudication notes where the
two reviewers disagreed.

Annotation runs in two blind passes. The first reviewer labels the case from a
line-numbered log with no model output visible. A second reviewer, who must not
be the first, labels the same case without seeing the first answer; the tool then
compares them and requires a written adjudication for every disagreement. Raw
agreement before adjudication is reported as the inter-rater measure.

**[MEASURED]** A first annotation pass over 12 django cases produced only
`expert_review` evidence — tier three, with the researcher as the expert. That is
the evaluator-bias risk the kickoff identified, and it is the reason the
traceability question in §3 matters.

**[DECISION]** Confirm the evidence hierarchy, and identify the second reviewer.

## 5. Failure taxonomy **[DECISION]**

The current schema declares eight categories: `dependency_error`,
`test_failure`, `build_configuration`, `timeout`, `permission_denied`,
`syntax_error`, `network_error`, `unknown`.

**[MEASURED]** The 12 annotated django cases populated only three of the eight
— `build_configuration` (6), `syntax_error` (3), `unknown` (3). Five categories
never occurred: `dependency_error`, `test_failure`, `timeout`,
`permission_denied`, `network_error`. This is a direct consequence of short
logs being static-analysis failures, and it is the strongest single argument for
stage-based selection.

**[DECISION]** Either (a) adopt stage-based selection so build and test failures
enter the cohort and the eight categories can be exercised, or (b) reduce the
taxonomy to the categories the cohort can actually contain, and state that
restriction as a scope limit. Retaining eight categories while five cannot occur
is not defensible.

The final taxonomy will be justified against published CI/CD failure
classifications before the cohort is frozen.

## 6. Partitions and held-out procedure

Three disjoint partitions, fixed before any prompt or taxonomy refinement:

| Partition | Purpose | May influence the system | In final claims |
| --- | --- | ---: | ---: |
| Development | Refine filtering, prompt, taxonomy, rubric | Yes | No |
| Pilot | Verify the frozen pipeline end to end | No | No |
| Final held-out | One-time evaluation | No | Yes |

Partitioning is by underlying defect rather than by run identifier, so reruns
and duplicate manifestations cannot leak between sets. The allocation is stored
in a versioned split manifest with a fixed seed and case checksums.

Enforcement is implemented: the benchmark refuses to run a held-out evaluation
over any case an exploratory cohort has already used, and triage excludes such
cases with a recorded reason. An override exists but records a written
justification and is never used for thesis evidence.

**[DECISION]** Approve the partition sizes once the cohort size is settled.

## 7. Metrics, pre-registered

Primary:

- failure-category macro F1, with per-category precision, recall, F1 and support;
- exact category accuracy;
- evidence-line precision, recall and F1 against annotated supporting lines;
- diagnostic completion rate, with inference failures counted as incorrect;
- root-cause correctness, if §2.1 option 1 is approved; otherwise reported
  qualitatively and excluded from accuracy claims.

Secondary: grounding score, hallucination rate, latency, token use, estimated
cost.

Because both conditions diagnose the same cases, comparison uses paired tests:
McNemar's test, a paired permutation test, and bootstrap confidence intervals.
Per-category support counts are reported alongside every per-category result so
that small groups are not over-read.

Two metrics are reported separately and must not be conflated. **Grounding
score** checks only that a cited line exists in the extract the model was given;
it never consults ground truth. **Evidence-line accuracy** compares the model's
cited lines with the annotated ones. **[MEASURED]** In a five-case pilot these
diverged sharply: 97.5% grounding against approximately 6% evidence-line F1.

**[DECISION]** Confirm whether evidence-line scoring uses strict set overlap, as
above, or a relaxed criterion such as any-annotated-line-hit or a ±N line
window.

## 8. Model conditions

| Condition | Model | Access |
| --- | --- | --- |
| Proprietary | `openai/gpt-5.6-terra` | API |
| Open-weights | `local/thesis-qwen3.5:9b-24k` | Ollama, fixed 24,576-token context |

Both conditions receive identical filtered log text, prompt, response schema and
reasoning effort (`medium`). Only the model differs, so any measured difference
is attributable to it.

**[MEASURED]** Observed per-case cost and latency: the proprietary condition
averaged 19.4 s and USD 0.038 per diagnosis; the open-weights condition averaged
17.4 minutes and no API cost. A 26-case cohort therefore implies roughly 7 hours
of local inference; a 74-case cohort implies roughly 21.5 hours. This is a
practical argument for a small, well-chosen cohort.

## 9. System freeze

Before the held-out run the system is tagged and the following recorded: git
commit and clean-worktree status, prompt hash, response schema, filter
parameters, dependency versions, model identifiers, Ollama version, model digest
and quantisation, reasoning effort, and input and ground-truth checksums.

Everything except the clean-worktree check is implemented. If the pilot reveals
a defect requiring a change, the system is re-frozen at a new version and a
different reserved pilot set is used; a pilot case that has been inspected never
moves into the final set.

## 10. Open decisions for this review

1. Approve stage-based and repair-based case selection (§3).
2. Approve the repository pair (§3).
3. Confirm the evidence hierarchy and identify the second reviewer (§4).
4. Resolve the taxonomy question: broaden the cohort, or narrow the taxonomy (§5).
5. Decide whether a rule-based baseline is in scope. None currently exists,
   although both the kickoff status update and the pre-meeting email assumed
   one. If it is in scope it must be built before the system is frozen.
6. Set the target cohort size, given the annotation and inference costs in §8.
7. Confirm the evidence-line scoring criterion (§7).
8. Resolve the primary-question gap: score root-cause correctness with a rubric,
   narrow the question, or score it indirectly (§2.1).
9. Decide whether suggested-fix quality is scored, reported qualitatively, or
   dropped. It was promised in correspondence and is currently unmeasured.

## 11. Threats to validity

- **Evaluator bias.** Ground truth produced by the researcher. Mitigated by
  blind annotation, independent second review with written adjudication, and by
  preferring documented historical fixes.
- **Filter truncation.** On large logs the system receives a fixed token window —
  as little as 0.8% of the log (§3). A model may be penalised for evidence it
  never received; evidence-line metrics are where this becomes visible.
- **Sample size.** A small cohort yields few discordant pairs, limiting the
  power of paired significance testing.
- **Taxonomy coverage.** Categories absent from the cohort cannot be evaluated
  (§5).
- **Cohort irreproducibility.** GitHub removes runs from its failure listing once
  they are re-run successfully. A cohort is a point-in-time sample and cannot be
  reconstructed from the API; this is why raw logs and checksums are preserved.
- **Model contamination.** Public repository logs may appear in model training
  data. Not controllable; reported as a limitation.
- **Local hardware.** Open-weights latency reflects one machine and is not a
  general claim about the model.

## 12. Timeline

| Phase | Work | Target |
| --- | --- | --- |
| 1 | Literature evidence matrix; traceability feasibility check | before this review |
| 2 | This plan approved or redirected | this review |
| 3 | Minimal tool changes the approved protocol requires | ~1 week after approval |
| 4 | Case construction and independent verification | ~1 week |
| 5 | System freeze and pipeline pilot | ~3 days |
| 6 | One-time held-out evaluation | ~3 days |
| 7 | Analysis and seminar preparation | before 9 November 2026 |

No final evaluation data is collected before phase 2 concludes.
