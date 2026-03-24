# Findings: Pipeline Scaling and Context Enrichment — March 2026

**Author:** Fahid Khan
**Date:** 11 March 2026
**Thesis:** LLM-Based CI/CD Failure Diagnosis — Tampere University

---

## 1. Summary

This document reports findings from the second iteration of system development and evaluation. Three changes were made to the diagnostic pipeline: (1) the LLM prompt was enriched with CI/CD run metadata, (2) the data collection was scaled from 2 to 9 repositories, and (3) several reliability issues in the evaluation tooling were identified and fixed. The primary finding is that the system generalises well to a broader, more diverse set of CI/CD failure logs, diagnosing 52 of 55 triaged logs across 7 distinct error types.

---

## 2. Finding 1: Context-Enriched Prompts

### Observation

The diagnostic prompt previously sent only the filtered log content to the LLM with no metadata about *where* the log came from. This meant the model had to infer the programming language, build system, and project structure entirely from the log text — increasing the risk of misinterpretation and hallucination.

### Change

The prompt now includes a `CONTEXT:` block containing the repository name, workflow name, CI system, and run URL. This metadata was already available from data collection but was not being passed through to the LLM.

Example prompt header:
```
CONTEXT:
- Repository: pytorch/pytorch
- Workflow: Upload test stats
- CI System: GitHub Actions
- Run URL: https://github.com/pytorch/pytorch/actions/runs/12345
```

### Implication

This is a low-cost improvement (no additional API calls, no extra data collection) that directly provides the LLM with domain context. The impact on diagnostic accuracy will be measured once the scaled dataset is fully annotated. This change also introduces a new experimental variable: future ablation studies can compare diagnosis quality with and without context metadata.

---

## 3. Finding 2: Dataset Scaling

### Before

| Metric | Value |
|---|---|
| Repositories | 2 (pytorch, tensorflow) |
| Raw logs | 20 |
| Triaged logs | 12 |
| Diagnosed logs | 12 |
| Error types observed | 3 (test_failure, dependency_error, syntax_error) |

### After

| Metric | Value |
|---|---|
| Repositories | 9 (tensorflow, pytorch, scikit-learn, flask, django, react, next.js, vue, angular) |
| Raw logs | 68 |
| Triaged logs | 55 |
| Diagnosed logs | 52 |
| Failed diagnoses | 3 (API timeouts on exceptionally large logs) |
| Error types observed | 7 (test_failure, dependency_error, build_configuration, unknown, network_error, permission_denied, syntax_error) |

### Observations

1. **Completion rate remained high (94.5%)** despite the scale increase. The 3 failures were caused by API timeouts on extremely large Angular pull request logs, not by diagnostic logic failures.

2. **Error type distribution shifted significantly.** In the original 12-log set, 83.3% were `test_failure`. In the 52-log set, `test_failure` dropped to 55.8%, with `dependency_error` (15.4%), `build_configuration` (11.5%), and `unknown` (9.6%) representing meaningful shares. This confirms that the original dataset was too homogeneous of test.

3. **Average confidence remained stable** at 75.8% (vs. 76.0% for the original 12), suggesting the model's self-calibration is consistent across different repository types.

4. **New error types appeared** that were absent from the original set: `build_configuration`, `network_error`, and `permission_denied`. These represent CI/CD failure modes beyond code-level errors and will test whether the system handles infrastructure-level issues.

### Triage effectiveness

The triage step removed 13 of 68 logs (19%):

| Removal Reason | Count |
|---|---|
| Duplicate error signatures | 7 |
| Token / auth errors | 4 |
| Cancelled runs | 2 |

The lower removal rate (19% vs. 40% in the original batch) is expected: the original dataset was heavily biased toward pytorch's "Upload test stats" workflow, which produced many near-identical logs. The more diverse repository set naturally produces fewer duplicates.

---

## 4. Finding 3: Evaluation Data Integrity

### Problem Discovered

When running the full pipeline end-to-end, re-collecting data **overwrote** the original `batch1.json` with new log entries. Because GitHub Actions run IDs change daily, the new file contained entirely different log IDs from the ground truth annotations. The evaluation script then silently computed 0% accuracy for both baselines — a misleading result that could have been mistaken for a regression.

### Root Cause

The data collection script always writes to `batch1.json` without checking for existing data. The raw log files are gitignored, so no backup existed in version control.

### Fixes Applied

1. **Pre-collection backup:** The data collection script now copies existing `batch1.json` to a timestamped backup (e.g., `batch1_backup_20260311_125800.json`) before overwriting.

2. **Multi-source content lookup:** The evaluation script now searches both the raw and triaged log files when looking up log content for baseline comparison. If IDs still don't match, it prints a clear warning with the count and sample of missing IDs, rather than silently reporting 0%.

### Implication

Ground truth annotations are tightly coupled to specific log IDs. Any re-collection requires re-annotation. This is an inherent tradeoff in working with live CI/CD data from GitHub — the same workflow produces different run IDs over time.

---

## 5. Design Decision: Rule-Based Triage

A question raised during supervisor discussion was whether the LLM itself should classify runs as "good" (diagnosable failure) vs. "bad" (cancelled, token error, duplicate). The current system uses deterministic regex rules for this step.

**Rationale for keeping rule-based triage:**
- **Speed:** Regex triage processes 68 logs in under 1 second. LLM classification would cost ~$0.15 and take ~15 minutes.
- **Determinism:** The same input always produces the same triage result, aiding reproducibility.
- **Auditability:** Each removal has a clear, inspectable reason (cancelled_run, token_error, duplicate_error, too_short).
- **Scope control:** The research contribution is LLM-based *diagnosis*, not LLM-based *run classification*. Adding LLM-based triage would require its own evaluation framework.

This is documented as a deliberate design choice, not a gap.

---

## 6. DSR Iteration History

The system has gone through four measurable design iterations:

| Iteration | Problem Observed | Change Made | Outcome |
|---|---|---|---|
| 1 | Raw logs too noisy for LLM context window | Added keyword-based log filtering with context windows | Reduced input to ~500 relevant lines with `[Line N]` markers |
| 2 | LLM cited non-existent line numbers | Added grounding verification against filtered log | Hallucinated references detected and flagged automatically |
| 3 | Free-text output not quantitatively evaluable | Added structured JSON schema with predefined error types | Enabled multi-dimensional accuracy metrics |
| 4 | LLM had no project context, diagnosed in isolation | Added context-enriched prompts with CI/CD metadata | Pending measurement on scaled dataset |

Each iteration follows the DSR build→evaluate→refine pattern. Iterations 1–3 were evaluated on the initial 12-log dataset. Iteration 4 will be evaluated on the scaled 52-log dataset after re-annotation.

---

## 7. Current Status and Next Steps

| Status | Detail |
|---|---|
| Data collected | 68 raw logs from 9 repositories |
| Triaged | 55 logs (13 removed) |
| Diagnosed | 52 logs (3 API timeouts) |
| Ground truth | Pending — old 12-log annotations orphaned by re-collection |
| Evaluation | Blocked on re-annotation |

**Next steps:**
1. Annotate all 52 diagnosed logs to build ground truth for the scaled dataset
2. Re-run evaluation to get updated accuracy, baseline comparison, and per-error-type breakdown
3. Compare results against the initial 12-log demonstration to assess whether accuracy holds at scale
4. Begin thesis Chapter 2 (Background & Related Work) in parallel
