# Failure category codebook

The written rules for assigning a failure category. Two reviewers following this
document should reach the same label; where they do not, the disagreement is in
the rules rather than in anyone's judgement, and the rules get fixed.

**Status: drafted in full, 21 October 2026. Not frozen.** Every definition and
tie-break rule below is a methodological decision, and each is open to revision
until pilot annotation begins. After that, changes are recorded in §11 and the
affected cases are re-checked.

**AI assistance, disclosed because the evaluation plan requires it to be stated
accurately, including for working documents.** The wording throughout this
document was drafted with AI assistance and is subject to the author's revision.
Two things were not: the choice between the narrow and broad readings of an
evidence line in §0, which the author made after reading the disagreement
between their own annotation and the model output on
`gh_scrapy_scrapy_36330213779`; and the decision to exclude check scripts that
run no test suite, which follows an earlier scope decision recorded in §10.

The definitions in §§1-8 are grounded in the cohort where instances exist and
marked as written a priori where they do not — six of the eight categories have
no development example, which is itself a limitation of this study rather than
a gap in this document.

Required by the evaluation plan §3.5, and by Mahade's Q3, which requires a
second reviewer to receive this document plus calibration examples before
beginning independent assessment.

**Version:** draft, 21 October 2026 · **Frozen:** no

---

## How to use this

1. Read the log and identify what actually failed.
2. Work down the categories in the order below. The first one whose definition
   is satisfied is the label.
3. If two seem to apply, consult the tie-break rules in §10.
4. If none apply, the label is `unknown` — see §8 before using it.
5. Record the evidence lines — see §0, which defines what counts.

The order matters: it encodes precedence, so a dependency failure inside a build
step is a dependency failure rather than a build failure.

---

## 0. What counts as an evidence line

**Decided 21 October 2026**, from the first paired development run. This rule
governs the study's primary measure, so it is settled before the remaining
cases are annotated rather than after.

**Definition.** An evidence line is a line that *states* part of the failure: a
line a reader needs in order to say what broke. It is not every line the tool
prints while reporting the failure.

**Include**

- The failure banner or section header that marks where the failure is reported
  (`=================================== FAILURES ===================================`).
- The identity of what failed: the failing test, target, task or step name.
- The assertion, exception or error itself, with the line that shows the
  expected and actual values (`> assert len(caplog.records) == 1`,
  `E assert 3 == 1`).
- The file and line reference the tool gives for the failure
  (`tests/test_exporters.py:416: AssertionError`).
- Logged errors or warnings that are part of the cause rather than background
  noise.
- The final status line and the non-zero exit that concludes the failure.

**Exclude**

- **Blank lines.** A blank line cannot evidence anything. This was the decisive
  observation: an early annotation marked five of them.
- Reproduced source code of the failing test, unless a specific line in it is
  itself the thing that broke.
- Environment and runner banners: interpreter version, worker identifier,
  platform, object reprs of fixtures.
- Progress output, timing summaries and coverage tables.
- Repetitions of the same error in other matrix entries — evidence belongs to
  the job recorded in `failing_job`. See §0.2.

**Why narrow rather than broad.** Both readings are coherent, and the choice
was between marking the whole reported failure block and marking the lines that
state the failure. Narrow was chosen because it measures the model rather than
the annotator's highlighting style. Under the broad reading, a model that
correctly identifies a failure is still penalised for not reproducing blank
lines and source code, and the resulting recall figure mixes capability with a
formatting convention. The cost of this choice is that it demands a judgement
about what is "part of the cause", which §0.1 illustrates.

**Consequence recorded for honesty.** The eleven development annotations were
made before this rule existed. The five scrapy ones used the broad reading and
need bringing under this rule; the six vite ones were already closer to it. No
category or root cause is re-decided by this — only the line selection changes,
and the change is made by the annotator, not derived automatically.

### 0.1 Worked example

`gh_scrapy_scrapy_36330213779`, a pytest assertion failure. Under this rule the
evidence lines are:

| line | content | why |
| --- | --- | --- |
| 10890 | `=== FAILURES ===` | marks the failure report |
| 10891 | `TestCsvItemExporter.test_csv_dropped_fields_warning` | identifies what failed |
| 10907 | `> assert len(caplog.records) == 1` | the assertion |
| 10908 | `E assert 3 == 1` | expected against actual |
| 10909-10910 | `+ where 3 = len([<LogRecord: asyncio ...` | what made it three |
| 10912 | `tests/test_exporters.py:416: AssertionError` | the file and line |
| 10914, 10916 | `ERROR asyncio: Unclosed client session` | the cause of the extra records |
| 10918 | `WARNING scrapy.exporters: CSVExporter dropped fields` | the expected record |
| 11131 | `FAILED tests/test_exporters.py::...` | the status line |
| 11132 | `1 failed, 4808 passed ...` | the outcome |
| 11137 | `##[error]Process completed with exit code 1.` | the non-zero exit |

Not evidence here: lines 10893, 10901, 10903, 10906 and 10911, which are blank;
10892, the `[gw1] linux -- Python 3.14.7` worker banner; 10894-10895, the
fixture object reprs; and 10897-10906, the reproduced body of the test.

### 0.2 Which job's evidence counts

A run's log contains every job in the run. When several matrix entries fail —
the same test breaking on four Python versions, say — **the evidence is the
failing job recorded in `failing_job`**, which is the first failure the GitHub
API reports for the run.

This is not an aesthetic choice. Triage scopes on `failing_job`, the filter
narrows the model's input to that job's section, and the annotated lines are
compared directly against what the model cites. If annotation uses a different
matrix entry than the filter does, the two sides are describing different jobs
and the comparison is meaningless. Six vite annotations were made against the
wrong entry on 20 October 2026 and had to be redone.

When presenting a case, the annotation tool prints the failing job's line range.
Annotate inside it.

---

## 1. `dependency_error`

**Definition.** The run failed while obtaining, resolving, installing or
building a dependency, before the code under test was exercised. The thing that
broke is an input the project declares, not the project's own behaviour.

**Includes.** A version constraint the resolver cannot satisfy; a package that
fails to build from source; a dependency fetched from version control whose
build is broken; a missing distribution for the platform or interpreter.

**Excludes.** A dependency that installs successfully and then misbehaves during
a test — that is `test_failure`, because a test executed and reported. A
dependency declared in the wrong place in a build file, which is
`build_configuration`; see §10.

**Observed in this cohort:** once. `aiohttp` installed from a git reference
fails its wheel build because GCC cannot find the generated C sources. That case
is in the held-out partition, so no development example of this category exists
and the definition above is written a priori rather than from observation.

*Why this label and not another:* the failure happens during installation, and
no test has run at the point the job stops.

## 2. `test_failure`

**Definition.** A test executed and reported a failure. The test runner ran, it
produced a result for at least one test, and that result was a failure or an
error inside the test.

**Includes.** A failed assertion; an unexpected exception raised inside a test
or its fixture; a test that errors during setup or teardown after the runner has
started; a flaky test that fails on this run.

**Excludes.** A failure before the runner starts, whatever the job is called —
if installation, compilation or configuration stopped the job, the label is the
category for that stage. A lint or type-check job that happens to be named
`checks`; those are out of scope entirely, see §9.

**The practical test.** Did the runner produce a per-test result? A pytest
summary line, a vitest `FAIL` for a named spec, a JUnit report. If the output
names a test and says it failed, this is the label.

**Observed in this cohort:** overwhelmingly. All eleven development cases, and
78 of the 81 eligible cases fail in a test-execution step. This is the category
the study is effectively about, and that concentration is a stated limitation
rather than a design intention.

*Why this label and not another:* the runner reached the test and reported on
it. Anything that stops a job earlier has its own category.

## 3. `build_configuration`

**Definition.** The project or its workflow is configured such that the job
cannot do what it was asked to do: compilation, packaging or the workflow
definition itself fails, independently of any test.

**Includes.** A compile or transpile step that fails on the project's own
sources; a build file referring to a target, plugin or path that does not exist;
an invalid workflow file; a required input or environment variable the job needs
and does not have; a toolchain version the build cannot work with.

**Excludes.** A dependency that cannot be obtained, which is `dependency_error`.
Malformed source that the tool reports as a parse error with a position, which
is `syntax_error`; see §10.

**Observed in this cohort:** not observed in the development set.

*Why this label and not another:* nothing was tested, and the thing that broke
is the project's own configuration rather than an external input.

## 4. `timeout`

**Definition.** The job or a step was stopped because it exceeded a time limit,
rather than because it produced a failing result.

**Includes.** A runner cancelling a job at the workflow or step timeout; a test
runner aborting a case under its own deadline; a step killed after exceeding a
hard limit.

**Excludes.** A test that asserts on elapsed time and fails that assertion —
that is `test_failure`, because the runner produced a result. A job cancelled by
a person or superseded by a newer commit, which is excluded in triage.

**Observed in this cohort:** not observed in the development set.

## 5. `permission_denied`

**Definition.** An operation was refused because the identity performing it was
not authorised.

**Includes.** HTTP 401 or 403 from a registry, API or artifact store; a missing
or expired token; a filesystem permission error; a container registry refusing a
pull or push.

**Excludes.** A connection that could not be established at all, which is
`network_error`; see §10. A 404, which is usually a wrong reference rather than
an authorisation problem.

**Observed in this cohort:** not observed in the development set.

*Why this label and not another:* the request reached its destination and was
refused on identity grounds.

## 6. `syntax_error`

**Definition.** A tool could not parse a file, and reports the position where
parsing failed.

**Includes.** A compiler or interpreter parse error naming a file and line; a
malformed YAML, JSON or TOML file the build must read.

**Excludes.** A type error, which is static analysis and out of scope under §9.
A valid file whose contents are wrong for the build, which is
`build_configuration`; see §10.

**Observed in this cohort:** not observed in the development set.

*Why this label and not another:* the file could not be read as the language it
claims to be, which is prior to anything the build or test does with it.

## 7. `network_error`

**Definition.** A network operation failed for transport reasons: the endpoint
could not be reached, the connection dropped, or the transfer did not complete.

**Includes.** DNS resolution failure; connection refused, reset or timed out;
TLS negotiation failure; a truncated download.

**Excludes.** A reachable endpoint that refuses on authorisation grounds, which
is `permission_denied`. A network failure while fetching a declared dependency,
which is `dependency_error` — the label follows what was being attempted, not
the mechanism; see §10.

**Observed in this cohort:** not observed in the development set.

## 8. `unknown`

**Definition.** The log does not contain enough evidence to assign a category
with confidence.

**Use it when** the job fails with a bare non-zero exit and no diagnostic; the
relevant output was not captured; or the evidence supports two categories and
the tie-break rules in §10 do not separate them.

**Do not use it** to avoid a difficult judgement. If the evidence supports a
category, assign it and record the reasoning in the notes. `unknown` is a
statement about the log, not about the annotator's certainty.

**If a case is `unknown`,** record what was missing. A pattern of unknowns is a
finding about what CI logs make available, which is relevant to the research
question; a scatter of them is a sign the categories need revisiting.

## 9. Out of scope

These do not receive a category. They are excluded during triage and recorded
with a reason:

- lint, formatting and style failures;
- documentation and spelling jobs;
- commit-message and other administrative checks;
- dependency bots, scanners and scheduled maintenance;
- runs where no job executed.

If a case reaches annotation and belongs here, do not invent a label. Record it
and raise the triage rule.

---

## 10. Tie-break rules

The pairs that genuinely overlap. Each needs a rule, not a preference.

### `test_failure` versus `build_configuration`

**Resolved by scope, 18 October 2026.** Four django `Run Quality Checks on a PR`
cases were labelled `test_failure` while both models answered
`build_configuration`. Reading the evidence showed the job to be a script
validating pull-request metadata: no build ran and no test executed. The cases
were out of scope, and django was replaced by scrapy/scrapy. Neither category
fitted, so the disagreement was not a definitional one.

The rule is still needed for cases that genuinely sit between the two.
Question to settle: does a check script that exits non-zero without executing a
test suite constitute a test failure?

**Rule.** Ask whether a test runner produced a per-test result. If the output
names a test and reports it as failed, the label is `test_failure`. If the job
stopped before any test result was produced, the label is the category for the
stage that stopped it.

A check script that exits non-zero without executing a test suite is **neither**.
It is out of scope under §9 and should be excluded in triage, not labelled. The
django cases above are the precedent: labelling them at all was the error.

### `dependency_error` versus `network_error`

A package download that fails could be either. Question to settle: is the label
determined by what was being attempted (fetching a dependency) or by the
mechanism that failed (the network)?

**Rule.** By what was being attempted. If the operation was obtaining,
resolving or installing a declared dependency, the label is `dependency_error`
even when the proximate cause is a dropped connection. `network_error` is for
network operations that are not dependency acquisition — a test reaching an
external service, an artifact upload, a deployment step.

The reason is that the taxonomy is meant to tell a maintainer where to look. A
failed dependency fetch sends them to the dependency declaration or the mirror,
whatever the transport did.

### `dependency_error` versus `build_configuration`

A dependency declared at an incompatible version fails at build time. Question
to settle: is a wrong version a dependency problem or a configuration problem?

**Rule.** If the resolver or installer reports that it cannot satisfy the
requirement, the label is `dependency_error` — the declared set of dependencies
has no solution. If the dependency installs successfully and the build then
fails because it is wired in wrongly — a missing plugin block, a wrong path, an
unconfigured repository — the label is `build_configuration`.

The dividing line is whether installation completed.

### `syntax_error` versus `build_configuration`

A compile failure can be either malformed source or a misconfigured build.
Question to settle: which evidence distinguishes them?

**Rule.** `syntax_error` requires the tool to report a **parse failure with a
position** — a file and a line or column where the input stopped being valid.
Anything else that fails at build time is `build_configuration`: a missing
symbol, an unresolved import, a wrong target, an incompatible toolchain.

The position is what makes the distinction checkable rather than a matter of
impression.

### `permission_denied` versus `network_error`

A 403 from a registry is both an authorisation failure and a network
interaction. Question to settle: does an HTTP authorisation status mean
permission or network?

**Rule.** If the endpoint was reached and answered, it is not a network error.
An HTTP status of any kind means the connection succeeded, so 401 and 403 are
`permission_denied`. `network_error` is reserved for failures where no response
was obtained: DNS failure, connection refused or reset, TLS failure, timeout.

If the refused operation was a dependency fetch, the previous rule takes
precedence and the label is `dependency_error`.

---

## 11. Changes

Every change to this document after annotation begins is recorded here, with the
reason, and the affected cases are re-checked.

| Date | Change | Reason | Cases re-checked |
| --- | --- | --- | --- |
| 18 Oct 2026 | Created as a skeleton | Required by plan §3.5 | — |
| 21 Oct 2026 | §0 added: what counts as an evidence line | The first paired development run showed evidence-line recall measuring the annotator's marking style as much as the models. The narrow reading was chosen. | All 11 development cases; 34 lines removed as blank, worker banners or fixture reprs |
| 21 Oct 2026 | §0.2 added: evidence belongs to the job in `failing_job` | Six vite annotations had been made against a different failing matrix entry than the filter scopes to | 6 vite cases, re-annotated |
| 21 Oct 2026 | §§1-8 defined, §10 tie-breaks resolved | Required before the remaining 42 cases are annotated; drafted with AI assistance, decisions and revision by the author | None yet — written before pilot annotation begins |
