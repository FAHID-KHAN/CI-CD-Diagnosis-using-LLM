# Research Questions — Revised Draft

**Thesis:** LLM-Based CI/CD Failure Diagnosis  
**Author:** Fahid Khan  
**Supervisors:** Jussi Rasku & Md Mahade Hasan  
**Date:** 30 March 2026  
**Status:** Draft — pending supervisor approval  

---

## Methodology

This thesis follows the **Design Science Research (DSR)** methodology. The artifact is an automated diagnostic system that uses Large Language Models to classify and explain CI/CD pipeline failures from log data. The research questions evaluate the artifact's effectiveness, compare design choices, and identify its strengths and limitations.

---

## Primary Research Question

> **PRQ: How effectively can an LLM-based diagnostic system identify failure causes in CI/CD pipeline logs?**

**Scope:** Measures the overall diagnostic capability of the artifact — error type classification accuracy, root cause quality, and evidence grounding — across real-world CI/CD failure logs from 17 open-source repositories.

**How it will be answered:**
- Run the diagnostic system on a curated dataset of annotated CI/CD failure logs
- Compare LLM output against human-annotated ground truth
- Compare against baseline approaches (regex pattern matching, keyword heuristics)
- Report overall accuracy, precision/recall/F1, hallucination rate, and execution time

**Expected output:**
- Summary table: LLM accuracy vs regex baseline vs heuristic baseline
- Confidence calibration analysis
- Hallucination rate (% of diagnoses with ungrounded evidence)

---

## Sub-Research Questions

### SRQ1: How does the diagnostic accuracy of proprietary LLMs compare to open-source LLMs for CI/CD failure classification?

**Motivation:** Using a single commercial model (e.g., GPT-4) has no novelty (Mahade, March 11 meeting). Comparing proprietary vs open-source models reveals whether expensive API-based models justify their cost for this task.

**Models to compare:**

| Category | Model | Access |
|----------|-------|--------|
| Proprietary | GPT-4o-mini (OpenAI) | API |
| Open-source | Llama 3 (Meta) | Local via Ollama |
| Open-source | Mistral 7B (Mistral AI) | Local via Ollama |

**Experiment design:**
1. Use the same set of 50+ annotated logs as input to all three models
2. Run via `benchmark_models.py` (direct LLM calls, no HTTP overhead)
3. Compare each model's output against the same ground truth

**Metrics:**

| Metric | What it measures |
|--------|-----------------|
| Error type accuracy | % of logs where the model identified the correct error category |
| Root cause F1 | Overlap between predicted and actual root cause (token-level) |
| Confidence calibration | Correlation between model confidence and actual correctness |
| Grounding score | % of cited evidence that actually exists in the log |
| Latency | Average diagnosis time (ms) per log |
| Cost | Estimated USD per diagnosis (API pricing vs local compute) |

**Expected output:**
- Model comparison table (accuracy, F1, grounding, speed, cost)
- Cost-accuracy trade-off chart
- Statistical significance tests (McNemar's or paired bootstrap)

---

### SRQ2: What is the impact of log preprocessing on LLM diagnostic accuracy?

**Motivation:** CI/CD logs can be thousands of lines. Raw logs may exceed LLM context windows and contain noise. The artifact includes smart filtering (keyword-based extraction, context windowing) and token-aware truncation (tiktoken, middle-out strategy). This question measures whether these preprocessing steps improve or degrade diagnosis quality.

**Experimental conditions:**

| Condition | Description |
|-----------|-------------|
| **No preprocessing** | Raw log passed directly to LLM (truncated only by model's context limit) |
| **Keyword filtering only** | Error/warning keywords extracted with surrounding context lines |
| **Smart filtering + token truncation** | Full pipeline: keyword filter → context window → middle-out truncation to 12,000 tokens |
| **Aggressive truncation** | Token budget reduced to 4,000 tokens (testing minimal context) |

**Experiment design:**
1. Select 50+ annotated logs
2. Run the best-performing model (from SRQ1) under each condition
3. Compare accuracy and grounding under each preprocessing strategy

**Metrics:**

| Metric | What it measures |
|--------|-----------------|
| Error type accuracy | Does preprocessing change classification correctness? |
| Hallucination rate | Does less context cause more fabricated evidence? |
| Grounding score | Are cited log lines more/less accurate after filtering? |
| Token usage | How many tokens does each condition consume? |
| Latency | Does filtering reduce response time? |

**Expected output:**
- Ablation table: accuracy × hallucination rate × grounding for each condition
- Token usage vs accuracy chart
- Recommendation: optimal preprocessing strategy

---

### SRQ3: Which categories of CI/CD failures are LLMs most and least effective at diagnosing?

**Motivation:** Not all CI/CD failures are equal. Dependency resolution errors produce different log patterns than test assertion failures or timeout issues. Understanding where LLMs succeed and fail provides actionable guidance for practitioners adopting LLM-based diagnostics.

**Error categories in the artifact:**

| Error Type | Example |
|------------|---------|
| `dependency_error` | Package version conflict, missing module |
| `test_failure` | Assertion error, test timeout |
| `build_configuration` | Wrong compiler flags, missing env var |
| `timeout` | Job exceeded time limit |
| `permission_denied` | Auth failure, insufficient access |
| `syntax_error` | Code parse error |
| `network_error` | DNS failure, connection refused |
| `unknown` | Unclassifiable failure |

**Experiment design:**
1. Use the full annotated dataset (ensuring representation across all error types)
2. Run all models from SRQ1
3. Break down results by error category

**Metrics:**

| Metric | What it measures |
|--------|-----------------|
| Per-type accuracy | Classification accuracy within each error category |
| Per-type precision/recall/F1 | Detection quality per category |
| Confusion matrix | Which error types get confused with each other |
| Root cause quality per type | Are some error types easier to explain than others? |

**Expected output:**
- Per-error-type heatmap (models × error types × accuracy)
- Confusion matrix showing misclassification patterns
- Ranked list: easiest → hardest failure types for LLM diagnosis
- Gap analysis: where does the LLM fall below the regex/heuristic baseline?

---

## How RQs Map to Thesis Chapters

| RQ | Chapter | Content |
|----|---------|---------|
| PRQ | Results (5.1) | Overall system performance, comparison to baselines |
| SRQ1 | Results (5.2) | Model comparison tables, cost-accuracy analysis |
| SRQ2 | Results (5.3) | Preprocessing ablation, token budget analysis |
| SRQ3 | Results (5.4) | Per-error-type breakdown, confusion matrices |
| All | Discussion (6) | Implications for practice, limitations, threats to validity |

---

## How RQs Map to DSR Framework

| DSR Component | Addressed By |
|---------------|-------------|
| **Problem identification** | CI/CD failures are costly to diagnose; logs are noisy and long |
| **Artifact design** | LLM-based diagnostic system with preprocessing pipeline, multi-model support, grounding verification |
| **Evaluation** | PRQ → does the artifact work? SRQ1 → which model choice is best? SRQ2 → does preprocessing help? SRQ3 → where does it fail? |
| **Contribution** | Design principles for LLM-based log diagnosis + empirical comparison data for practitioners |

---

## Dataset

| Property | Value |
|----------|-------|
| Source | GitHub Actions logs from 17 public repositories |
| Domains | ML (TensorFlow, PyTorch, scikit-learn), Web (React, Next.js, Vue, Angular), Backend (Flask, Django, Spring Boot), Infrastructure (Kubernetes, Terraform, Docker, Elasticsearch, Kafka), Build tools (Gradle), Systems (Rust) |
| Collection | GitHub Actions API — failed workflow runs |
| Triage | Noise removal (cancelled runs, token errors, duplicates) |
| Ground truth | Manual annotation by domain expert + seeded synthetic logs with known defects |

---

## Summary Table

| | Research Question | Experiment | Key Metrics | Tool |
|---|---|---|---|---|
| **PRQ** | How effectively can an LLM-based system identify CI/CD failure causes? | Full pipeline on annotated logs vs baselines | Accuracy, F1, hallucination rate, latency | `make evaluate` |
| **SRQ1** | How do proprietary vs open-source LLMs compare? | GPT-4o-mini vs Llama3 vs Mistral on identical logs | Per-model accuracy, cost, speed, grounding | `make benchmark` |
| **SRQ2** | What is the impact of log preprocessing? | Ablation: raw vs filtered vs truncated | Accuracy delta, hallucination delta, token usage | `evaluate_demo.py` ablation |
| **SRQ3** | Which failure types are easiest/hardest to diagnose? | Per-error-type breakdown across all models | Per-type P/R/F1, confusion matrix | `make evaluate` |

---

*Draft prepared 30 March 2026. To be reviewed and approved by supervisors before proceeding with experiments.*
