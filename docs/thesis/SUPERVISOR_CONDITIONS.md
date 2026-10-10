# Supervisor conditions and response

Record of supervisor feedback on the evaluation plan, what each point settles,
and what it requires. New feedback is appended rather than overwritten.

**Status:** conditionally approved by Md Mahade Hasan on 6 October 2026.
His reply is explicitly supervisory input, not final approval — Dr Jussi Rasku
must review before the next steps proceed.

---

## 1. What is now settled

| Ref | Point | Decision |
| --- | --- | --- |
| Q1 | Dataset size and split | 120 collected, 80 usable, split 15 / 15 / 50 approved. **120 is a target, not a strict requirement**; the final count follows the eligibility criteria. |
| Q2 | Gradle checked first | Approved. Replacement permitted if the GitHub Actions history lacks eligible, diverse build or test failures. |
| Q4 | Keyword-and-pattern baseline | **In scope.** Keep it limited, freeze it before the held-out run, and never expand it after seeing held-out results. |
| Q5 | Controlled defects | Approved: at most two per rare category, sixteen overall, supplementing natural cases rather than replacing them. |
| Q6 | Root-cause rubric | 0 / 1 / 2 approved, with the supervisor's wording (§3 below). |
| Q7 | Freeze approval | Prepared by the author, annotation and dataset documentation checked by the second reviewer, approved by **both** supervisors, recorded as a version tag, commit or signed checklist. |
| Q8 | 9 November seminar | **Verified pilot findings are sufficient.** The full held-out evaluation is not required for the seminar. |

Two open decisions from the plan are therefore closed: the baseline is in scope
(Q4), and both supervisors approve the freeze (Q7).

## 2. New requirements to fold into the plan

| # | From | Requirement | In the plan? |
| --- | --- | --- | --- |
| R1 | Q1 | Report the final case distribution by repository **and** by failure category | No — add to §5 |
| R2 | Q2 | The final report must explain why Gradle was retained or replaced | No — add to §3.1 |
| R3 | Q3 | Document the reviewer **selection procedure** | No |
| R4 | Q3 | Give the reviewer the rubric, annotation instructions and **calibration examples** before independent work begins | No |
| R5 | Q3 | Preserve the original independent labels even after a consensus label is created | Implemented, §4 below |
| R6 | Q3 | Re-check the 35–50 hour estimate after the pilot and report the actual figure if it differs materially | Partly — §8 gives the estimate, not the re-check |
| R7 | Q5 | Controlled-defect records must capture defect type, injection procedure, intended root cause, affected component and reproducibility | No |
| R8 | Q6 | Evidence lines must be checked for whether they **genuinely support** the diagnosis, not only whether they overlap the annotated set | No — this is a judgement step beyond precision, recall, F1 and Jaccard |
| R9 | Q6 | Report raw **and** chance-corrected agreement; specify the exact evidence-line matching rule before evaluation | Partly — kappa is named, the matching rule is not yet fixed |
| R10 | Q7 | Extend the freeze package to include system instructions, decoding parameters, output format, baseline implementation and analysis procedure | Partly — §6 is narrower |
| R11 | Q8 | Label pilot results as preliminary and begin the held-out evaluation only after the freeze | Add to §6 |

## 3. Rubric wording to adopt

The supervisor's definitions replace the earlier wording:

| Score | Definition |
| --- | --- |
| 0 | The predicted root cause is incorrect. |
| 1 | The prediction is partially correct but incomplete, too general, or insufficiently supported. |
| 2 | The root cause is correct and supported by relevant evidence from the logs or other available artefacts. |

## 4. Tooling: done and outstanding

**Done (6 October 2026).** Adjudication previously overwrote the first
reviewer's label with the consensus value, which destroyed one of the two
independent label sets. Cohen's kappa cannot be computed from a label that no
longer exists, so R5 and R9 were coupled. Both independent sets are now
snapshotted before adjudication (`annotator_*` and `verifier_*`, with `actual_*`
holding the consensus), covered by a test. 76 offline tests pass.

**Outstanding, in dependency order:**

1. Cohen's kappa for categories and weighted kappa for the ordinal scores (R9).
2. The root-cause scoring form implementing the §3 rubric, with de-identified,
   randomly ordered responses.
3. Preprocessing recall: how many verified evidence lines survive filtering.
4. The evidence-support check (R8), which the current overlap metrics do not cover.
5. Triage exclusion of lint-only, documentation-only and administrative jobs.
6. The fixed development / pilot / held-out split manifest, grouped so that
   related repairs and repeated signatures stay in one partition.
7. The keyword-and-pattern baseline (Q4), written against development cases only
   and frozen.
8. Controlled-defect record fields (R7).
9. The freeze package and its checklist (R10).

## 5. Open proposal for Dr Rasku: gate criterion 4

The repository gate was run on 28 September against the criteria as written in
the plan. Measured results, reported unamended:

| Repository | Logs | In scope | Repair-linked | Top workflow | Top failing job | Distinct jobs |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| gradle/gradle | 30/30 | 26/30 | 14/30 | 25/30 | 12/30 | 12 |
| sveltejs/svelte | 30/30 | 17/30 | 20/30 | 30/30 | 13/30 | 5 |
| django/django | 30/30 | 9/30 | 22/30 | 8/30 | 7/30 | 8 |
| eslint/eslint | 30/30 | 6/30 | 18/30 | 16/30 | 9/30 | 9 |
| pallets/flask | no eligible runs — all listed failures older than the log-retention window | | | | | |

Against the criteria as written, **every candidate fails**. Django and ESLint
fail criterion 2 structurally: most of their Actions failures are lint,
documentation or commit-message jobs. Gradle and Svelte fail criterion 4.

**The proposal.** Criterion 4 reads "the cases are not dominated by one repeated
error or workflow". Measured at workflow level it rejects any project that uses
a single umbrella workflow, regardless of how varied its failures are. Gradle's
25/30 sits in `Contributor CI Build`, which contains twelve distinct failing
jobs (`Sanity Check on Linux` 12, `Compile All` 5, `Unit Test Windows ARM`, and
others). Svelte's 30/30 sits in one workflow named `CI`, containing `Lint`,
`Tests (20, windows-latest)`, `TSGo` and two more. In both cases the criterion is
measuring CI structure rather than failure diversity.

The proposal is to measure criterion 4 at the **failing job** level. Gradle would
then read 12/30 and Svelte 13/30, both within a "no more than half" rule.

This amendment was identified **after** the gate was run, so it is recorded here
as an explicit request rather than applied. Q2 requires the eligibility criteria
to be fixed before the replacement decision, so no repository will be retained or
replaced on the amended criterion until Dr Rasku has approved it. Both the
as-written and amended measurements will be reported in the thesis either way.

**If approved:** `gradle/gradle` and `sveltejs/svelte` become the pair. Gradle
contributes the build and test failures the study is about (26/30 in scope);
Svelte contributes the strongest repair traceability among repositories that also
produce real build and test failures (20/30). Gradle's criterion 3 reading of
14/30 remains one case below its threshold and is reported as measured.

**If not approved:** both repositories are replaced and the gate re-run on new
candidates under the unamended criteria.

## 6. Revised schedule

Q8 removes the held-out evaluation from the pre-seminar critical path.

| Dates | Work |
| --- | --- |
| 6–11 October | Jussi's review; criterion 4 resolved; tooling items 1–5; begin collection |
| 12–18 October | Finish collection and triage; codebook; split manifest; baseline; reviewer calibration |
| 19–25 October | Independent annotation of development and pilot cases |
| 26 October–2 November | Run the 15-case pilot; blind-score it; record actual review time against the 35–50 hour estimate |
| 3–9 November | Seminar material, with pilot results labelled preliminary |
| After 9 November | Freeze package, both-supervisor approval, then the one-time held-out evaluation |

## 7. Next action

Send the revised plan to Dr Rasku with a short note stating that Mahade has
reviewed it, listing the changes made in response, and asking specifically for a
decision on the criterion 4 proposal in §5, since the repository pair cannot be
fixed without it.
