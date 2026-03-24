# Executive Summary: LLM-Based CI/CD Failure Diagnosis

**Fahid Khan** | Master's Thesis, Tampere University | March 2026
Supervisors: Jussi Rasku & Md Mahade Hasan

---

## Problem

When CI/CD pipelines fail, developers manually read through thousands of lines of unstructured build logs to find what went wrong and how to fix it. This is slow, error-prone, and requires domain expertise. Existing automated approaches are limited to simple regex pattern matching, which can classify errors but cannot explain *why* a build failed or *how* to fix it.

## Research Question

> To what extent can Large Language Models accurately diagnose CI/CD pipeline failures from raw build logs, and how does their performance compare to traditional pattern-matching approaches?

**Sub-questions addressed in the demonstration evaluation:**

1. How accurately does the LLM classify CI/CD failure error types compared to regex-based approaches?
2. Can a grounding verification mechanism reliably detect LLM hallucinations in log diagnosis?
3. Does the LLM provide actionable root cause explanations and fix suggestions beyond what baselines offer?

## System Overview

The artifact is a modular diagnostic pipeline built with FastAPI and GPT-4o-mini:

```
Raw CI/CD Log ──> Log Filtering ──> Context Enrichment ──> LLM Diagnosis ──> Grounding Verification ──> Structured Report
                  (noise removal,     (repository name,    (GPT-4o-mini,     (checks cited lines       {error_type,
                   context windows,    workflow, CI system,  structured JSON    exist in original log,    root_cause,
                   line numbering)     run URL)              output)            flags hallucinations)     fix, evidence}
```

**Key design decisions:** (1) Structured JSON output enables measurable evaluation. (2) Log filtering reduces noise and fits context windows. (3) Context enrichment provides the LLM with repository and workflow metadata so it can reason about project-specific patterns rather than diagnosing a raw text blob in isolation. (4) Grounding verification addresses LLM hallucination risk by cross-checking cited evidence against the original log.

## Results

An initial demonstration evaluation was conducted on 12 logs from PyTorch and TensorFlow. The system has since been scaled to **68 raw logs from 9 repositories**, with **52 successfully diagnosed** (94.5% completion rate). Full re-annotation of the larger dataset is in progress.

### Headline Comparison (initial 12-log demonstration)

| Metric                | LLM (GPT-4o-mini) | Regex Baseline | Heuristic Baseline |
|-----------------------|:------------------:|:--------------:|:------------------:|
| Error type accuracy   | **91.7%**          | 75.0%          | 58.3%              |
| Root cause explanation| **100% accurate**  | Not capable    | Not capable        |
| Fix suggestion        | **91.7% actionable**| Not capable   | Not capable        |
| Evidence grounding    | **100% accurate**  | Not capable    | Not capable        |

The LLM outperforms regex by **+16.7pp** and heuristics by **+33.4pp** on classification alone -- while additionally providing root cause explanations, actionable fixes, and grounded evidence that baselines cannot offer at all.

### Scaled Dataset (52 diagnosed logs)

| Metric | Value |
|---|:---:|
| Repositories covered | 9 (TensorFlow, PyTorch, scikit-learn, Flask, Django, React, Next.js, Vue, Angular) |
| Error types observed | 7 (test_failure 55.8%, dependency_error 15.4%, build_configuration 11.5%, unknown 9.6%, network_error 3.8%, permission_denied 1.9%, syntax_error 1.9%) |
| Avg. confidence | 75.8% |
| Completion rate | 94.5% (52/55) |

### Hallucination Detection

The grounding verifier flagged 3 of 12 diagnoses (25%) as containing potentially hallucinated references. In all three cases, the LLM's self-reported confidence was correspondingly low (42--45% vs. 85--90% for clean diagnoses), confirming that confidence scores serve as a reliable trust signal.

### Operational Metrics

| Metric              | Value        |
|---------------------|:------------:|
| Completion rate     | 100% (12/12) |
| Avg. execution time | ~15 seconds  |
| Avg. cost per log   | ~$0.003      |
| Mean quality rating | 5.0 / 5      |

## Methodology

The work follows **Design Science Research Methodology** (Hevner et al., 2004; Peffers et al., 2007) with iterative build-evaluate-refine cycles:

| DSR Activity             | Mapping                                                        |
|--------------------------|----------------------------------------------------------------|
| Problem Identification   | Manual CI/CD log diagnosis is slow and error-prone             |
| Objectives               | Accurate classification + root cause + fix + grounding         |
| Design & Development     | Modular pipeline: filtering, LLM inference, grounding verification |
| Demonstration            | 12 real-world logs from PyTorch and TensorFlow                 |
| Evaluation               | Multi-dimensional comparison against regex and heuristic baselines |
| Communication            | This summary, proof of work document, thesis manuscript        |

**Design iterations:**

- *Iteration 1:* Raw logs sent directly to LLM -- noisy input, poor context fit. Added log filtering with keyword-based extraction and context windows.
- *Iteration 2:* Filtered logs improved accuracy, but LLM occasionally cited non-existent line numbers. Added grounding verification to detect hallucinated references.
- *Iteration 3:* Free-text LLM output was difficult to evaluate quantitatively. Added structured JSON schema to enable measurable, multi-dimensional evaluation.
- *Iteration 4:* LLM diagnosed logs in isolation with no project context, increasing hallucination risk. Added context-enriched prompts with repository name, workflow name, CI system, and run URL.

## Limitations & Threats to Validity

- **Initial evaluation sample (n=12):** Scaled dataset (n=52) awaiting re-annotation for updated metrics.
- **Single annotator (thesis author):** Potential bias; no inter-rater reliability computed.
- **Improved diversity:** 68 logs from 9 repositories across 3 language ecosystems (Python, JavaScript/TypeScript, mixed). 7 error types observed vs. 3 in the initial demonstration.
- **LLM non-determinism:** Temperature=0.1 reduces but does not eliminate output variability.

## Next Steps

| Action                        | Timeline    | Purpose                                          |
|-------------------------------|:-----------:|--------------------------------------------------|
| Annotate 52 diagnosed logs    | Week 1      | Build ground truth for scaled dataset            |
| Scale to remaining 8 repos    | Weeks 1--2  | Complete 17-repo target for full diversity       |
| Refine research questions     | Week 1      | Align experiments with supervisor feedback        |
| Ablation studies              | Weeks 3--4  | Test impact of filtering, temperature, model choice |
| Multi-annotator evaluation    | Weeks 3--4  | Address single-annotator bias                    |
| Thesis Chapters 2--4          | Weeks 2--6  | Background, methodology, system design           |

---

*Full technical details: [docs/proof_of_work.md](proof_of_work.md) (678 lines) | Repository: github.com/fahidkhan/cicd_diagnosis_LLM*
