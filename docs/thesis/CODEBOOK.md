# Failure category codebook

The written rules for assigning a failure category. Two reviewers following this
document should reach the same label; where they do not, the disagreement is in
the rules rather than in anyone's judgement, and the rules get fixed.

**Status: skeleton. The definitions are not written yet.** Every `TO WRITE`
below is a methodological decision for the author. The structure, the tie-break
pairs and the candidate examples are prepared; the content is not.

Required by the evaluation plan §3.5, and by Mahade's Q3, which requires a
second reviewer to receive this document plus calibration examples before
beginning independent assessment.

**Version:** draft, 18 October 2026 · **Frozen:** no

---

## How to use this

1. Read the log and identify what actually failed.
2. Work down the categories in the order below. The first one whose definition
   is satisfied is the label.
3. If two seem to apply, consult the tie-break rules in §10.
4. If none apply, the label is `unknown` — see §8 before using it.
5. Record the lines that support the decision.

The order matters: it encodes precedence, so a dependency failure inside a build
step is a dependency failure rather than a build failure.

---

## 1. `dependency_error`

**Definition.** TO WRITE

**Includes.** TO WRITE

**Excludes.** TO WRITE

**Worked example.** `gh_gradle_gradle_37528456960` — gradle/gradle, `Compile All`
*Why this label and not another:* TO WRITE

## 2. `test_failure`

**Definition.** TO WRITE

**Includes.** TO WRITE

**Excludes.** TO WRITE — note that this is the most heavily used category in the
development set (9 of 16 cases) and therefore the one whose boundaries matter
most.

**Worked examples.**
- `gh_gradle_gradle_38262124569` — gradle/gradle, `Sanity Check on Linux`
- `gh_django_django_38132965162` — django/django, `Run Quality Checks on a PR`

*Why this label and not another:* TO WRITE

## 3. `build_configuration`

**Definition.** TO WRITE

**Includes.** TO WRITE

**Excludes.** TO WRITE

**Worked example.** `gh_django_django_38291208286` — django/django,
`Run Quality Checks on a PR`
*Why this label and not another:* TO WRITE

## 4. `timeout`

**Definition.** TO WRITE

**Includes.** TO WRITE

**Excludes.** TO WRITE

**Worked example.** None in the development set. A controlled defect may be
required to establish the boundary.

## 5. `permission_denied`

**Definition.** TO WRITE

**Includes.** TO WRITE

**Excludes.** TO WRITE

**Worked examples.**
- `gh_gradle_gradle_38202525149` — gradle/gradle, `update-perf-test-buckets`
- `gh_gradle_gradle_37257596630` — gradle/gradle, `update-test-buckets`

*Why this label and not another:* TO WRITE

## 6. `syntax_error`

**Definition.** TO WRITE

**Includes.** TO WRITE

**Excludes.** TO WRITE

**Worked example.** `gh_gradle_gradle_37630755438` — gradle/gradle, `Compile All`
*Why this label and not another:* TO WRITE

## 7. `network_error`

**Definition.** TO WRITE

**Includes.** TO WRITE

**Excludes.** TO WRITE

**Worked example.** `gh_gradle_gradle_37521515041` — gradle/gradle,
`generate-and-submit`
*Why this label and not another:* TO WRITE

## 8. `unknown`

**Definition.** TO WRITE

This category needs a stricter rule than the others, because it is the one a
reviewer reaches for when tired. State explicitly what must be true before a
case is labelled `unknown` rather than merely difficult. Candidates to consider:

- the log does not contain the failure at all;
- the failure is reported but its nature cannot be determined from the log;
- more than one cause is equally supported and none predominates.

Note the asymmetry with the models: a model answering `unknown` may be correctly
reporting that its filtered input lacked the evidence. Preprocessing recall
distinguishes those cases; a reviewer working from the full log has no such
excuse.

---

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

**Rule.** TO WRITE

### `dependency_error` versus `network_error`

A package download that fails could be either. Question to settle: is the label
determined by what was being attempted (fetching a dependency) or by the
mechanism that failed (the network)?

**Rule.** TO WRITE

### `dependency_error` versus `build_configuration`

A dependency declared at an incompatible version fails at build time. Question
to settle: is a wrong version a dependency problem or a configuration problem?

**Rule.** TO WRITE

### `syntax_error` versus `build_configuration`

A compile failure can be either malformed source or a misconfigured build.
Question to settle: which evidence distinguishes them?

**Rule.** TO WRITE

### `permission_denied` versus `network_error`

A 403 from a registry is both an authorisation failure and a network
interaction. Question to settle: does an HTTP authorisation status mean
permission or network?

**Rule.** TO WRITE

---

## 11. Changes

Every change to this document after annotation begins is recorded here, with the
reason, and the affected cases are re-checked.

| Date | Change | Reason | Cases re-checked |
| --- | --- | --- | --- |
| 18 Oct 2026 | Created as a skeleton | Required by plan §3.5 | — |
