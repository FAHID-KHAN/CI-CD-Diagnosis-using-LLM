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
| Code | Complete. 186 tests, lint and type checks pass. |
| Study data | `thesis_scrapy_vite_2026` is the study cohort: 131 raw, 81 eligible after re-triage, re-split (11 / 11 / 31 plus 28 reserve), **22 of 53 annotated** -- development 11/11, pilot 11/11, held_out 0/31. Two paired runs complete, each with three conditions. Superseded: `thesis_pair_2026` (27 annotations, all void -- django and gradle both dropped) and `thesis_gradle_scrapy_2026` (78 eligible, never annotated). |
| Repositories | scrapy/scrapy and vitejs/vite, decided 18 October 2026 |
| Active config | `configs/thesis_scrapy_vite_2026.yaml` — scrapy/scrapy (100) and vitejs/vite (60), sampling window 14–45 days. Cohort collected 18 October; do not edit, its SHA-256 is in the manifests. |
| Evaluation plan | Sent and approved. `EVALUATION_PLAN.md` holds the drafted §3.1, §3.2 and amended §10; reconcile it with whatever was actually sent. |
| Progress report | `docs/thesis/PROGRESS_REPORT_2026-10-21.md` — standalone, written 21 October |
| Next | Annotate the 31 held-out cases (10–13 h). Then verify the approval record, freeze, run `final` once. |
| Approval | **Granted 21 October 2026.** Single-annotator ground truth accepted. Recorded in `data/studies/thesis_scrapy_vite_2026/methodology_approval.json` — verify its fields against the actual message. |
| Blocked on | Annotation. The held-out run is gated on a completed pilot and a freeze record, not on approval. |

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

**The log filter loses the evidence on large logs.** Measured on the 16-case
development partition, 14 October 2026 (`experiments/dev_001`, hosted model):

| | |
| --- | --- |
| Mean preprocessing recall | 32.6% |
| Cases where no verified evidence line survived | 9 of 16 |
| Cases fully preserved | 3 of 16 |

Every one of those nine returned `unknown`, at 97–98% confidence. The model was
not guessing; it correctly reported that it could not see the failure. The
run's 12.5% category accuracy therefore measures the filter, not the model.

**Diagnosed and partly fixed, 14 October 2026.** Instrumenting the three
filtering stages (`LogFilter.trace_filtering`) attributed the loss precisely:
keyword matching was finding all the evidence (31/31, 34/34, 50/50), and the
500-line cap was then discarding it. The cap kept the *first* 500 lines of what
survived the window, so setup output at the top of a log filled the budget
before the failure near the bottom was reached. Token truncation was not
involved; it never received the evidence.

The cap now keeps the last 500 lines. A CI log is chronological and a failure
is reported where it occurs, which is near the end. Effect on the development
partition:

| | before | after |
| --- | ---: | ---: |
| Cases with no evidence surviving | 9 of 16 | 5 of 16 |
| Cases fully preserved | 3 of 16 | 7 of 16 |
| Mean preprocessing recall | 32.6% | 57.6% |

**The five remaining failures are a documented limitation, not a defect to
fix.** Every one is a log of 41,000 to 96,000 lines. Three still lose at the
cap: with 800 to 1,500 keyword hits, the context windows cover far more than
500 lines even from the tail. Two lose at the keyword window itself -- the
failure text contains none of the configured markers.

Decision (14 October 2026): accept this rather than tune further. "Keyword and
context-window filtering does not scale to logs above roughly 40,000 lines" is
a reportable finding about the limits of the approach, and preprocessing recall
makes the boundary measurable rather than asserted. Continued tuning against
five development cases would also risk fitting the filter to them.

**Confirmed against the models, 14 October 2026.** Re-running the development
partition on the hosted condition after the cap fix (`experiments/dev_002`
against `dev_001`, same cases, same prompt, same schema -- only the filter
changed):

| | dev_001 | dev_002 |
| --- | ---: | ---: |
| Mean preprocessing recall | 32.6% | 57.6% |
| Category accuracy | 12.5% | 43.8% |
| Predictions changed | — | 6 of 16 |

Five cases went from wrong to right, and every one lies in the 1,000-4,000 line
band the cap fix rescued:

| Raw lines | Verified category | dev_001 | dev_002 |
| ---: | --- | --- | --- |
| 2,547 | permission_denied | unknown | permission_denied |
| 2,413 | syntax_error | unknown | syntax_error |
| 3,661 | dependency_error | unknown | dependency_error |
| 1,262 | network_error | permission_denied | network_error |
| 2,527 | permission_denied | unknown | permission_denied |

The five logs above 40,000 lines were unchanged, still `unknown`, as expected.

Two things follow. The recovered cases span four different categories, so the
earlier appearance that the system could only answer `unknown` or
`build_configuration` was an artefact of evidence loss, not a limit of the
model. And four django cases verified as `test_failure` are still consistently
answered `build_configuration` despite their evidence surviving filtering
(236-239 line logs) -- that is a codebook or model-error question, not a
preprocessing one, and it concerns the `Run Quality Checks on a PR` job whose
scope has been in doubt since the repository assessment.

These are development-partition figures. They exist to direct the work and must
never be reported as findings.

This defect was found on the partition the plan permits tuning on, which is
what the development set is for. The change is recorded here and belongs in the
freeze record and the methods chapter.

**Cost and time.** Proprietary: 19.4 s and USD 0.038 per case. Open-weights:
17.4 minutes per case, no API cost. A 26-case cohort means roughly 7 hours of
local inference.

**The open-weights condition truncates before it answers.** Diagnosed on the
development partition, 17 October 2026 (`experiments/dev_002_local`). Five of
sixteen inferences failed, and the captured responses show one cause with no
ambiguity:

| | |
| --- | --- |
| `finish_reason` | `length` on all five |
| Completion tokens | exactly 4,096 on all five |
| Response characters | 0 on all five |

Qwen 3.5 is a reasoning model: it spends completion budget thinking before
emitting any JSON, and on these cases it consumed the whole allowance and
returned nothing. The parse error (`Expecting value: line 1 column 1`) was an
empty string, not malformed output.

This is configuration, not model quality. `max_tokens` is 4,096 while the model
has a 24,576-token context and these prompts occupied 16,137 to 16,923 tokens,
leaving roughly 7,600 tokens of headroom. Successful calls were observed using
up to 4,441 completion tokens, which is why some completed and others were cut
off. **Until this is raised, any comparison understates the open-weights
condition**, because five of its sixteen cases never got to answer.

Found only because failed inferences now store the raw response,
`finish_reason` and token usage. Before that change a failure recorded only its
error string and could not be explained.

**Fixed, 18 October 2026.** The completion budget is now set per condition in
`src/api/llm_service.py`: `HOSTED_MAX_TOKENS = 4096`, `LOCAL_MAX_TOKENS = 7168`.
The local figure leaves headroom above the largest observed development prompt
(16,923 tokens) within the fixed 24,576-token context. An explicit `max_tokens`
still overrides it, so the budget can be varied deliberately and recorded.

**Confirmed, 18 October 2026** (`experiments/dev_003_local`). All 16 cases
completed, against 11 of 16 before. The largest completion was 6,523 tokens,
which the previous 4,096 budget would have truncated. The run also took 1.6
hours rather than 4.6: cases that previously burned the full budget before
failing now finish.

| | dev_002_local | dev_003_local |
| --- | ---: | ---: |
| Completed | 11 of 16 | 16 of 16 |
| Total run time | ~4.6 h | 1.6 h |
| Completion tokens (median / max) | — | 2,920 / 6,523 |

**Its category accuracy is 0%, and that figure is not yet a measurement.** The
prediction distribution against ground truth:

| Category | Verified | Predicted |
| --- | ---: | ---: |
| test_failure | 9 | 1 |
| build_configuration | 1 | 6 |
| unknown | 0 | 6 |
| permission_denied | 3 | 1 |
| syntax_error | 1 | 0 |

Two reasons to distrust it. Nine of the sixteen cases turn on the unwritten
`test_failure` / `build_configuration` tie-break: both models disagree with the
ground truth in the same direction, which more often indicates the labels than
the models. And five cases still have no evidence surviving the filter, where
`unknown` is the correct answer.

What does hold up: the hosted condition answered 7 of 16 correctly against the
local condition's 0, consistently across both runs. And the operational gap is
real regardless of any label -- 1.6 hours against roughly 2 minutes for the same
sixteen cases, at USD 0 against USD 0.46.

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

## django/django was replaced by scrapy/scrapy

Decided 18 October 2026. The evaluation plan §3.1 requires the retention or
replacement of a repository to be explained; this is that explanation.

**Why django failed.** Fifteen of its eighteen eligible cases came from one job,
`Run Quality Checks on a PR`. Reading the annotated evidence showed what these
are: `scripts/pr_quality/check_pr.py` validating pull-request metadata -- a
malformed Trac ticket reference, an AI disclosure reading only "Claude", a
ticket not yet Accepted. No build ran and no test executed. They are
administrative checks of the same class as `check-commit-suffix`, which triage
already excludes, and were admitted only because the job name contains the word
"check". Excluding them leaves django with roughly three cases.

This also resolved the `test_failure` / `build_configuration` dispute. Both
models answered `build_configuration` on those four cases while the ground truth
said `test_failure`; neither category fits a metadata validation script. The
disagreement was an artefact of forcing an out-of-scope case into a category,
not a defect in either model or in the codebook.

**Repository assessment, 18 October 2026** (30 inspected failures each):

| Repository | In scope | Repair-linked | Families |
| --- | ---: | ---: | ---: |
| pytest-dev/pytest | 26/30 | 15/30 | 27 |
| scrapy/scrapy | 23/30 | 18/30 | 25 |
| sveltejs/svelte | 21/30 | 10/30 | 24 |
| pandas-dev/pandas | 14/30 | 10/30 | 21 |
| gradle/gradle | 14/30 | 14/30 | 11 |
| django/django | 9/30 | 22/30 | 3 |

scrapy was chosen over pytest-dev/pytest despite a lower in-scope rate, on
repair traceability: 18 of 30 against 15. That figure determines how much of the
ground truth can rest on a documented repair rather than on expert judgement,
which is the concern both supervisors raised. pandas was excluded because four
of its in-scope cases are `Type Checking` jobs, the same lint-adjacent category
that sank django. The svelte figure quoted earlier in this project (20/30
repair-linked) predates the bot-filter change and should be disregarded.

**What this does not fix.** scrapy's failures are overwhelmingly `Run tests`, so
the category skew remains: 20 of 27 annotated cases were already
`test_failure`. Controlled defects are still required for category coverage.

**Carried forward.** The 11 gradle annotations are preserved and can be moved
into the new cohort by log checksum with
`tools/carry_over_annotations.py`. The 16 django annotations are not carried:
those cases are out of scope. `thesis_pair_2026` is retained as the record of
the django attempt.

## The codebook

`docs/thesis/CODEBOOK.md` exists as a skeleton with 34 `TO WRITE` markers. The
structure, the five overlapping category pairs and the worked examples drawn
from the development set are prepared; the definitions are not written.

It matters for three reasons beyond the plan requiring it (§3.5). Chance-
corrected agreement measures whether two reviewers applied the same rules, so
without written rules it measures only whether two people think alike. A second
reviewer cannot begin without it, per Mahade's Q3. And it is the only way to
settle disagreements of definition rather than of judgement.

**Largely resolved by replacing django.** The nine development cases that hinged
on the `test_failure` / `build_configuration` rule were the out-of-scope
`Run Quality Checks on a PR` cases. The tie-break still needs writing, but it no
longer blocks a development result.

**The live case.** Four django `Run Quality Checks on a PR` failures are
labelled `test_failure` in the ground truth; the hosted model answered
`build_configuration` on all four, with their evidence fully preserved through
filtering (236-239 line logs). This is not a preprocessing problem and not
obviously a model error. The question it turns on -- does a check script that
exits non-zero without running a test suite constitute a test failure? -- has
no written answer yet, so neither label can be called correct. The same four
cases are also the `Run Quality Checks on a PR` job whose scope has been in
doubt since the repository assessment.

## The preprocessing boundary, and what it costs

Measured 18 October 2026 on the 27 annotated cases of `thesis_pair_2026`, and
on the 78-case `thesis_gradle_scrapy_2026` cohort. These numbers decide whether
gradle can serve as a repository arm, so they are recorded in full.

**Preprocessing recall splits cleanly at roughly 40,000 log lines.**

| raw log lines | cases | lost all evidence | mean recall |
| --- | --- | --- | --- |
| under 40k | 22 | 0 (0%) | 74% |
| over 40k | 5 | 5 (100%) | 0% |

Not a gradient -- a wall. Every case below the threshold retained some verified
evidence; every case above it retained none. `lost_at` attributes three of the
five to `line_cap` and two to `keyword_window`.

**The budget cannot be raised.** The local model's context is the binding
constraint on what *both* models see:

```
local context          24,576
completion reserve     -7,168
available for prompt   17,408
largest prompt observed 16,923
headroom                   485 tokens
```

Raising `max_tokens` on the filter breaks the local condition. Raising it for
the hosted model alone would mean the two conditions no longer receive the same
input, which ends the controlled comparison. A deployable pipeline has one
preprocessing configuration and ours is sized to the smaller model. This belongs
in the thesis as a stated scoping decision, not in limitations -- a reader will
otherwise ask why the hosted model was not given the whole log.

**Section scoping fails on gradle specifically -- see the correction below.**
Large gradle logs are 26-section archives and the evidence does sit in only two
or three sections, so restricting the filter to them looked promising. Tested two
ways against the five large-log cases: scoping to the sections whose name matches
`failing_job` recovered evidence in 1 of 5 (mean recall 4%), and ranking sections
by error-keyword density and filling the line budget recovered none. Gradle's
sections are themselves 3,000-11,000 lines of keyword-dense test output, so the
500-line cap still crowded the evidence out.

**This was recorded at the time as "section scoping does not work", which was
wrong as a general claim** -- it held only for gradle's umbrella jobs, which are
now excluded from the study. On scrapy and vite the failing job's section is
around 1,200 lines and scoping works very well. See the section on the scoped
filter below. The claim is left here, corrected, rather than deleted, because the
measurement was real and the overreach is worth remembering.

**The boundary is an umbrella-job effect, not a repository effect.** Within
gradle the separation is total:

| gradle failing job | cases | median lines | over 40k |
| --- | --- | --- | --- |
| umbrella / aggregate | 25 | 43,426 | 25 |
| single-purpose | 11 | 2,413 | 0 |

The 25 are `Sanity Check on Linux` (18) and a 16-module `(Unit Test)` aggregate
(7). An umbrella job is not one diagnosable failure -- it is many independent
failures reported under one job name, which is the same reasoning already
recorded in `_job_step_key` in `src/evaluation/failure_families.py`. Asking for
*the* root cause of such a run is not well posed, so the ground truth would be
ambiguous even to a human annotator. This is a construct-validity argument, and
excluding on it is selection on evidence availability, which the methodology
permits; selection by model performance it is not.

**What is left of gradle is too thin for a repository arm.** Of the 11
single-purpose cases, five are maintenance or bot workflows that triage did not
catch -- `Upgrade to latest wrapper`, `Auto update performance test buckets`,
`Auto update test buckets`, `Submit Dependency Graph`, `Running Copilot Code
Review`. `is_bot_run` returned `False` for all five -- `BOT_MARKERS` carried
`"dependency submission"` but the workflow is named `Submit Dependency Graph`,
and nothing matched the Copilot reviewer. Markers for all five were added on
18 October 2026, so a future cohort excludes them. That leaves four `Compile All` cases
and two `Contributor CI Build` cases with no `failing_job` recorded: **about six
genuinely diagnosable gradle cases.** Six is an anecdote, not an arm.

**The split would concentrate the loss in held-out.** Previewed read-only with
`allocate(..., rule="combined", seed=20261010)`, no manifest written:

| partition | n | over 40k | usable | usable gradle |
| --- | --- | --- | --- | --- |
| development | 16 | 5 | 11 | 2 |
| pilot | 16 | 3 | 13 | 4 |
| held_out | 46 | 17 | 29 | 5 |

The held-out set runs once. Twenty-four of its 29 usable cases are scrapy, so as
it stands the single confirmatory run would be a scrapy study with five gradle
cases attached.

**Analysis decision to pre-register before annotating.** Report accuracy
stratified: primary on cases where preprocessing recall > 0, which is where the
model was actually given the evidence and so is what measures the models; and
preprocessing recall across the whole cohort as a separate result, which is what
measures the pipeline. Both always reported together. Fixing this now, before
any model has run on this cohort, is what separates it from choosing the
flattering subset after the fact.

## Candidate repositories for the gradle replacement

Measured 18 October 2026 with `tools/scout_repositories.py`, four sampled failed
runs per repository across fifteen candidates in six ecosystems. Raw
measurements: `docs/thesis/measurements/repository_scout_2026-10-18.json`.
No model was run and nothing here looks at model output.

**Three "tractable" verdicts were artifacts and the scout cannot see why.** It
samples by recency and reports the workflow name, so a repository whose recent
failures are maintenance automation looks small:

| repository | median | what was actually sampled |
| --- | --- | --- |
| babel/babel | 60 | 3 of 4 were `Lock Threads`, an issue-locking bot; its real CI run was 13,355 lines |
| etcd-io/etcd | 285 | all 4 were `Measure TestGrid Flakiness`, a scheduled measurement, not a fault |
| netty/netty | 168 | 3 of 4 were `PR Reports`; the one real `Build PR` was **1,324,878 lines** |

This is the django lesson again -- a short median meant administrative jobs, not
tractable ones. `is_bot_run` catches neither `Lock Threads` nor
`Measure TestGrid Flakiness`; both are candidates for `BOT_MARKERS` if either
repository is ever reconsidered.

**No JVM candidate is tractable.** netty 1.3M lines, apache/dubbo 3.5M,
micronaut-core 53,574, mockito 26,650 and most of its logs already expired.
Large JVM projects build and test every module in one job, which is the same
umbrella structure that made gradle unusable. Worth stating in the thesis: the
exclusion is not about gradle specifically but about how JVM monorepo CI
reports, and it is why the ecosystem contrast cannot be python-versus-jvm.

**Two candidates hold up**, and vitejs/vite was chosen -- see the decision
record below. Their sampled logs are genuine CI runs, and 28
inspected failed runs each contained no bot runs and no umbrella jobs:

| repository | real failed runs | median lines | tokens kept | filter saturated | in-scope jobs |
| --- | --- | --- | --- | --- | --- |
| vitejs/vite | 100 | 4,723 | 2,453-3,480 | no | 24 of 28 |
| sveltejs/svelte | 94 | 3,626 | 1,641-3,773 | no | 21 of 28 |

The unsaturated filter is the column that matters. Both stay well inside the
12,000-token budget, so the model receives the whole filtered selection and the
measurement tests the model rather than the filter -- the opposite of gradle,
and unlike vuejs/core, hugo, symfony and mockito, which all saturate at ~11,990
tokens. Non-in-scope jobs in both are `Lint`, which triage already excludes.

Both run matrix jobs (`Build&Test: node-24, windows-latest`, `Tests (20,
macOS-latest)`), so one fault surfaces across several matrix entries and family
grouping will collapse them. Distinct-family yield per raw run is therefore
unknown until a collection pass runs, and is probably lower than scrapy's.

The ecosystem contrast becomes Python versus JavaScript rather than Python
versus JVM. Caveat on the numbers: four sampled logs per repository for sizes
and 28 inspected runs for job names. Thin, but it is a tractability decision,
which is what the methodology permits selecting on.

## gradle/gradle was replaced by vitejs/vite

Decided 18 October 2026, on the measurements in the two sections above.
Evaluation plan §3.1 requires a repository replacement to be explained; this is
that explanation. The study repositories are now **scrapy/scrapy** and
**vitejs/vite**.

**Why gradle failed.** Twenty-five of its 36 eligible cases were umbrella jobs
-- `Sanity Check on Linux` and a sixteen-module `(Unit Test)` aggregate -- which
report many independent failures under one job name and so have no single root
cause to annotate. All 25 were over 40,000 log lines and lost every verified
evidence line in filtering; all 11 single-purpose jobs were under it and lost
none. Excluding umbrella jobs leaves about six genuinely diagnosable gradle
cases, which is an anecdote rather than a repository arm.

**Why the replacement is not JVM.** Five JVM candidates were measured and none
is tractable: netty/netty 1,324,878 lines on its one real `Build PR` sample,
apache/dubbo 3.5M, micronaut-core 53,574, mockito/mockito 26,650 with most logs
already expired. Large JVM projects build and test every module in one job,
which is the same structure that made gradle unusable. The ecosystem contrast is
therefore Python versus JavaScript. This is a finding to report rather than a
compromise to apologise for: it is measured across five projects and it bounds
where the artifact applies.

**Why vite.** Its sampled logs stay inside the token budget (2,453-3,480 tokens
kept against a 12,000 budget), so the filter does not saturate and the model
receives the whole filtered selection -- the measurement tests the model rather
than the filter. Of 28 inspected failed runs, none was a bot run and none was an
umbrella job; 24 were in scope and the other four were `Lint`, which triage
already excludes.

**Yield, measured rather than assumed.** The concern was that matrix jobs
(`Build&Test: node-24, windows-latest`) would make one fault surface repeatedly
and be collapsed by family grouping. It does not happen, for two reasons: matrix
entries are jobs within a single run rather than separate runs, so one run
contributes one case whatever the matrix width; and fault diversity is high --
84 distinct commits across 100 failed runs, against scrapy's 73. Of 24 inspected
runs, 20 were in scope with a downloadable log and all 20 had **distinct** error
signatures, so the duplicate cap removed nothing. That is 0.83 cases per raw run
inspected, against the 0.42 assumed for gradle and scrapy combined.

Signature distinctness was checked for the opposite failure as well -- a
signature sensitive to volatile content would under-deduplicate and admit real
duplicates. `compute_error_signature` strips ISO timestamps, ANSI codes and hex
addresses, and the commit-distinctness figures above account for the result, so
20 of 20 is genuine diversity.

**The inclusion gate, run afterwards, met two of four criteria for vite.** Full
record in `docs/thesis/measurements/repository_gate_2026-10-18.json`.

| criterion | vitejs/vite | scrapy/scrapy | threshold |
| --- | --- | --- | --- |
| 1 logs downloadable | 30/30 | 30/30 | >= 30 |
| 2 build/test/dep/config/env | 24/30 | 23/30 | >= half |
| 3 linkable to a repair | 5/30 | 18/30 | >= 15 |
| 4 not dominated by one workflow | 30/30 (CI) | 21/30 (CI) | <= half |

Both unmet readings are artifacts rather than properties of the repository, and
both were checked rather than assumed.

Criterion 3 is a sampling-window effect. Repair linkage looks for a later
passing run of the same workflow on the same branch, so it needs elapsed time.
vite produces 100 failed runs in two days, so its most recent 30 are mostly too
new to have been repaired. Measured instead on runs from 30 September to
1 October, vite is **15/30** -- at the threshold and comparable to scrapy's
recent 18/30. The same test on scrapy's older runs gives **4/30**, because 28 of
those 30 came from fork branches that no longer exist. The criterion is unstable
with respect to window and fork ratio, and the gate's "most recent 30" default
penalises any repository with high failure throughput. Worth fixing in
`tools/check_repository_gate.py` before it is used again.

Criterion 4 is contradicted by the family counts in the same report: vite shows
30 distinct error signatures and 30 distinct `job_step` keys out of 30 inspected
runs, the highest diversity measured anywhere here. The single-workflow figure
reflects vite keeping all CI in one workflow file.

**A consequence that does need a decision.** Both repositories are test-heavy --
vite 24 of 30 `build_test` with failing steps concentrated on `Test serve` and
`Test serve (bundled dev)`, scrapy 23 of 30. This pair will not populate eight
failure categories evenly, and the existing annotation already skews that way
(20 of 27 were `test_failure`). That is evidence for the open decision on
categories. It is not a reason to pick a repository by predicted category, which
would be circular.

**What this does not settle.** Four sampled logs per repository for sizes and 24
to 30 inspected runs for jobs, signatures and the gate. Enough for a selection
decision on tractability, which is the only basis the methodology permits, but
the real distinct-family yield is known only after a collection pass. The nine
gradle annotations that matched by checksum are discarded with gradle.

## The cohort is sampled from an age window, not from the newest runs

Added 18 October 2026, with the sampling-frame change in
`src/data_collection/data_collection.py`.

Collection used to ask GitHub for the newest failed runs. That is the worst
window for ground truth. A repair is found by looking for a later passing run of
the same workflow on the same branch, so a failure has to have had time to be
fixed before the repair exists to be read -- and the ground-truth standard in
plan §10(c) is "documented repair where available, otherwise blind annotation",
with evaluator bias named as the first validity threat in §11 precisely because
the annotation originates with one person.

Repair-linked share of the first 20 failed runs in each window, measured
18 October 2026:

| window | vitejs/vite | scrapy/scrapy | runs available |
| --- | --- | --- | --- |
| 0-7 days old | 5/20 | 11/20 | 155 / 44 |
| **14-45 days old** | **10/20** | **17/20** | **261 / 284** |
| 45-80 days old | 8/20 | 4/20 | 440 / 287 |

Beyond about 45 days the rate falls again: GitHub expires logs at around 90 days
and the branches a repair would appear on have often been deleted. The config
declares `sampling_window_days: {minimum_age: 14, maximum_age: 45}`, where
availability is 261 and 284 runs against the 160 needed.

This roughly doubles the share of cases whose annotation can be checked against
a documented repair. It does not write any ground truth and it does not look at
model output; it selects on evidence availability, which the methodology
permits.

**Two details that matter more than they look.** The manifest records the
resolved absolute dates (`created_range`), not the ages, because "14 to 45 days
ago" denotes a different interval every day and only the absolute range makes a
frame reproducible. And a resumed collection reuses the recorded range instead
of recomputing it -- otherwise an interruption would move the window by however
long it lasted and the cohort would be drawn from two different frames. A resume
against a protocol that has gained a window where the interrupted run had none
is refused outright.

Preflight samples inside the same frame, so its one-log check is drawn from the
population collection will use.

## How each research question gets answered

Written 18 October 2026. The questions are in `docs/thesis/EVALUATION_PLAN.md`
§3. This maps each one to the measurement that answers it and to what is still
missing, because two of the three have a gap that will not close by itself.

### Proposed revision, 18 October 2026 -- not yet sent to supervisors

**Drafted into `EVALUATION_PLAN.md` §3 on 21 October 2026, and the author is
now rewriting the plan to send.** What is in the file is material to rework
rather than the version going to supervisors. The original wording is kept
beside the revision in §3.2 so the change stays visible, and §3.2 states that
the revision is a request rather than a decision already taken. §3.1 was written
at the same time to cover repository retention and replacement, which condition
R2 requires and which four documents already referenced as §3.1 although it did
not exist; the revised wording moved to §3.2 rather than taking that number.

Three rows of §10 were also amended and need the author's eye before they go
out: **(b)** the repository pair, which still named django; **(c)** the
ground-truth standard, which still promised a second reviewer; and **(d)** the
taxonomy, which now carries the numbers behind the decision. Row (c) is the one
to read closely — it reverses a commitment made to supervisors.

> **Primary.** How accurately can an LLM-based system identify the category of a
> CI/CD pipeline failure and the log lines evidencing it, relative to a
> deterministic rule-based baseline?
>
> **SRQ1.** Under identical preprocessed input, how does the diagnostic
> performance of a proprietary LLM differ from that of a locally hosted
> open-weights model, and at what difference in cost and latency?
>
> **SRQ2.** Which properties of a CI/CD failure log and its pipeline
> configuration determine whether the system can diagnose the failure?

**Primary.** Two edits. "Identify failure causes" became the category and the
evidencing log lines, so the question names what is actually scored. And
"relative to a deterministic rule-based baseline" replaces "how effectively",
which had no referent -- an accuracy figure alone answers nothing. This makes
wiring `src/api/baseline.py` into a run a precondition rather than an
improvement. If the 0/1/2 rubric is adopted, extend to "the category, its root
cause, and the log lines evidencing it"; that is the only remaining fork.

**SRQ1.** "Under identical preprocessed input" carries the constraint the
original wording would overclaim past: the local model's 24,576-token context
sets the filter budget for both conditions, so this compares two models under
one shared deployable configuration, not each at its best. Cost and latency are
named because they were measured and because "differ" is not only accuracy.

**SRQ2.** Reformulated from failure categories to log and pipeline properties,
because the sampling frame cannot populate eight categories. Category survives
inside it as one factor among four, reported where n permits.

**Disclosure this requires.** The methods chapter must state that SRQ2 was
reformulated on 18 October 2026 because the cohort's category distribution --
known from triage and the repository gate, neither of which involves model
output -- could not support per-category comparison. Reformulating before the
held-out run on evidence about cohort composition is legitimate scoping;
reformulating after seeing held-out accuracy would not be, and the whole
distinction lies in the timing and the stated basis. Undisclosed, a moved
question reads as fishing.

### Primary -- how effectively can the system identify failure causes?

"Effectively" is meaningless without a reference point, so the answer is three
numbers, not one.

* **The floor** is the rule-based baseline in `src/api/baseline.py`: a
  deterministic keyword-and-pattern classifier that receives the same filtered
  log, returns the same taxonomy, and is scored by the same code. If the models
  do not beat fixed rules, there is no result to report. **It is not wired into
  `automated_scripts/benchmark_models.py`.** This is the largest single gap in
  answering the primary question, and it was a commitment made to supervisors.
* **The ceiling** is two-sided. `preprocessing_recall` bounds what the model
  could possibly have found, because it cannot identify a cause from evidence it
  never received. Inter-annotator agreement bounds what "correct" means at all,
  and there is still no second reviewer.
* **The measurement** is `category_scores` plus `evidence_line_scores` in
  `src/evaluation/category_metrics.py` -- category accuracy and the precision,
  recall and F1 of the log lines the model cites.

One wording problem has to be resolved rather than left. The question asks about
failure *causes*; the system scores the *category* and the cited evidence lines,
not the free-text root cause against the annotated one. Either adopt the 0/1/2
rubric, which roughly doubles annotation effort per case, or reword the question
to failure categories and supporting evidence. Plan §10(e). Leaving the question
broader than the measurement is the gap a supervisor will find first.

### SRQ1 -- proprietary versus open-weights

The strongest of the three, and the one the apparatus was built for. Paired
design: both conditions receive the identical filtered log, the same prompt and
the same response schema, so the only difference is the model. `McNemar` and
`Wilcoxon` over discordant pairs, via `statistical_tests.json`,
`pairwise_agreements` and `cross_experiment_deltas`. Cost and latency belong in
the answer too, since "differ" is not only about accuracy.

Two things must be stated plainly or the comparison is overclaimed. The local
model's 24,576-token context sets the preprocessing budget for **both**
conditions -- 485 tokens of headroom at the largest observed prompt -- so this
measures the two models under one shared deployable configuration, not each
model at its best. And ties carry no information: a case where both fail because
the evidence never survived filtering reduces power without biasing either way.

### SRQ2 -- which categories are diagnosed best and worst

The weak one. `category_scores` and `macro_f1` compute it correctly, but the
cohort will not contain eight categories to compare. Of 27 annotated cases 20
were `test_failure`; vite is 24 of 30 `build_test` and scrapy 23 of 30. Several
categories will arrive with one case or none, and a per-category F1 over n=1 is
not a finding.

Two honest responses, and they are not exclusive:

* Rescope the question to the categories the cohort actually contains, and
  report the remainder as not evaluable rather than as poor performance. Plan
  §10(d), and the data now forces the issue.
* Use **controlled defects** to populate the thin categories deliberately. This
  is the only lever available: repositories cannot be selected by predicted
  category, because choosing data by the outcome under study is circular, and
  the natural failure distribution of any actively maintained project is
  test-heavy. Seeded faults, capped at 2 per category and 16 overall, are what
  turns SRQ2 from an observation about one skewed cohort into a question with an
  answer. Not started, and the item with the longest tail.

### What this means in order of urgency

1. Wire the baseline into a run. Without it the primary question has no anchor.
2. Decide the root-cause wording -- rubric, or narrow the question.
3. Decide categories, and whether controlled defects are in scope. SRQ2 depends
   on it.
4. Find a second reviewer. Agreement is the ceiling on every accuracy claim
   above, and it is also a supervisor condition.

## Ground truth with a single annotator

Decided 18 October 2026: there will be no second reviewer. Independent
verification was a supervisor condition, so the decision has to be disclosed
with its substitute plan rather than quietly omitted.

**What can no longer be claimed.** No inter-rater reliability. Cohen's kappa
must not be reported as inter-annotator agreement, and nothing may describe the
ground truth as independently verified. `--mode verify` in
`automated_scripts/annotate_blind.py` remains in the tool, unused for its
original purpose.

**What substitutes, strongest first.**

1. **Documented repair as the anchor.** This is why the sampling window matters
   and it is now doing double duty. In the 14-45 day frame roughly 85% of scrapy
   cases and 50% of vite cases have a findable repair, so for most of the cohort
   the ground truth rests on an artefact the project's own developers produced
   rather than on one person's reading. It also permits a real analysis rather
   than an assurance: report accuracy separately for repair-anchored and
   judgement-only cases. If the two are close, that is empirical evidence that
   the annotation is not driving the result.
2. **Blind annotation**, already implemented. State precisely what it does. It
   closes *contamination* -- labels cannot be shaped by model output, because no
   model output is ever shown. It does not address *reliability*. Conflating the
   two is the error to avoid, because a single annotator who never saw model
   output can still be consistently wrong.
3. **Intra-rater (test-retest) agreement.** Re-annotate roughly 20 cases after a
   gap of one to two weeks with `--mode verify` under the same annotator id. The
   mode shows neither the previous label nor any model output, and adjudication
   snapshots the first label into `annotator_*`, so both survive and can be
   compared. Report it as intra-rater self-consistency, explicitly not as
   inter-rater agreement. **Kappa is not implemented** -- it appears only as a
   comment at `annotate_blind.py:386`, so this needs a small piece of code.
4. **Transparency.** Publish the full annotation set with its checksums in the
   freeze package and the appendix so a reader can audit every label, alongside
   the procedural checks `audit_annotations` already enforces: every annotation
   must cite evidence lines, and a root cause may not restate its category.

**Why the revised research questions survive this better than the originals.**

* **SRQ1 is nearly immune.** Any labelling bias applies identically to both
  models, so it cancels in the contrast. The paired comparison measures two
  conditions against the same labels, whatever those labels' absolute quality.
* **SRQ2 as reformulated is largely immune.** Log length, job structure and the
  `lost_at` filter stage are measured mechanically, not annotated. Only
  preprocessing recall touches annotated evidence lines, and none of it depends
  on the category judgement.
* **The primary question is the exposed one**, because it is the only absolute
  accuracy claim. This is where the baseline earns its place: "beats
  deterministic rules by X" is far more robust to annotation quality than "is
  X% accurate".

**How the conclusion should be scoped.** State boundary-condition findings with
most confidence, because they rest least on annotation -- the ~40,000-line
preprocessing wall, umbrella jobs, JVM monorepo intractability. State relative
claims next: model against model, system against baseline. State absolute
accuracy as conditional on a single-annotator ground truth. Lead the limitations
with that, name the direction of possible bias, and present the repair-anchored
comparison as the evidence bearing on it.

## Where the thesis stands, 18 October 2026

The apparatus is close to complete and the evidence is at zero. That is an
unusual position and the risk in it is specific, so it is recorded plainly.

**Strong.** 148 offline tests, checksummed manifests, immutable study
directories, config SHA-256 provenance, blind annotation with adjudication,
leakage guards, triage that re-runs offline from raw logs, reporting that
recomputes from per-log files so an interrupted run still reports correctly. Plus
findings that are measured rather than asserted: the ~40,000-line preprocessing
wall with a clean 0-of-22 against 5-of-5 separation; umbrella jobs as a
construct-validity problem rather than a size problem; JVM monorepo CI shown
intractable across five projects; the filter's line-cap defect, whose one-line
fix moved accuracy from 12.5% to 43.8% and recall from 32.6% to 57.6%; repair
traceability roughly doubling under the 14-45 day window.

**At zero.** Ground truth. All 27 existing annotations are void -- 16 died with
django, 11 with gradle -- and the live cohort has none. Also outstanding: the
baseline not wired into a run, 34 codebook definitions, controlled defects, and
supervisor approval of a plan whose §3 and §10 still name django.

**The binding constraint is annotation time.** Three repository attempts --
django, gradle, vite -- consumed the weeks that would have gone to annotation.
That was not waste: the selection work was necessary and produced the best
findings here. But the consequence is that what remains is annotation-dominated,
and annotation cannot be parallelised, automated or delegated. The minimum path
is roughly 80 cases at 15 development, 15 pilot and 50 held-out, each requiring a
5,000 to 40,000-line log to be read.

**Recommended scope reduction**, if the seminar date requires results rather
than work in progress:

1. Write the codebook before annotating anything. Annotating without it means
   inconsistent labels and a second pass.
2. Shrink the cohort to about 10 development, 10 pilot, 30 held-out. A smaller
   cohort honestly reported beats a larger one half-annotated, and the
   boundary-condition findings do not need a large n.
3. Drop controlled defects and take the narrower SRQ2, which does not need them.
4. Send the evaluation plan now. It is stale, and supervisors are the gate on
   the held-out run.

## The cohort, collected 18 October 2026

`thesis_scrapy_vite_2026`. Frame `2026-09-03..2026-10-04`, recorded in the
collection manifest as `sampling_window.created_range`.

131 raw logs, 99 eligible, 32 excluded (31 `out_of_scope_job`, 1 `token_error`).
Zero duplicate error signatures, zero duplicate families, zero bot runs, zero
umbrella jobs -- so every eligible case represents a distinct family.

| | eligible | median lines | max | over 40k |
| --- | --- | --- | --- | --- |
| scrapy/scrapy | 60 → 54 | 5,348 | 52,421 | 18 |
| vitejs/vite | 45 | 4,832 | 5,244 | 0 |

vite is exactly what the scout predicted: tight, consistent, nothing near the
filter's limit. scrapy carries all 18 large logs, and they are genuine
`tests (...)` matrix jobs -- verbose pytest output rather than aggregation, so
the umbrella rule correctly does not fire on them.

**Do not assume those 18 behave like gradle's.** The ~40,000-line boundary was
measured on five gradle cases. The filter now keeps the *last* 500 lines and
pytest prints its failure summary at the end, so scrapy's large logs may retain
their evidence where gradle's did not. Whether the boundary transfers is unknown
until those cases are annotated and `preprocessing_recall` can be computed, and
assuming it transfers would be repeating an error already made once here.

**scrapy collected 71 of 100 requested**, which is the
`complete_with_warnings` status. Not the sampling window:
`collect_logs_from_repo` fetches a single API page of 100 candidate runs, and 29
were undownloadable or had no job. Paginating would fix it; the cohort is
oversized regardless.

**A scope leak was caught and closed.** Four cases were mypy jobs -- scrapy
names them `checks (3.10, mypy)`, `"check"` is an in-scope pattern, and `"mypy"`
was not in the `lint_format` exclusions, so they classified as `build_test`.
This is precisely how django's `Run Quality Checks on a PR` was admitted. Added
`mypy`, `pyright`, `typecheck`, `type-check` and `pre-commit` to the excluded
patterns; `pre-commit` resolves a question open since the gradle cohort, on the
grounds that it runs whatever hooks a repository configures, predominantly lint,
and aggregates many of them under one job. Re-triage took the cohort from 105 to
99.

## The split, written 18 October 2026

Targets 10 / 10 / 30, rule `combined`, seed `20261010`.

| bucket | allocated | scrapy | vite | over 40k | median lines |
| --- | --- | --- | --- | --- | --- |
| development | 11 | 6 | 5 | 2 | 4,793 |
| pilot | 11 | 6 | 5 | 2 | 4,862 |
| held_out | 31 | 17 | 14 | 5 | 4,793 |
| reserve | 46 | 25 | 21 | 9 | 4,874 |

**53 cases to annotate.** Each partition sits one over target because families
are allocated whole and one can tip a partition past its quota; splitting a
family is the thing that must never happen, so the overshoot is accepted.

Large logs are spread at 16-19% per bucket rather than concentrated, which was
the risk worth checking: held-out keeps about 26 cases well inside the filter's
reach even if all five of its large ones lose their evidence, so the single
confirmatory run will not be dominated by ties.

**`make_split.py` gained a `RESERVE` bucket.** Everything past quota previously
fell into held-out, which produced a 77-case held-out set from a target of 30. A
held-out set larger than can be annotated is not a larger held-out set but an
undefined one: scoring needs ground truth, so unannotated cases parked there
would leave the confirmatory set to be decided case by case during annotation.

Two guards came with it. `check_no_family_spans_partitions` now covers the
reserve, so a reserved case cannot share a fault with a held-out one. And the
manifest records `reserve_is_outside_the_confirmatory_analysis: true` -- moving a
case from reserve into held_out after any held-out result has been seen would
make the held-out set a function of those results, so a later extension requires
a new split manifest with a stated reason, exactly as a re-split does.

## One fault had entered the cohort nineteen times

Found 18 October 2026, from the first three annotations: two of them described
the same root cause in different runs.

A VCS-installed `aiohttp` whose wheel build fails because GCC cannot find its C
sources appeared in **19 of 99 eligible cases**, spread across development (3),
pilot (2), held_out (9) and reserve (5). Nine of 31 held-out cases were the same
fault as three development cases -- precisely the leakage the grouped split
exists to prevent, and it would also have meant 29% of the confirmatory set was
one fault.

`compute_error_signature` hashed the first 20 matching error lines nearly
verbatim, and three kinds of run-to-run variation defeated it:

* **Revisions and digests.** `aiohttp @ git+https://...@3489636c` names the
  commit built, which differs every run. The existing `0x`-prefixed rule did not
  reach a bare hex SHA.
* **Elapsed times.** `evaluation failed :( (177.25 seconds)`.
* **Ordering.** A parallel build races its `cc1: fatal error:` lines out in a
  different order each run, so one set of compiler errors hashed many ways.

All three are now normalised, and the selected window is sorted before hashing.
**Selection still happens in document order** -- sorting the whole list first was
tried and merged six unrelated pypy failures, because generic noise such as
`##[error]Process completed with exit code 1.` sorts ahead of the informative
lines and crowded them out. Measured on this cohort: the fault collapses from 19
signatures to 1, the cohort goes from 99 distinct signatures to 81, and the only
group formed is the genuine one.

**Re-triaged and re-split**, reason recorded in the split manifest. 99 -> 81
eligible: 17 excluded as `duplicate_error` under the two-per-repository cap and
one more as `duplicate_failure_family`. The fault now appears **once**, in
held_out, with no development or pilot exposure.

**Two of the three annotations are void** -- both annotated cases were capped
out, and two other instances were retained instead. Making the cap prefer
already-annotated cases was considered and rejected: triage would then depend on
annotation progress, so re-running it at different stages would yield different
cohorts, which is a worse loss than half an hour of reading. The two were the
same fault in any case, so one of them was duplicate effort regardless.

| bucket | cases | scrapy | vite | over 40k |
| --- | --- | --- | --- | --- |
| development | 11 | 5 | 6 | 2 |
| pilot | 11 | 5 | 6 | 3 |
| held_out | 31 | 14 | 17 | 5 |
| reserve | 28 | 12 | 16 | 8 |

**53 cases still to annotate**, one of which is already done.

## Evidence line numbers must be read in the archive's frame

A GitHub run's stored log is a ZIP of one file per job, concatenated under
`=== name ===` headers, so a 47,019-line archive can hold 80 job sections and
the failing job's output may begin tens of thousands of lines in. Reading that
job in GitHub's web UI shows it numbered from 1 instead.

The third annotation hit this. Its reading was correct -- 
`test_csv_dropped_fields_warning` really did fail with three captured log records
instead of one, in the `tests (ubuntu, 3.14, no-reactor-extra-deps)` job -- but
the cited lines 410-657 fall inside a different job's section. That job's output
starts at line 10,480 and the described evidence sits at roughly 10,890-11,131.

This is measurement-critical. The model is shown `[Line N]` numbered from the
start of the stored archive, so `evidence_line_scores` and
`preprocessing_recall` are computed in that frame. Annotated numbers in a job's
local frame would score near zero even where the model cited exactly the right
lines. **32 of the 99 pre-re-triage cases were exposed** -- every case whose
failing job is not the first section.

`failing_job_section` in `automated_scripts/annotate_blind.py` now prints the
failing job's line range when presenting a case, so the reviewer can jump there
and still read the numbers the scoring uses. It prints nothing rather than
guessing when the job cannot be located. The numbered log the tool writes to
`ground_truth/review_logs/<log_id>.txt` was always in the correct frame; the
offset just made it impractical to find the failure in it.

`gh_scrapy_scrapy_36330213779` is still eligible and still in development, so
its `failure_lines` need redoing by hand.

## The filter is scoped to the failing job

Changed 20 October 2026, on evidence from the first eleven annotated development
cases -- which is what the development partition is for.

**What the first measurement showed.** Preprocessing recall over all eleven:
**ten of eleven lost every verified evidence line**, each at `line_cap`. That
included vite logs of under 5,000 lines, so size was not the cause. Position
was.

A stored run log is a ZIP of one file per job, concatenated under `=== name ===`
headers, and it **ends with the runner's own `*/system.txt` files** -- about
eighty of them in a scrapy run. Keeping the last 500 keyword-matching lines of
the archive therefore lands in system logs, while the failing job sits in the
middle. The tail heuristic that fixed the django and gradle cohort, where logs
were short and single-section, is actively wrong for a multi-job archive.

**What scoping does.** `scope_to_failing_job` in `src/api/log_sections.py`
narrows the log to the failing job's own section before filtering. Measured on
the five scrapy cases whose annotations are verified correct:

| case | archive lines | job section | recall before | after |
| --- | --- | --- | --- | --- |
| 37192544648 | 34,978 | 1,174 | 0% | 73% |
| 37112769007 | 35,752 | 1,172 | 0% | 85% |
| 36564226178 | 47,712 | 1,277 | 0% | 74% |
| 36330213779 | 47,019 | 1,056 | 0% | 100% |
| 35055489720 | 5,250 | 1,177 | 40% | 50% |

The residual loss was token truncation inside the section, and most of it was
not log content at all -- see the next section.

**Three consequences for the thesis.** The ~40,000-line boundary largely
dissolves, because what bounds the system is the failing job's size rather than
the archive's. The local model's 24,576-token context stops being the binding
constraint on both conditions. And the artifact's input is now the failing job's
log, not the run's -- which has to be stated as a design decision, and is
defensible on its own terms, since a diagnostic tool in practice is pointed at
the job that failed.

**Line numbers stay in the stored log's frame.** The offset is added back, so a
model citation and an annotated evidence line remain directly comparable --
`evidence_line_scores` compares exactly those two. An unlocatable job falls back
to the whole log rather than guessing a section, since scoping to the wrong job
would hide the failure completely.

One definition lives in `src/api/log_sections.py` because the filter, the recall
trace and blind annotation all need to agree on it. A private copy in any one of
them would let the model's view and the annotated numbers drift apart. This is
the same lesson as `is_bot_run` sitting in `tools/` where triage could not see
it.

### Terminal escape codes were spending the token budget

vite's test output carries thousands of colour and cursor sequences
(`\x1b[41m\x1b[1m FAIL `), and nothing stripped them before the log reached the
model. They tell the model nothing and they cost budget.

Stripping them per line, measured over the eleven development cases, lifted mean
preprocessing recall from **80% to 91%** and took the worst case from 3% to
100%. `strip_ansi` and `ANSI_ESCAPE` live in `src/api/filtering.py`. Stripping
is per line, so line numbers do not move -- a test asserts the failing line keeps
its original number, because the model's `[Line N]` markers and the annotated
evidence have to stay in one frame.

**`compute_error_signature` in `automated_scripts/triage.py` keeps its own
narrower escape-code pattern on purpose.** Widening it there would change every
error signature, which changes which cases the duplicate cap removes, which
changes the collected cohort. A comment beside the new pattern records this so
the two are not unified later by someone tidying up.

### The token budget is now a hard invariant

`_truncate_to_tokens` trimmed from the middle until head and tail were five lines
each and then stopped. A log whose individual lines are enormous therefore
escaped the limit: `gh_vitejs_vite_36550600858`, in the pilot partition, returned
a **24,246-token** prompt against a 12,000 budget. With about 4,900 tokens of
prompt overhead that needed roughly 29,000 against the local model's 17,408, so
it would have failed or been silently cut by the provider mid-run.

It now clips to the budget as a last resort rather than returning a prompt that
cannot be served. Clipping can cost the final `[Line N]` marker, which is
accepted: a truncated marker is recoverable, an unservable prompt is not. After
both changes the largest filtered prompt across all 81 cases is 11,997 tokens and
none exceeds the budget.

### What the development set finally measures

| stage | mean recall | cases losing all evidence |
| --- | --- | --- |
| whole archive, tail heuristic | 4% | 10 of 11 |
| scoped to the failing job | 80% | 0 of 11 |
| escape codes stripped | **91%** | 0 of 11 |

Seven of the eleven are now fully preserved. This is the number the stratified
analysis rests on, and it is a result in its own right: it says what share of the
verified evidence the pipeline actually delivers to the model.

## Six vite annotations pointed at the wrong matrix entry (resolved)

`failing_job_section` compared section names literally, but GitHub sanitises the
filename: the job `Build&Test: node-24, ubuntu-latest` is stored as
`4_Build&Test node-24, ubuntu-latest.txt`, with the colon dropped. No section
matched for any vite case, the offset banner stayed silent, and all six vite
annotations were recorded against the first failing matrix entry rather than the
one `failing_job` records. Their line numbers are in the archive's frame and the
readings are coherent; they simply describe a different job of the same run.

The matcher now normalises to letters and digits before comparing. **The six
were redone on 20 October 2026 and all eleven development annotations are now
verified to fall inside the failing job's section** -- the six vite ones were
removed from `ground_truth.json` (backed up first) so the annotator would offer
them again with the banner showing. All six came back at 100% preprocessing
recall.

This also leaves a methodological point to settle: when several matrix entries
of one run fail, the recorded `failing_job` is whichever the API reported first.
Triage and the scope rules already key on `failing_job`, and the filter now
scopes to it, so annotation has to use the same anchor or the two sides are not
comparable. That rule belongs in the codebook.

**All eleven development cases were annotated `test_failure`.** The category skew
predicted from the repository gate has arrived in full.

## The first paired development run, 20-21 October 2026

`experiments/development_20261020_221319`, eleven development cases, both
conditions, no parse failures or inference errors. These results refine the
system; they are not findings.

**Category accuracy was 11/11 for both models, which cannot separate them.**
Every case in the cohort is annotated `test_failure`, so the measure has no
variance to work with and both conditions sit at the ceiling.

*Qualified twice, 21 October 2026.* First written as "it means nothing", on the
assumption that any classifier would reach 11/11; the rule-based baseline scores
**2 of 11**, so the measure does separate models from fixed rules. Then the
pilot showed it separates the two models from each other as well -- 81.8%
against 54.5% -- because that partition contains four categories. The
saturation was a property of this development sample, not of the cohort. See the
pilot section below.

**Evidence lines do discriminate, and the two models are far apart:**

| | precision | recall | F1 |
| --- | --- | --- | --- |
| `openai/gpt-5.6-terra` | 0.89 | 0.56 | **0.67** |
| `local/thesis-qwen3.5:9b-24k` | 0.78 | 0.23 | **0.34** |

Both models are precise and incomplete -- what they cite is usually genuine
evidence, but they mark a fraction of the annotated span. The hosted model finds
0.56 of it, the local model 0.23. The local model's deficit is almost entirely
recall; its precision holds at 0.78.

**The pipeline reported the two as identical.** `statistical_tests.json` for
this run says `"Models performed identically on all samples"`, `p = 1.0`, because
McNemar is computed on category accuracy and there are no discordant pairs to
find. On the same eleven cases a Wilcoxon signed-rank over paired evidence-line
F1 gives **p = 0.00098, the hosted model ahead in 11 of 11 cases, mean
difference +0.31 F1**. The category test was not wrong; it was answering a
question this data cannot distinguish. As the tool stood, **SRQ1 was
unanswerable from what it reported** even though the data answers it clearly.

`StatisticalTests.paired_evidence_line_test` now runs alongside McNemar and is
surfaced in the HTML comparison. It reuses `evidence_line_scores` rather than
reimplementing F1, and excludes cases with no annotated lines as unscorable
rather than scoring them zero -- a missing annotation must never read as a model
failure. Both tests are reported together: each answers part of SRQ1, and
McNemar will have something to say on a cohort with category variance.

The stored `statistical_tests.json` for this run predates the change and does
not carry the new field. Reporting is read-only over stored results by design,
so it is not backfilled; the next run writes it.

**Three things this run establishes.**

1. The pipeline works end to end on this cohort: 22 diagnoses, no failures, no
   unparsed responses, no prompt exceeding the token budget.
2. Evidence-line F1 should be the primary measure for this study, not category
   accuracy. The reformulated primary question already names the evidence lines;
   this is the evidence for that wording.
3. Part of the 0.56 recall is definitional rather than error. The annotation
   marks whole assertion blocks including the expected/actual diff; the models
   mark the failure line and stop. Nothing says where a failure's evidence ends,
   and that rule is one of the 34 missing codebook definitions. It is now the
   one with the clearest evidence behind it.

**Still outstanding and now more visible:** the rule-based baseline would also
score 11/11 on category here, which is the sharpest possible demonstration of
why the floor matters. It is still not wired into a run.

## The codebook is drafted

21 October 2026. `docs/thesis/CODEBOOK.md`, no `TO WRITE` markers left, not
frozen. Revisable until pilot annotation begins; after that §11 records every
change and the affected cases are re-checked.

**§0 defines an evidence line**, which was the gap that mattered. The first
paired development run showed evidence-line recall measuring the annotator's
marking style as much as the models: 37 lines marked against the model's 12 on
one case, including five blank lines. The author chose the narrow reading --
lines that *state* the failure, not every line the tool prints while reporting
it.

**A prediction of mine was wrong and the record should say so.** I expected the
narrow rule to raise the models' recall, on the theory that most of what they
"missed" was not evidence. After trimming the 34 blank lines, worker banners and
fixture reprs, hosted F1 went 0.67 to 0.66 and local stayed at 0.34. The models
genuinely miss about half the evidence; they had also been citing some of the
blank lines themselves. The finding is better for being measured under a stated
rule, and it is unchanged in substance: 11 of 11 to the hosted model,
p = 0.0010, mean difference +0.33 F1.

**§0.2 fixes the evidence to the job in `failing_job`.** Triage scopes on it,
the filter narrows to its section, and the annotation is compared against what
the model cites from that section. Annotating a different matrix entry makes the
two sides describe different jobs, which is what went wrong with the six vite
cases.

**§§1-8 are defined and §10's five tie-breaks are resolved.** Six of the eight
categories have no development example, and the definitions say so rather than
pretending to be grounded. The tie-breaks settle: label by what was being
attempted rather than the mechanism that failed; `syntax_error` requires a
reported parse position; an HTTP status means the endpoint answered, so 401 and
403 are `permission_denied` rather than network failures; and a check script
that runs no test suite is out of scope rather than a `test_failure`.

AI assistance is disclosed in the document header, naming what was drafted and
what the author decided.

## The baseline runs as a third condition

21 October 2026. `src/api/baseline.py` existed and nothing called it; the
primary research question is worded "relative to a deterministic rule-based
baseline", so the question was unanswerable as the tool stood. It was also one
of the commitments made to supervisors.

`run_baseline` in `automated_scripts/benchmark_models.py` now runs it on
identical filtered input, in the same record shape, scored by the same code. It
runs **first**, before any network call, so a provider failure still leaves a
complete baseline condition on disk. The ruleset checksum travels with every
record, so a ruleset edited after results were seen cannot pass unnoticed.
`--no-baseline` opts out.

**Measured on the eleven development cases:**

| condition | category | evidence-line F1 |
| --- | --- | --- |
| baseline, keyword rules | **2/11** | **0.01** |
| `local/thesis-qwen3.5:9b-24k` | 11/11 | 0.34 |
| `openai/gpt-5.6-terra` | 11/11 | 0.66 |

**A second prediction of mine was wrong, and this one in the project's favour.**
I expected the baseline to score 11/11 on category too, which would have shown
the category metric to be entirely dead. It scores 2 of 11. The metric cannot
separate the two models from each other -- that part stands -- but it separates
models from fixed rules decisively. The earlier claim that category accuracy is
"dead" was too strong: it is saturated *between the models*, not uninformative
in general.

**Why the baseline fails is the useful part.** It answers `permission_denied`
six times, because its rules match the bare string `"403"` and the word
`"forbidden"`, which appear incidentally in test output -- an HTTP status in a
fixture, a URL containing 403. A keyword matcher cannot distinguish a failure
from a mention of one. That is precisely the discrimination the thesis claims an
LLM provides, and it can now be demonstrated rather than asserted.

**A bug avoided while wiring it.** The statistical tests compare the first two
conditions in `all_results`, and the baseline runs first, so adding it would
have silently reported *baseline against hosted* as the model comparison. The
baseline is now explicitly excluded from that pair, and each model additionally
gets a `versus_baseline` entry carrying both McNemar and the evidence-line test.

## Supervisor approval, and the workflow defects it exposed

21 October 2026. Approval granted, including the single-annotator design. That
removed the methodology hold and immediately showed that the tool had never been
made partition-aware after the split was introduced. Six defects, all from one
cause.

**`final` ran the whole cohort.** `cmd_final` passed no `--partition`, so the
held-out experiment would have covered all 81 eligible cases -- every
development and pilot case the system was tuned on included -- and the
confirmatory result would have been scored partly on its own tuning data. The
most serious of the six. Now `--partition held_out`, asserted by a test.

**The pilot partition was unreachable.** `pilot` ran the five-case smoke cohort,
so the 11 pilot cases had no command at all. `pilot` now runs the partition and
the smoke rehearsal is `pilot-smoke`, matching the existing `-smoke` naming.
`engineering` still uses the smoke one.

**Ground-truth progress was counted against the whole cohort.** The stage was
complete only at 81 annotations; 53 are ever annotated, so it could never
complete -- and `cmd_final` requires that stage. The held-out run was
unreachable by arithmetic. Progress is now reported per partition:
`development 11/11, pilot 0/11, held_out 0/31`.

**Status advised re-collecting a fixed cohort.** `next_action` returned
`cohort` whenever collection was `PARTIAL`, which it permanently is -- 131 of
160 requested, because GitHub drops runs from the failure listing. Once triage
has produced a cohort it is immutable and re-collection is refused, so the
advice was simply wrong.

**The single-annotator guard still refused after approval.** Supervisor approval
does not clear a check inside the tool. Rather than weakening the guard, the two
findings are downgraded from `blocking` to a new `disclosed` severity when
`methodology_approval.json` is present and names an approver and a date. A
disclosed finding never disappears and prints ahead of warnings -- the point of
accepting a weakness is that it is reported, not that it stops being true. A
recorded file rather than a command-line flag, because the approval is an
external event with a date and because a flag would leave no trace. `next_action`
no longer suggests recruiting a verifier.

**The freeze record was thin, and nothing required a pilot first.** It now
carries each condition's identity -- the hosted route and reasoning effort, and
for the local alias the `ollama show` output with its architecture, parameter
count, quantization and context, plus the Modelfile checksum, because
`thesis-qwen3.5:9b-24k` is an alias and the name alone does not say which weights
ran. The two completion budgets are recorded separately (4,096 hosted, 7,168
local) where one number previously hid the difference. Added: the codebook
checksum, the methodology approval, the freeze approver, and the pilot state.

Three new gates refuse a freeze: **no completed pilot run** (the held-out
experiment happens once and must not be the first full exercise of the
pipeline), **no recorded freeze approver**, and **no methodology approval**
where ground truth rests on one annotator. `--allow-dirty` previously forgave
every gate; it now forgives only an uncommitted worktree.

**The shell routing had no tests**, which is how four of these survived while
170 Python tests passed. Five routing tests now assert what each command runs:
that `final` is scoped to held-out, that `pilot` and `pilot-smoke` are distinct,
that `engineering` uses the smoke pilot, that the default study config is the
active one, and that every dispatched command has a function behind it.

## The pilot run, 21 October 2026

`experiments/pilot_20261021_132809`, eleven pilot cases, three conditions, no
parse failures. Results refine the system; they are not findings.

| condition | category | evidence F1 | grounding | time/case | cost |
| --- | --- | --- | --- | --- | --- |
| baseline, keyword rules | 9.1% | -- | n/a | 0 ms | $0 |
| `openai/gpt-5.6-terra` | **81.8%** | 0.32 | 100% | 12.9 s | $0.44 |
| `local/thesis-qwen3.5:9b-24k` | 54.5% | 0.16 | 68.5% | **495 s** | $0 |

**Category accuracy discriminates, and the earlier claim that it was dead was
wrong twice over.** The pilot contains four categories -- `test_failure`,
`dependency_error`, `timeout`, `network_error` -- and with that variance the
measure separates all three conditions cleanly. The development set was
single-category by accident of sampling, not because the cohort is
single-category. Corrected in the development-run section above.

Significance: hosted beats local by 27 percentage points on category but with
only three discordant pairs that is **not significant** (McNemar p = 0.248). On
evidence lines it is -- hosted ahead in 10 of 11, p = 0.002. Against the
baseline, hosted is significant on category (p = 0.013) and local is not
(p = 0.074).

**The local model's latency is a finding for SRQ1:** 495 s per case against the
hosted model's 12.9 s, with one case at 1,125 s. Roughly 40x, on identical
input.

### The permutation test reported p = 0.0, and was wrong

It printed `p = 0.0` where McNemar reported 0.248 on identical data. The
observed statistic was computed as `a.mean() - b.mean()`, which lands one unit
in the last place above the same quantity computed from the difference array --
in floating point `9/11 - 6/11 > 3/11` -- so **no permutation ever counted as
extreme** and the p-value collapsed to zero. The correct value for three
discordant pairs all favouring one model is 0.25.

Fixed by computing the observed statistic from the array the permutations are
drawn from, with a tolerance on the comparison. The p-value is now the unbiased
estimator `(extreme + 1) / (n + 1)`: resampling cannot demonstrate p = 0, since
the floor is set by how many permutations were drawn. Recomputed on the pilot
data the two tests agree -- McNemar 0.248, permutation 0.257.

A reported p = 0.0 would not have survived examination. Three tests now cover
it, one of which asserts the two tests agree on the same data.

### Evidence-line recall is confounded with annotation breadth

Evidence F1 fell from 0.66 and 0.34 on development to 0.32 and 0.16 on pilot.
The cause is not annotation drift: the median annotated line count is 21 on
development and 23 on pilot.

The cause is that **the models cite a roughly constant number of lines** -- 6 to
16, mostly 7 to 12 -- however many the annotation marks. Where a case is
annotated with 54 lines, a model citing 6 is capped at 11% recall even if all
six are correct. Across the 22 cases the correlation between annotated line
count and the hosted model's F1 is **r = -0.41**, and cases with 34 or more
annotated lines average F1 0.24 against 0.55 for the rest.

So recall, and therefore F1, partly measures how broadly the annotation marks
evidence rather than how well the model locates it. §0 of the codebook fixed
*what kind* of line counts as evidence; it does not fix *how many*.

**Precision is largely independent of annotation breadth** -- 0.5 to 1.0 across
both partitions -- and it matches what the prompt asks for: point at the
failure, not enumerate it.

### Resolved 21 October 2026: both statistics, split by claim

The first instinct was to make precision the single primary measure. That was
based on an overstatement of the confound, and switching wholesale would have
cost a real result for nothing.

**Breadth varies between cases, but within a case both conditions face the same
annotation.** In a *paired* test it therefore cancels: it damages the absolute
figure, not the contrast. Measured on both runs, hosted first:

| run | precision | F1 | mean lines cited |
| --- | --- | --- | --- |
| development | 0.89 / 0.77, p = 0.008 | 0.66 / 0.34, p = 0.001 | 13.1 / 6.2 |
| pilot | 0.69 / 0.59, **p = 0.266** | 0.32 / 0.16, **p = 0.002** | 10.1 / 4.5 |

Precision alone loses the pilot comparison. The contract, settled before
freezing:

* **F1 is the single hypothesis test.** Breadth cancels within pairs, and F1
  uses signal precision discards. One p-value is reported, and it is this one.
* **Precision is a descriptive capability figure with no p-value.** "When the
  system cites a line, is it evidence?" is not a claim about a difference
  between conditions, and two tests over the same pairs would be multiple
  testing without a correction.

A test asserts the result carries exactly one key containing `p_value`.

**What precision hides is in the last column.** The local model cites roughly
half as many lines -- 4.5 against 10.1 -- which is a genuine behavioural
difference, and precision is blind to it: a model citing one correct line scores
1.00. The mean citation count is therefore reported beside both statistics, and
a test documents the blind spot by asserting that precision ties a thorough
model with a minimal one while F1 and the citation count separate them.

**For the write-up:** report the absolute capability as precision and the model
comparison on F1. A single headline "evidence accuracy" figure would be
answering two questions at once.

No re-annotation is needed, so the 22 existing annotations stand.

## Where things stand, 25 October 2026

Fifteen days to the seminar. **The tool is finished; the remaining work is
annotation and writing.**

```
development  11/11  annotated, paired run complete
pilot        11/11  annotated, paired run complete
held_out      0/31  nothing annotated
```

Committed through `75ae285`, worktree clean, 186 tests pass. Every blocker that
is not annotation is cleared: supervisors approved on 21 October, the codebook
is written, the baseline runs as a third condition, the evidence-metric contract
is settled, the freeze gates work, and the statistical tests are correct.

The pilot earned its place: it caught a crash in the baseline wiring, a
permutation test reporting `p = 0.0` where the correct value was 0.25, and the
annotation-breadth confound -- all on a partition the plan permits inspecting,
before the run that happens once.

**The honest arithmetic.** Thirty-one logs remain, and the pilot cases carried 20
to 56 evidence lines each, so 10 to 13 hours of reading is realistic. Then the
held-out run, then the document. Nothing in the tooling changes that number.

**A decision to make deliberately rather than discover.** If held-out annotation
is not finished by about 1 November, cut the held-out set to a size that can be
completed. A smaller confirmatory set honestly reported is worth more than an
incomplete one, and choosing it in advance is defensible where running out of
time is not.

### A freeze record was created by accident and removed

On 25 October an agent ran `freeze ACTION=create APPROVED_BY="test"` intending
only to exercise the gate, and the command created a real record: approver
`"test"`, frozen against the 22-annotation ground truth. It was backed up and
deleted, and `freeze verify` now correctly reports that no record exists.

It could not have corrupted a result silently -- `final` verifies against the
record, and the ground-truth checksum changes the moment held-out annotation
begins, so verification would have refused. But it was a false provenance
artifact, and `create` refuses when a record already exists, so it would have
blocked the real freeze.

Recorded because the lesson is in the tool, not the mistake: **`freeze create`
has no dry-run.** Checking whether the gates pass requires performing the act
they gate. A `--check` mode that reports the blocking problems without writing
would make the gates inspectable without creating anything.

## Open decisions

Six, listed in `docs/thesis/EVALUATION_PLAN.md` §10. The ones that block
annotation:

- Keep eight failure categories and widen the data, or cut the categories down.
  The codebook now records that six of the eight have no development example and
  78 of 81 cases fail at a test step, so this is close to being settled by the
  data rather than by choice.
- Score root-cause correctness with a rubric, or narrow the primary research
  question to categories and evidence lines.
- ~~What happens to gradle.~~ Settled 18 October 2026: replaced by
  vitejs/vite. The next step is a new config and a fresh collection pass.
- **The research questions.** Revised wording is drafted in
  `EVALUATION_PLAN.md` §3 with the originals beside it in §3.2. **The author is
  writing the plan that will actually be sent.** SRQ2 changed meaning and needs
  supervisor agreement; the Primary's reference to a baseline is satisfied now
  that the baseline runs as a condition.
- **Whether `freeze create` should gain a `--check` mode** that reports the
  blocking problems without writing a record. Its absence caused a false freeze
  record to be created on 25 October simply by inspecting the gates.
- **Whether to re-triage `thesis_gradle_scrapy_2026`.** The two rules it would
  apply now exist -- `is_umbrella_job` in `src/evaluation/job_scope.py`, and
  `BOT_MARKERS` entries for the five maintenance workflows that slipped through.
  Triage is offline and re-runnable from the raw logs, so this touches no config
  and no collection manifest. It is probably not worth doing on this cohort,
  because replacing gradle means collecting a new one; the rules matter for the
  next collection, not this one.

One commitment made to supervisors that is not implemented: **root-cause /
suggested-fix quality scoring**. The **rule-based baseline** was wired in on
21 October 2026 and runs as a third condition. A third,
**independent second review**, has been declined -- see the single-annotator
section above for the substitute plan, which has to be disclosed to supervisors
rather than left as a silent omission.

## Where to look

| Path | What |
| --- | --- |
| `docs/thesis/PROGRESS_REPORT_2026-10-21.md` | Standalone progress report: state, findings, RQ changes, what remains |
| `docs/thesis/ACTION_ITEMS.md` | What to do next, in order |
| `docs/thesis/CODEBOOK.md` | Category rules. Skeleton; definitions not written |
| `docs/thesis/SUPERVISOR_CONDITIONS.md` | Supervisor conditions and the response to each |
| `docs/thesis/EVALUATION_PLAN.md` | The plan to send to supervisors |
| `docs/architecture/CONTROLLED_STUDY_RUNBOOK.md` | Exact operating procedure |
| `docs/architecture/architecture.png` | The system in one picture |
| `docs/archive/` | Superseded. Describes RAG, ChromaDB and models that are gone |
