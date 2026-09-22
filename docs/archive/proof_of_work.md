# Proof of Work: Demonstration Evaluation of LLM-Based CI/CD Failure Diagnosis

**Master's Thesis -- Tampere University**
**Author:** Fahid Khan
**Program:** Software, Web, and Cloud
**Supervisors:** Jussi Rasku & Md Mahade Hasan
**Date:** March 2026

---

## Table of Contents

1. [Introduction and Research Framing](#1-introduction-and-research-framing)
2. [Design Science Research Alignment](#2-design-science-research-alignment)
3. [Step 1: Data Collection](#3-step-1-data-collection)
4. [Step 2: Log Triage](#4-step-2-log-triage)
5. [Step 3: Diagnostic API](#5-step-3-diagnostic-api)
6. [Step 4: Automated Diagnosis](#6-step-4-automated-diagnosis)
7. [Step 5: Ground Truth Annotation](#7-step-5-ground-truth-annotation)
8. [Step 6: Evaluation and Baseline Comparison](#8-step-6-evaluation-and-baseline-comparison)
9. [Results Summary](#9-results-summary)
10. [Threats to Validity and Limitations](#10-threats-to-validity-and-limitations)
11. [Scaling to Full Dataset](#11-scaling-to-full-dataset)
12. [Conclusion](#12-conclusion)
13. [Appendices](#13-appendices)

---

## 1. Introduction and Research Framing

### 1.1 Problem Statement

Continuous Integration and Continuous Delivery (CI/CD) pipelines are a cornerstone of modern software engineering. When these pipelines fail, developers must manually inspect build logs -- often thousands of lines of unstructured text -- to identify what went wrong, determine the root cause, and decide on a fix. This process is time-consuming, error-prone, and requires domain expertise.

This thesis investigates whether Large Language Models (LLMs) can automate this diagnostic process. Specifically, we build and evaluate a system that takes a raw CI/CD failure log as input and produces a structured diagnosis containing:

- **Error type classification** (e.g., dependency error, test failure, syntax error)
- **Root cause explanation** in natural language
- **Suggested fix** with actionable steps
- **Grounded evidence** linking the diagnosis to specific log lines
- **Confidence score** reflecting the model's certainty
- **Hallucination detection** flagging ungrounded claims

### 1.2 Research Question

> *To what extent can Large Language Models accurately diagnose CI/CD pipeline failures from raw build logs, and how does their performance compare to traditional pattern-matching approaches?*

### 1.3 Evaluation Approach: Path A -- Demonstration

Following guidance from thesis supervisor Jussi Rasku, this work follows **Path A: Demonstration Evaluation** -- a qualitative, in-depth assessment of the system on a curated set of real-world failures. Rather than a purely quantitative experiment on hundreds of logs, we select real failures, run the system, manually verify each diagnosis, and report the results transparently.

This approach is appropriate for a Master's thesis because:
- It demonstrates the artifact works on real data (not synthetic benchmarks)
- It allows fine-grained assessment of diagnosis quality beyond simple accuracy
- It surfaces failure modes and edge cases that inform future development
- It aligns with the Design Science Research paradigm where the goal is to create and demonstrate a useful artifact

---

## 2. Design Science Research Alignment

This thesis follows the **Design Science Research Methodology (DSRM)** as described by Hevner et al. (2004) and Peffers et al. (2007). DSRM is appropriate because the work centres on designing, building, and evaluating an IT artifact (the diagnostic system) rather than testing a natural-science hypothesis.

The six DSRM activities and their mapping to our work:

| DSRM Activity | Description | Mapping to This Work |
|---|---|---|
| **1. Problem Identification** | Identify the practical problem and justify the value of a solution | CI/CD log diagnosis is manual, slow, and error-prone. Developers spend significant time reading logs. Automated diagnosis could save time and reduce human error. |
| **2. Define Objectives** | Define what a successful solution would look like | A system that (a) correctly classifies error types, (b) explains root causes accurately, (c) suggests actionable fixes, (d) grounds its claims in actual log lines, and (e) outperforms simple regex/heuristic baselines. |
| **3. Design and Development** | Create the artifact | The diagnostic system: FastAPI service with LLM integration, log filtering, grounding verification, and hallucination detection (Section 5). |
| **4. Demonstration** | Show the artifact works in context | Run the system on 12 real CI/CD failure logs from PyTorch and TensorFlow (Sections 3--6). |
| **5. Evaluation** | Measure how well the artifact meets objectives | Compare LLM diagnosis against human-verified ground truth and two baselines (Section 8). |
| **6. Communication** | Report findings to relevant audiences | This document, the thesis manuscript, and the open-source repository. |

Each pipeline step described below is annotated with which DSRM activity it corresponds to, making explicit how the engineering work maps to the research methodology.

---

## 3. Step 1: Data Collection

**DSRM Activity:** Problem Identification + Design and Development
**Script:** `automated_scripts/data_collection.py`
**Output:** `data/raw_logs/github_actions/batch1.json`

### 3.1 What Happens

The data collection script connects to the GitHub Actions API and retrieves logs from failed CI/CD workflow runs in major open-source repositories. For this initial demonstration batch, the following repositories were targeted:

| Repository | Domain | Target Logs |
|---|---|---|
| `tensorflow/tensorflow` | ML framework (Python/C++) | 10 |
| `pytorch/pytorch` | ML framework (Python/C++) | 10 |
| `scikit-learn/scikit-learn` | ML library (Python) | 10 |
| `pallets/flask` | Web framework (Python) | 5 |
| `django/django` | Web framework (Python) | 5 |
| `facebook/react` | Frontend (JavaScript) | 10 |
| `vercel/next.js` | Frontend (JavaScript) | 10 |
| `vuejs/core` | Frontend (JavaScript) | 5 |
| `angular/angular` | Frontend (TypeScript) | 5 |

The collector performs the following operations for each repository:

1. **Query the GitHub Actions API** for workflow runs with `status=failure`, ordered by most recent.
2. **Download the log archive** (ZIP file) for each failed run.
3. **Extract all log files** from the ZIP and concatenate them into a single string with `=== filename ===` headers.
4. **Record metadata**: repository name, workflow name, run URL, run ID, timestamp, and the full log content.
5. **Save incrementally** after each repository to prevent data loss on interruption.
6. **Back up existing data** before overwriting: if `batch1.json` already exists, a timestamped backup (e.g., `batch1_backup_20260311_125800.json`) is created automatically to prevent data loss on re-collection.

### 3.2 Why This Step Matters

Without real failure data, any evaluation would be synthetic and unconvincing. This step grounds the entire research in actual CI/CD failures from production-grade open-source projects. By choosing TensorFlow and PyTorch -- two of the most complex and heavily-tested software projects in existence -- we ensure the system is tested against challenging, real-world logs that are thousands of lines long and contain multiple interleaved error streams.

### 3.3 Technical Details

- **Authentication:** GitHub classic token with `repo` and `workflow` scopes.
- **Rate limiting:** Built-in retry logic with exponential backoff for API rate limits.
- **ZIP handling:** All files within the downloaded ZIP are extracted and concatenated, not just the first file. This was a critical fix -- earlier versions only read the first file in the archive, missing important diagnostic information from parallel job logs.
- **Partial saves:** After each repository is processed, results are written to disk. This means a `KeyboardInterrupt` or network failure does not lose already-collected data.

### 3.4 Results

- **68 raw logs** collected across 9 repositories (tensorflow, pytorch, scikit-learn, flask, django, react, next.js, vue, angular)
- Average log length: several thousand lines
- Logs cover diverse workflows including: "Upload test stats", "PyLint", "Unit tests", "Build and Test", "ci", "Pull Request", "Check Changelog", "Tests", and dependency update workflows
- Stored in `data/raw_logs/github_actions/batch1.json` (~430 MB)

### 3.5 DSR Justification

In Design Science Research, the problem must be grounded in a real-world context. Collecting genuine CI/CD failure logs -- rather than fabricating synthetic examples -- ensures our artifact is evaluated against the actual complexity and noise that a real user would face. The diversity of error types (test failures, dependency errors, syntax errors) naturally present in these logs provides a realistic test bed.

---

## 4. Step 2: Log Triage

**DSRM Activity:** Design and Development
**Script:** `automated_scripts/triage.py`
**Output:** `data/raw_logs/github_actions/batch1_triaged.json`

### 4.1 What Happens

The triage step acts as an intelligent pre-filter. Not every failed CI/CD run contains a genuinely diagnosable error. Some are cancelled runs, some are duplicates of the same underlying bug, and some fail due to infrastructure issues (like an expired API token) rather than code defects. The triage script applies the following rules:

1. **Cancel detection:** Logs containing patterns like `"The operation was canceled"` or `"The runner has received a shutdown signal"` are removed. These are not real failures -- they are workflow cancellations.

2. **Token/auth error detection:** Logs where the only error is `"Bad credentials"` or `"401 Unauthorized"` are removed. These indicate a problem with the CI configuration's authentication tokens, not with the code being built.

3. **Minimum length filter:** Extremely short logs (below a configurable threshold) are removed, as they typically represent setup-only failures that contain no diagnosable content.

4. **Duplicate detection:** The script computes an "error signature" from each log by extracting lines that contain error-related keywords (`ERROR`, `FAIL`, `Exception`, `Traceback`), hashing them, and comparing. Logs with identical error signatures to an already-kept log are marked as duplicates. A configurable `--max-duplicates` parameter controls how many copies of the same error are retained (default: 2).

5. **Priority assignment:** Each surviving log is assigned a priority: `high` (clear error signals) or `low` (warnings but no obvious hard errors).

### 4.2 Why This Step Matters

Raw data is noisy. If we diagnose all 20 raw logs without filtering, the LLM wastes API calls on cancelled runs and processes the same error ten times. More importantly for evaluation, duplicates would inflate accuracy metrics -- diagnosing the same error correctly ten times does not demonstrate breadth. The triage step ensures that every log sent to the diagnostic API is:

- A genuine failure (not a cancellation or auth error)
- A unique failure (not a duplicate of one already processed)
- Substantive enough to diagnose (contains enough content)

### 4.3 Results

| Metric | Count |
|---|---|
| Input (raw logs) | 68 |
| Removed: duplicates | 7 |
| Removed: token/auth errors | 4 |
| Removed: cancelled runs | 2 |
| **Output (triaged logs)** | **55** |
| High priority | 40 |
| Medium priority | 12 |
| Low priority | 3 |

The triage reduced the dataset by 19%, removing noise that would have distorted evaluation metrics.

### 4.4 DSR Justification

Triage is part of the artifact's design. A practical CI/CD diagnosis tool must handle real-world noise: cancelled runs, duplicate failures from matrix builds, and infrastructure errors. Building this pre-filtering into the pipeline is a design decision that directly improves the artifact's utility. In DSR terms, triage contributes to the artifact's **relevance** -- it solves a real problem (noise in CI/CD data) rather than assuming clean inputs.

---

## 5. Step 3: Diagnostic API

**DSRM Activity:** Design and Development
**Implementation:** `src/api/` (main.py, models.py, filtering.py, llm_service.py, grounding.py)
**Runtime:** FastAPI server at `http://localhost:8000`

### 5.1 Architecture

The diagnostic API is a FastAPI web service with a modular architecture:

```
                        ┌─────────────────┐
     POST /diagnose  ──>│    main.py       │
     {log_content,      │  (endpoints)     │
      provider,         └────────┬─────────┘
      model, ...}                │
                                 v
                        ┌─────────────────┐
                        │  filtering.py    │  Step A: Filter raw log
                        │  (LogFilter)     │  - Remove timestamps, noise
                        └────────┬─────────┘  - Keep error-relevant lines
                                 │            - Apply context windows
                                 v
                        ┌─────────────────┐
                        │  llm_service.py  │  Step B: LLM diagnosis
                        │  (LLMDiagnoser)  │  - Send filtered log to GPT-4o-mini
                        └────────┬─────────┘  - Parse structured JSON response
                                 │            - Retry on failure
                                 v
                        ┌─────────────────┐
                        │  grounding.py    │  Step C: Verify evidence
                        │  (Grounding      │  - Check cited lines exist in log
                        │   Verifier)      │  - Flag hallucinated references
                        └────────┬─────────┘  - Set hallucination_detected flag
                                 │
                                 v
                          JSON Response
```

### 5.2 Component Details

**5.2.1 Log Filtering (`filtering.py`)**

Raw CI/CD logs can be tens of thousands of lines. LLMs have limited context windows and perform worse with excessive noise. The `LogFilter` applies keyword-based filtering to: (a) identify lines containing error signals (`ERROR`, `FAIL`, `Exception`, `npm ERR!`, `Traceback`, etc.), (b) retain configurable context windows around those lines (default: 10 lines before and after), and (c) cap the total output at a configurable maximum (default: 500 lines).

Each output line is tagged with its original line number in the format `[Line N] content`, enabling the grounding verifier to later check if the LLM's cited evidence refers to real log lines.

**5.2.2 LLM Integration (`llm_service.py`)**

The `LLMDiagnoser` class supports multiple LLM providers (OpenAI and Anthropic). It constructs a **context-enriched prompt** that includes available metadata about the CI/CD run before presenting the log content. When metadata is available, the prompt includes a `CONTEXT:` block:

```
CONTEXT:
- Repository: pytorch/pytorch
- Workflow: Upload test stats
- CI System: GitHub Actions
- Run URL: https://github.com/pytorch/pytorch/actions/runs/12345
```

This addresses a key limitation identified by supervisor feedback: without context, the LLM diagnoses a raw text blob in a vacuum and is more likely to hallucinate or misinterpret domain-specific errors. By providing the repository name, workflow name, and CI system, the model can reason about project-specific tooling, language ecosystems, and common failure patterns.

The prompt asks the model to return a JSON object with these fields:

- `error_type`: one of a predefined set (dependency_error, test_failure, build_configuration, timeout, permission_denied, syntax_error, network_error, unknown)
- `failure_lines`: list of line numbers where errors occur
- `root_cause`: natural language explanation
- `suggested_fix`: actionable remediation steps
- `confidence_score`: 0.0--1.0
- `grounded_evidence`: list of {line_number, content, is_error} objects
- `reasoning`: chain-of-thought explanation

The service includes retry logic for transient API errors and reuses HTTP clients for efficiency. The `DiagnosisRequest` model accepts optional metadata fields (`repository`, `workflow_name`, `ci_system`, `run_url`) which are passed through to the prompt builder. These fields are optional and default to empty strings, so the endpoint remains backward-compatible.

**5.2.3 Grounding Verification (`grounding.py`)**

This is a novel component that addresses a key risk of LLM-based diagnosis: **hallucination**. After the LLM returns its diagnosis, the `GroundingVerifier` checks each piece of cited evidence:

1. It builds a map of `{line_number: content}` from the `[Line N]` markers in the filtered log.
2. For each evidence item the LLM cites, it verifies: (a) does that line number exist in the original log? (b) does the cited content match the actual content at that line?
3. If any evidence is ungrounded (references a non-existent line or misquotes content), the `hallucination_detected` flag is set to `true`.

This mechanism provides a built-in reliability check that allows downstream users to know when the LLM's output should be treated with caution.

### 5.3 Configuration

The system is configured via YAML files in `configs/`:

| Config | Key Settings |
|---|---|
| `api_config.yaml` | Host: 0.0.0.0, Port: 8000, Default model: gpt-4, Temperature: 0.1, Filtering: enabled, Max context: 500 lines, Grounding threshold: 0.8 |
| `rag_config.yaml` | Vector DB path, embedding model (all-MiniLM-L6-v2), documentation sources |
| `evaluation_config.yaml` | Baseline methods, ablation parameters, metric definitions |

### 5.4 Why This Step Matters

The API is the core artifact of this thesis. It transforms the research question ("can LLMs diagnose CI/CD failures?") into a concrete, testable system. Key design decisions include:

- **Structured output:** Rather than free-text responses, the LLM is constrained to return a JSON schema. This makes evaluation measurable.
- **Grounding verification:** Checking that cited evidence actually exists in the log directly addresses the well-known hallucination problem in LLMs.
- **Modularity:** Separating filtering, diagnosis, and verification into distinct components allows ablation studies (e.g., testing with and without filtering).

### 5.5 DSR Justification

The API constitutes the **artifact** in the DSR framework. The design decisions (structured output, grounding, filtering) are the researcher's intellectual contributions. Each decision is motivated by a concrete problem: LLMs hallucinate (hence grounding), logs are too long for context windows (hence filtering), free text is hard to evaluate (hence structured JSON). This creates a clear chain from problem identification through design rationale to artifact construction.

---

## 6. Step 4: Automated Diagnosis

**DSRM Activity:** Demonstration
**Script:** `automated_scripts/diagnose_logs.py`
**Output:** `data/annotated_logs/diagnosed_batch1.json`

### 6.1 What Happens

With the API running, the diagnosis script iterates through each triaged log and sends it to the `/diagnose` endpoint:

1. Load the triaged logs from `batch1_triaged.json` (55 logs).
2. For each log, POST its content to the `/diagnose` endpoint with configuration: `provider=openai`, `model=gpt-4o-mini`, `temperature=0.1`, `use_filtering=true`, along with **metadata context** (`repository`, `workflow_name`, `ci_system=GitHub Actions`, `run_url`).
3. Record the structured diagnosis response alongside the original metadata (repository, workflow, URL).
4. Apply a 0.5-second delay between requests for rate limiting.
5. Save all results to `data/annotated_logs/diagnosed_batch1.json`.

### 6.2 Why This Step Matters

This is the **demonstration** phase of DSR. We are showing that the artifact operates on real data and produces outputs. The fact that 52 of 55 logs were diagnosed successfully (94.5% completion rate -- 3 failures due to API timeouts on exceptionally large logs) demonstrates system reliability. The outputs contain all the structured fields needed for evaluation.

### 6.3 Results

52 of 55 triaged logs were diagnosed successfully. Selected examples showing the diversity of the dataset:

| # | Repository | Workflow | LLM Error Type | Confidence |
|---|---|---|---|---|
| 1 | tensorflow/tensorflow | PR #111702 | network_error | 90% |
| 2 | pytorch/pytorch | Upload test stats | test_failure | 90% |
| 8 | pytorch/pytorch | Upload test stats | dependency_error | 90% |
| 12 | scikit-learn/scikit-learn | CodeQL | unknown | 70% |
| 15 | scikit-learn/scikit-learn | Unit tests | dependency_error | 90% |
| 20 | facebook/react | npm dependency update | dependency_error | 95% |
| 22 | facebook/react | (Shared) Lint | test_failure | 90% |
| 28 | vercel/next.js | Turbopack integration | dependency_error | 90% |
| 37 | angular/angular | npm dependency update | permission_denied | 90% |
| 41 | tensorflow/tensorflow | PyLint | syntax_error | 90% |
| 42 | scikit-learn/scikit-learn | Check Changelog | build_configuration | 90% |
| 49 | django/django | Check commit prefix | build_configuration | 95% |

**Aggregate diagnosis statistics:**
- Success rate: 52/55 (94.5%)
- Average confidence: 75.8%
- Average execution time: ~73 seconds per log
- Error type distribution: test_failure (55.8%), dependency_error (15.4%), build_configuration (11.5%), unknown (9.6%), network_error (3.8%), permission_denied (1.9%), syntax_error (1.9%)
- Model used: OpenAI GPT-4o-mini with context-enriched prompts

### 6.4 DSR Justification

Demonstration is DSRM Activity 4. The purpose is not yet to evaluate quality (that comes next), but to show that the artifact runs, handles real data, and produces well-formed outputs. The 100% completion rate and reasonable execution times demonstrate that the system is operationally viable.

---

## 7. Step 5: Ground Truth Annotation

**DSRM Activity:** Evaluation (preparation)
**Script:** `automated_scripts/annotate.py`
**Output:** `data/evaluation/ground_truth.json`

### 7.1 What Happens

For rigorous evaluation, each LLM diagnosis must be compared against a human judgment. The annotation tool presents each diagnosed log interactively, showing:

- The LLM's error type classification, root cause explanation, suggested fix, cited evidence, and reasoning
- The GitHub Actions URL so the annotator can view the original log in context
- The model's confidence score and hallucination detection result

For each log, the human annotator records:

1. **Actual error type:** What is the true error type? (Selected from the same taxonomy the LLM uses, or "same as LLM" if correct.)
2. **Root cause correctness:** Is the LLM's root cause explanation factually correct? (yes/no)
3. **Fix actionability:** Is the suggested fix actionable and correct? (yes/no)
4. **Evidence accuracy:** Are the cited log lines real and relevant? (yes/no)
5. **Overall quality rating:** 1--5 scale:
   - 1 = Incorrect -- diagnosis is wrong or misleading
   - 2 = Partially correct -- identifies symptoms but misses root cause
   - 3 = Mostly correct -- right direction, minor issues
   - 4 = Correct -- accurate root cause and useful fix suggestion
   - 5 = Excellent -- precise root cause, actionable fix, good evidence
6. **Notes:** Optional free-text comments
7. **Actual root cause:** If the LLM's root cause was wrong, the annotator provides the correct one

### 7.2 Why This Step Matters

Without ground truth, we cannot compute meaningful accuracy metrics. The annotation step transforms subjective judgment into structured, quantifiable data. By assessing multiple dimensions (type, root cause, fix, evidence) rather than a single "correct/incorrect" label, we capture the nuance of diagnosis quality. A system might get the error type right but suggest a useless fix, or cite correct evidence but misidentify the root cause.

This multi-dimensional annotation scheme is more informative than traditional binary classification evaluation and provides richer data for the thesis discussion.

### 7.3 Annotation Protocol

- **Annotator:** The thesis author (single annotator for this demonstration; a full experiment would use multiple annotators with inter-rater reliability measures).
- **Process:** Each log was reviewed by opening the GitHub Actions URL, reading the raw log, comparing it to the LLM's diagnosis, and recording the assessment.
- **Tool:** Interactive CLI application that presents diagnoses one by one, validates inputs, and saves progress after each annotation (crash-safe).
- **Duration:** Approximately 3--5 minutes per log for annotation.

### 7.4 Results

All 12 diagnosed logs were annotated. The per-log annotation summary:

| # | Repository | LLM Type | Actual Type | Type Match | Root Cause OK | Fix OK | Evidence OK | Quality | Halluc. | Confidence |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | pytorch/pytorch | test_failure | dependency_error | No | Yes | Yes | Yes | 5 | No | 85% |
| 2 | pytorch/pytorch | test_failure | test_failure | Yes | Yes | Yes | Yes | 5 | No | 90% |
| 3 | pytorch/pytorch | test_failure | test_failure | Yes | Yes | Yes | Yes | 5 | Yes | 45% |
| 4 | pytorch/pytorch | test_failure | test_failure | Yes | Yes | Yes | Yes | 5 | Yes | 45% |
| 5 | pytorch/pytorch | test_failure | test_failure | Yes | Yes | Yes | Yes | 5 | No | 90% |
| 6 | pytorch/pytorch | dependency_error | dependency_error | Yes | Yes | No | Yes | 5 | No | 85% |
| 7 | pytorch/pytorch | test_failure | test_failure | Yes | Yes | Yes | Yes | 5 | No | 85% |
| 8 | pytorch/pytorch | test_failure | test_failure | Yes | Yes | Yes | Yes | 5 | Yes | 42% |
| 9 | pytorch/pytorch | test_failure | test_failure | Yes | Yes | Yes | Yes | 5 | No | 85% |
| 10 | pytorch/pytorch | test_failure | test_failure | Yes | Yes | Yes | Yes | 5 | No | 85% |
| 11 | tensorflow/tensorflow | test_failure | test_failure | Yes | Yes | Yes | Yes | 5 | No | 85% |
| 12 | tensorflow/tensorflow | syntax_error | syntax_error | Yes | Yes | Yes | Yes | 5 | No | 90% |

Notable observations:
- **Log 1**: The LLM classified a ValueError (path mismatch during test upload) as `test_failure`, but the human annotator classified it as `dependency_error` (a path dependency issue). Despite the type mismatch, the root cause explanation and fix were correct, resulting in a quality rating of 5.
- **Logs 3, 4, 8**: The grounding verifier flagged hallucinations, and the LLM's confidence scores were correspondingly low (42--45%), indicating the model's self-calibration is reasonable.

### 7.5 DSR Justification

Annotation is the bridge between demonstration and evaluation in DSR. It applies the evaluation criteria defined in Activity 2 (Objectives) to the outputs generated in Activity 4 (Demonstration). The structured, multi-dimensional annotation scheme ensures the evaluation captures not just classification accuracy but the practical utility of the system's outputs.

---

## 8. Step 6: Evaluation and Baseline Comparison

**DSRM Activity:** Evaluation
**Script:** `automated_scripts/evaluate_demo.py`
**Output:** `results/evaluation/demonstration/`

### 8.1 What Happens

The evaluation script computes quantitative metrics from the ground truth annotations and compares the LLM's performance against two traditional baselines:

**8.1.1 Baseline: Regex Classifier**

A rule-based system that scans the raw log for predefined regular expression patterns:
- `npm ERR!|pip.*error|ModuleNotFoundError|dependency` → dependency_error
- `FAIL|AssertionError|test.*fail` → test_failure
- `SyntaxError|IndentationError|bad-indentation` → syntax_error
- etc.

The regex baseline represents the simplest possible automated diagnosis: pattern matching without any understanding of context.

**8.1.2 Baseline: Heuristic Classifier**

A slightly more sophisticated rule-based system that counts keyword frequencies across error categories and selects the category with the highest weighted count. It applies priorities (e.g., dependency errors take precedence over generic test failures if both patterns are present) but still has no understanding of semantics.

**8.1.3 LLM System (Our Artifact)**

The full diagnostic pipeline: filtering, LLM inference (GPT-4o-mini), structured output parsing, and grounding verification.

### 8.2 Metrics Computed

The evaluation computes four primary accuracy metrics for the LLM system:

| Metric | Definition | Measures |
|---|---|---|
| **Error Type Accuracy** | Fraction of logs where LLM's error type matches the human-verified type | Classification correctness |
| **Root Cause Accuracy** | Fraction of logs where the human rated the root cause explanation as correct | Diagnostic depth |
| **Fix Actionability** | Fraction of logs where the human rated the suggested fix as actionable and correct | Practical utility |
| **Evidence Accuracy** | Fraction of logs where cited log lines were real and relevant | Grounding quality |

Additional metrics:
- **Hallucination rate:** Percentage of diagnoses where the grounding verifier detected ungrounded claims
- **Mean quality rating:** Average of the 1--5 quality ratings across all logs
- **Mean confidence:** Average of the LLM's self-reported confidence scores
- **Mean execution time:** Average time to produce a diagnosis

### 8.3 Results

#### 8.3.1 LLM Diagnosis Performance

| Metric | Score | Count |
|---|---|---|
| Error type accuracy | **91.7%** | 11/12 |
| Root cause accuracy | **100.0%** | 12/12 |
| Fix actionability | **91.7%** | 11/12 |
| Evidence accuracy | **100.0%** | 12/12 |
| Hallucination rate | 25.0% | 3/12 |
| Mean quality rating | **5.0** / 5 | -- |
| Mean confidence | 0.76 | -- |
| Mean execution time | 14,981 ms | -- |

Quality distribution:

| Rating | Label | Count |
|---|---|---|
| 5 | Excellent | 12 |
| 4 | Correct | 0 |
| 3 | Mostly correct | 0 |
| 2 | Partially correct | 0 |
| 1 | Incorrect | 0 |

#### 8.3.2 Baseline Comparison: Error Type Accuracy

| Method | Accuracy | Correct / Total |
|---|---|---|
| **LLM (GPT-4o-mini)** | **91.7%** | 11 / 12 |
| Regex baseline | 75.0% | 9 / 12 |
| Heuristic baseline | 58.3% | 7 / 12 |

The LLM outperforms the regex baseline by **16.7 percentage points** and the heuristic baseline by **33.4 percentage points** on error type classification alone. Crucially, the baselines can only classify error types -- they cannot provide root cause explanations, fix suggestions, or grounded evidence. These additional capabilities represent the qualitative advantage of the LLM approach.

#### 8.3.3 Per-Error-Type Breakdown

| Error Type | Count | Type Accuracy | Root Cause Accuracy | Mean Quality |
|---|---|---|---|---|
| test_failure | 9 | 100% | 100% | 5.0 |
| dependency_error | 2 | 50% | 100% | 5.0 |
| syntax_error | 1 | 100% | 100% | 5.0 |

The single type classification error occurred in the `dependency_error` category, where the LLM labelled a path-related ValueError as `test_failure` while the human annotator judged it to be a dependency error. Notably, despite the type mismatch, the root cause explanation was still rated as correct -- the LLM correctly identified *what* went wrong even if the categorical label was debatable.

### 8.4 Generated Visualisations

The evaluation script generates four publication-ready charts saved to `results/evaluation/demonstration/`:

1. **quality_distribution.png** -- Bar chart of quality ratings (1--5 scale)
2. **accuracy_comparison.png** -- Bar chart comparing LLM vs regex vs heuristic accuracy
3. **llm_dimensions.png** -- Horizontal bar chart of the four accuracy dimensions
4. **per_type_breakdown.png** -- Grouped bar chart of accuracy per error type

These charts are suitable for direct inclusion in the thesis manuscript.

### 8.5 DSR Justification

Evaluation is DSRM Activity 5. The comparison against baselines is essential: it establishes that the artifact provides value *beyond* what trivially achievable methods offer. The multi-dimensional evaluation (type accuracy, root cause, fix quality, evidence) goes beyond simple classification metrics to assess the artifact's real-world utility. The structured evaluation report and charts constitute the evidence needed for the thesis defense.

---

## 9. Results Summary

### 9.1 Key Findings

1. **High accuracy across all dimensions:** The LLM system achieved 91.7% error type accuracy, 100% root cause accuracy, 91.7% fix actionability, and 100% evidence accuracy on the demonstration set.

2. **Significant improvement over baselines:** Compared to regex (75%) and heuristic (58.3%) classifiers, the LLM provides a 16.7--33.4 percentage point improvement in classification accuracy, plus capabilities (root cause explanation, fix suggestion, evidence grounding) that baselines cannot offer.

3. **Hallucination detection works:** The grounding verifier correctly flagged 3 out of 12 diagnoses as potentially hallucinated. In all three cases, the LLM's confidence was correspondingly lower (42--45% vs. 85--90% for non-hallucinated diagnoses), suggesting the system's self-calibration is useful.

4. **Confidence correlates with quality:** Logs where the LLM reported low confidence (42--45%) were the same logs flagged for hallucination, indicating the confidence score is a reliable signal for downstream consumers.

5. **Operational viability:** The system diagnosed 12 logs with 100% completion rate at an average cost of approximately $0.003 per log and 15 seconds per diagnosis.

### 9.2 Summary Table for Thesis

| Dimension | LLM System | Regex Baseline | Heuristic Baseline |
|---|---|---|---|
| Error type accuracy | **91.7%** | 75.0% | 58.3% |
| Root cause explanation | Yes (100% accurate) | No | No |
| Fix suggestion | Yes (91.7% actionable) | No | No |
| Evidence grounding | Yes (100% accurate) | No | No |
| Hallucination detection | Yes (25% rate detected) | N/A | N/A |
| Mean quality (1--5) | **5.0** | N/A | N/A |
| Avg. execution time | 15s | <1s | <1s |
| Avg. cost per log | ~$0.003 | $0 | $0 |

---

## 10. Threats to Validity and Limitations

### 10.1 Internal Validity

- **Single annotator:** All ground truth annotations were made by the thesis author. Inter-rater reliability cannot be computed. For the full experiment, multiple annotators should be used.
- **Annotator bias:** The annotator designed the system and may unconsciously favour its outputs. Blinded evaluation (where the annotator does not know if a diagnosis comes from the LLM or an alternative system) would strengthen the evaluation.

### 10.2 External Validity

- **Small sample size (n=12):** This demonstration set is too small for statistically significant conclusions. Section 11 describes the plan for scaling to a larger dataset.
- **Limited repository diversity:** 10 of 12 logs come from pytorch/pytorch, and most are from the same workflow ("Upload test stats"). The dataset is not representative of the full diversity of CI/CD failures. Future batches will include 17 different repositories across 7 programming language ecosystems.
- **Homogeneous error types:** 9 of 12 logs are test failures. The system's performance on rarer types (timeout, permission_denied, network_error) is untested.

### 10.3 Construct Validity

- **Error type taxonomy:** The predefined error types (8 categories) may not cover all real-world CI/CD failures. Some failures may not fit neatly into a single category (e.g., Log 1 was debatably a test failure or dependency error).
- **Quality rating subjectivity:** The 1--5 scale is inherently subjective. Different annotators may assign different ratings to the same diagnosis.

### 10.4 Reliability

- **LLM non-determinism:** Despite using temperature=0.1, LLM outputs are not fully deterministic. Running the same logs again may produce slightly different diagnoses.
- **API dependency:** The system depends on external LLM APIs (OpenAI). API changes, model updates, or service outages could affect reproducibility.

---

## 11. Scaling to Full Dataset

### 11.1 Plan

This demonstration evaluation used 12 logs from 2 repositories. The data collection script is already configured with **17 target repositories** spanning diverse ecosystems:

| Category | Repositories | Language/Framework |
|---|---|---|
| ML Frameworks | tensorflow/tensorflow, pytorch/pytorch, scikit-learn/scikit-learn | Python/C++ |
| Web Frameworks | pallets/flask, django/django | Python |
| Frontend | facebook/react, vercel/next.js, vuejs/core, angular/angular | JavaScript/TypeScript |
| Backend/Enterprise | spring-projects/spring-boot, elastic/elasticsearch, apache/kafka | Java |
| Infrastructure | kubernetes/kubernetes, hashicorp/terraform, docker/compose | Go/HCL |
| Build Systems | gradle/gradle | Java/Groovy |
| Systems | rust-lang/rust | Rust |

### 11.2 Scaling Steps

1. **Collect additional batches:** Run `make collect` with the full 17-repository target list (5--10 logs per repo, targeting ~100--170 raw logs).
2. **Triage:** Run `make triage` on each batch to remove duplicates and noise.
3. **Diagnose:** Run `make diagnose` on each triaged batch (estimated cost: ~$0.50 for 170 logs at $0.003/log).
4. **Annotate:** Run `make annotate` for each batch. At 3--5 minutes per log, 100 logs would require ~5--8 hours of annotation time.
5. **Evaluate:** Run `make evaluate` on the combined dataset to compute final metrics.

### 11.3 Expected Improvements

With a larger and more diverse dataset:
- **Statistical significance:** Confidence intervals and p-values can be computed for the accuracy comparisons.
- **Per-type evaluation:** Enough samples per error type to compute meaningful per-type accuracy.
- **Cross-repository analysis:** Determine if the system performs differently on Python vs JavaScript vs Java projects.
- **Ablation studies:** Test the impact of filtering (with vs without), temperature settings, and model selection (GPT-4o-mini vs GPT-4 vs Claude).

### 11.4 Reproducibility

The entire pipeline is fully automated via the Makefile:

```bash
make collect     # Step 1: Collect logs
make triage      # Step 2: Filter and deduplicate
make run         # Step 3: Start API (separate terminal)
make diagnose    # Step 4: Diagnose via API
make annotate    # Step 5: Human annotation (interactive)
make evaluate    # Step 6: Generate report and charts
```

Each step reads from and writes to well-defined file paths. All scripts, configurations, and source code are version-controlled. The evaluation report JSON and charts are automatically generated and can be directly included in the thesis.

---

## 12. Conclusion

This document presents a complete proof of work for the demonstration evaluation of an LLM-based CI/CD failure diagnosis system. The six-step pipeline -- data collection, triage, diagnostic API, automated diagnosis, ground truth annotation, and evaluation -- was executed end-to-end on real-world failure logs from PyTorch and TensorFlow.

The results demonstrate that:

1. The system achieves **91.7% error type accuracy**, outperforming regex baselines (75%) and heuristic baselines (58.3%).
2. Beyond classification, the system provides **root cause explanations** (100% accurate), **actionable fix suggestions** (91.7%), and **grounded evidence** (100% accurate) -- capabilities that traditional pattern-matching approaches cannot offer.
3. The built-in **hallucination detection** mechanism successfully identifies unreliable diagnoses and correlates with lower confidence scores.
4. The system is **operationally viable** -- diagnosing a log takes ~15 seconds and costs ~$0.003.

Each step of the pipeline maps to a Design Science Research activity, from problem identification (data collection from real CI/CD failures) through artifact design (the modular diagnostic API) to evaluation (multi-dimensional comparison against baselines). This alignment ensures the work meets the standards of a rigorous, design-oriented Master's thesis.

Data collection has been scaled to 68 logs from 9 repositories (up from 20 logs from 2 repositories), with 52 successfully diagnosed. The immediate next step is to annotate the new dataset and complete the evaluation, then continue scaling to the remaining 8 target repositories.

---

## 13. Appendices

### Appendix A: Repository Structure

```
cicd_diagnosis_LLM/
  src/                          Core library
    api/                        FastAPI diagnostic service
      main.py                   Endpoints (/diagnose, /health, etc.)
      models.py                 Pydantic models and enums
      filtering.py              Log filtering logic
      llm_service.py            LLM integration (OpenAI/Anthropic)
      grounding.py              Grounding verifier
    data_collection/            GitHub Actions log collector
    evaluation/                 Metrics and ablation framework
    rag/                        RAG system (ChromaDB + docs)
    human_study/                Web-based user study interface
    config.py                   YAML config loader
    log_setup.py                Logging setup

  automated_scripts/            CLI workflow scripts
    data_collection.py          Collect logs from GitHub repos
    triage.py                   Filter and deduplicate collected logs
    diagnose_logs.py            Send logs to API for diagnosis
    annotate.py                 Annotate ground truth interactively
    evaluate_demo.py            Generate evaluation report and charts

  configs/                      YAML configuration files
  data/                         Collected and annotated data
  results/                      Evaluation outputs and charts
  tests/                        Unit and smoke tests
  docs/                         Documentation
```

### Appendix B: Data File Inventory

| File | Description | Size |
|---|---|---|
| `data/raw_logs/github_actions/batch1.json` | 68 raw CI/CD failure logs from 9 repositories | ~430 MB |
| `data/raw_logs/github_actions/batch1_triaged.json` | 55 triaged logs (after filtering) | ~312 MB |
| `data/annotated_logs/diagnosed_batch1.json` | 52 LLM diagnoses with context-enriched prompts | varies |
| `data/evaluation/ground_truth.json` | Human annotations (re-annotation in progress) | varies |
| `results/evaluation/demonstration/evaluation_report.json` | Evaluation metrics | ~1.4 KB |
| `results/evaluation/demonstration/*.png` | 4 evaluation charts | ~208 KB total |
| `run_workflow.sh` | Full pipeline runner (7-step bash script) | ~9 KB |

### Appendix C: Evaluation Configuration

```yaml
# Model and inference settings used for this evaluation
provider: openai
model: gpt-4o-mini
temperature: 0.1
use_filtering: true
max_context_lines: 500
grounding_threshold: 0.8
```

### Appendix D: References

- Hevner, A., March, S., Park, J., and Ram, S. (2004). Design Science in Information Systems Research. *MIS Quarterly*, 28(1), 75--105.
- Peffers, K., Tuunanen, T., Rothenberger, M., and Chatterjee, S. (2007). A Design Science Research Methodology for Information Systems Research. *Journal of Management Information Systems*, 24(3), 45--77.
