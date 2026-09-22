# Kickoff action items verified against the tool

Checked on 22 September 2026 against the working tree, by reading the code and
the stored study data rather than the documentation. Every "verified by" entry
names the command or file that produced the finding, so each row can be
re-checked independently.

Source: `Thesis_Kickoff_Meeting_Minutes_2026-09-21.docx`.

## How ground truth is produced and evaluated today

**Production.** `automated_scripts/annotate_blind.py` shows the annotator a
line-numbered copy of the log with no model output, and records a failure
category, a root-cause statement, supporting line numbers and, since this
revision, the evidence linking the label to something checkable. A second mode
(`--mode verify`) lets a different reviewer label the same case blind and
adjudicate every disagreement in writing.

**Evaluation.** Ground truth reaches the score in exactly one place:
`compute_model_metrics` in `src/evaluation/report_comparison.py` compares
`result["error_type"]` with `annotation["actual_error_type"]` for an exact
string match. `error_type_accuracy` is the fraction of matched cases, with an
inference failure counted as incorrect. `StatisticalTests` in
`src/evaluation/evaluation.py` then runs McNemar, a paired permutation test and
bootstrap confidence intervals over that same correct/incorrect vector.

**What that means.** A single categorical exact match carries every accuracy
claim in the study. Two other annotated fields now feed the reporting layer as
well:

- `failure_lines` is scored by `src/evaluation/category_metrics.py`
  (evidence-line precision, recall, F1 and Jaccard). Before this revision the
  field was loaded into `PredictionResult.actual_lines` and never read by any
  metric.
- `actual_root_cause` is still **not** scored. Comparing a free-text cause needs
  the expert rubric the roadmap defers to the approved protocol.

**Grounding is not correctness.** `GroundingVerifier.verify_evidence` checks
that each line a model cited exists in the *filtered log the model was given*,
with a 0.75 fuzzy-match fallback. It never consults ground truth. A model can
score 100% grounding while citing entirely the wrong lines, which is what the
pilot shows: 97.5% grounding against roughly 6% evidence-line F1. Report the two
separately and never describe grounding as accuracy.

## Decisions

| ID | Decision | Tool position | Verified by |
|---|---|---|---|
| D1 | Move to evaluation design; ground truth is the missing piece | Correct: collection, triage and benchmarking are complete; ground truth was the gap | Working tree |
| D2 | Start with two contrasting repositories | **Not aligned.** `configs/thesis_fresh_2026.yaml` lists six repositories across three ecosystems; the collected cohort holds 74 eligible cases from all six | `configs/thesis_fresh_2026.yaml`, `data/studies/thesis_fresh_2026/triaged/eligible_logs.json` |
| D3 | Prefer historical fixes or seeded defects; independent review; LLM-as-judge is a last resort | **Now enforced.** Annotation records an evidence method and reference, a second reviewer can verify blind, and `make audit-ground-truth` refuses to call unlinked single-annotator ground truth defensible. No LLM-as-judge path exists anywhere in the code | `src/evaluation/ground_truth_audit.py`, `automated_scripts/annotate_blind.py` |
| D4 | Separate development from final data; freeze and evaluate once | **Was violated, now blocked.** All five smoke cases are members of the 74-case cohort `make final` reads. The benchmark now refuses such a run unless `--allow-excluded-cases` is given with a written justification | `src/evaluation/case_partitions.py`, `tests/test_methodology_guards.py` |
| D5 | Category-level results showing where the LLM is strong or weak | **Now available.** Per-category precision, recall, F1 and support, macro F1, and a confusion matrix per condition | `src/evaluation/category_metrics.py`, comparison page |
| D6 | Ground the setup in literature before the main evaluation | Outside the tool. No evidence matrix exists in the repository | — |
| D7 | Shortened working title | Documentation only | `docs/THESIS_EXECUTION_ROADMAP_2026-09-21.md` |
| D8 | Next review in about two weeks with a methodology proposal | Outside the tool | — |

## Action items

| ID | Owner | Action | Status against the tool |
|---|---|---|---|
| A1 | Fahid | Review comparable research | **Not started in-repo.** No evidence matrix or bibliography exists |
| A2 | Fahid | Written evaluation plan | **Partly drafted.** The roadmap specifies ground truth, partitions, metrics and freeze criteria but has not been through the approval gate |
| A3 | Fahid | Select two contrasting repositories | **Open.** Still six repositories; no written justification of a pair |
| A4 | Fahid | Investigate historical failing/fixed revisions | **Tool ready, data absent.** `evidence_method: historical_fix` with a `fixing_reference` can now be recorded, and the audit blocks a case that claims one without the reference. No case records one yet |
| A5 | Fahid | Design seeded defects; reserve an unseen set | **Partly ready.** `evidence_method: seeded_defect` with a `seed_reference` is supported and audited. The reservation half is enforced by the partition guard; no seeding tooling exists |
| A6 | Fahid | Define system version and freeze criteria | **Partial.** `run_metadata.json` records git commit, prompt hash, schema, model identity, Ollama digest and input checksums. Nothing refuses to run from a dirty worktree, and there is no freeze manifest |
| A7 | Fahid | Share papers with Mahade | Outside the tool |
| A8 | Fahid | Seminar material | Outside the tool |
| A9 | Mahade | Review papers and design | Outside the tool |
| A10 | Jussi | Forward examiner paperwork | Outside the tool |
| A11 | Fahid and Jussi | Confirm seminar start time | Outside the tool |

## Findings in the stored study data

1. **The recorded root causes are unusable.** All five annotations in
   `data/studies/system_smoke_001/ground_truth/ground_truth.json` hold a single
   digit (`"6"`, `"1"`, `"8"`, `"3"`, `"7"`) instead of a statement. The old
   prompt accepted any non-empty string, so the error-type menu index was
   entered one prompt too late. `prompt_root_cause` now rejects bare numbers,
   category names and anything under 25 characters. **These five cases need
   re-annotation.**
2. **The smoke cohort leaks into the final cohort.** All five smoke case ids are
   present in the 74-case eligible cohort, and `smoke_manifest.json` already
   declared `exclude_from_future_held_out_evaluation: true` with nothing
   enforcing it.
3. **`statistical_tests.json` was truncated at 223 bytes**, cut off inside
   `"significant_at_005":`. `json.dump` hit a NumPy `bool_` and raised
   mid-write, which also aborted the final report write and the trade-off chart.
   The `float()`/`bool()` normalisation in `src/evaluation/evaluation.py` fixes
   the cause; re-running the pilot regenerated all three files.

## What is still open in the tool

These need the supervisors' approved protocol before implementation, because
each one locks a methodological choice:

- a two-repository study configuration with a new study id (D2, A3);
- a versioned development / pilot / final split manifest with a fixed seed,
  partitioned by underlying defect rather than by run id (D4);
- a freeze manifest that refuses a final run from a dirty or mismatched
  worktree (A6);
- an expert rubric for root-cause correctness and fix usefulness, with an
  inter-rater procedure, so `actual_root_cause` can be scored;
- a decision on whether the rule-based baseline named in the status update is in
  scope, since no baseline exists in the current workflow.
