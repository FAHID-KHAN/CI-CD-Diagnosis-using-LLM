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
| Study data | `thesis_pair_2026`: 179 raw, 56 eligible, 27 annotated, split written. Four development runs in `experiments/`. |
| Active config | `configs/thesis_gradle_scrapy_2026.yaml` — gradle/gradle and scrapy/scrapy |
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

**Section scoping was tried and does not work.** Large gradle logs are
26-section archives and the evidence does sit in only two or three sections, so
restricting the filter to them looked promising. It was tested two ways against
the five large-log cases: scoping to the sections whose name matches
`failing_job` recovered evidence in 1 of 5 (mean recall 4%), and ranking
sections by error-keyword density and filling the line budget recovered none.
The sections are themselves 3,000-11,000 lines of keyword-dense test output, so
the 500-line cap still crowds the evidence out. Recorded so it is not retried.

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

**Two candidates hold up.** Their sampled logs are genuine CI runs, and 28
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

## Open decisions

Six, listed in `docs/thesis/EVALUATION_PLAN.md` §10. The ones that block
annotation:

- Keep eight failure categories and widen the data, or cut the categories down.
- Score root-cause correctness with a rubric, or narrow the primary research
  question to categories and evidence lines.
- **What happens to gradle.** Its umbrella jobs are undiagnosable by this
  pipeline and excluding them leaves about six usable cases, so the
  cross-repository comparison cannot rest on it as collected. Either replace it
  with another repository, or drop the cross-repository dimension and report
  gradle as a documented boundary. No JVM candidate measured tractable, so a
  replacement means accepting a Python-versus-JavaScript contrast; see the
  preprocessing boundary and candidate sections above for the numbers.
- **Whether to re-triage `thesis_gradle_scrapy_2026`.** The two rules it would
  apply now exist -- `is_umbrella_job` in `src/evaluation/job_scope.py`, and
  `BOT_MARKERS` entries for the five maintenance workflows that slipped through.
  Triage is offline and re-runnable from the raw logs, so this touches no config
  and no collection manifest. It is probably not worth doing on this cohort,
  because replacing gradle means collecting a new one; the rules matter for the
  next collection, not this one.

Two commitments made to supervisors that are not implemented: a **rule-based
baseline**, and **root-cause / suggested-fix quality scoring**.

## Where to look

| Path | What |
| --- | --- |
| `docs/thesis/ACTION_ITEMS.md` | What to do next, in order |
| `docs/thesis/CODEBOOK.md` | Category rules. Skeleton; definitions not written |
| `docs/thesis/SUPERVISOR_CONDITIONS.md` | Supervisor conditions and the response to each |
| `docs/thesis/EVALUATION_PLAN.md` | The plan to send to supervisors |
| `docs/architecture/CONTROLLED_STUDY_RUNBOOK.md` | Exact operating procedure |
| `docs/architecture/architecture.png` | The system in one picture |
| `docs/archive/` | Superseded. Describes RAG, ChromaDB and models that are gone |
