# Controlled CI/CD Failure Diagnosis Study

This repository contains one thesis workflow: collect a fixed set of failed
GitHub Actions logs, triage them with documented rules, create blind human
ground truth, and compare one proprietary model with one open-weights model.

**Methodology hold:** the 21 September kickoff review requires independent,
evidence-backed ground truth, a two-repository starting scope and a genuinely
held-out final set. Do not use the current pilot or final commands for thesis
evidence until the [evaluation roadmap](docs/THESIS_EXECUTION_ROADMAP_2026-09-21.md)
has reached its methodology-approval and tool-update gates.

![Architecture](docs/architecture.png)

## Research conditions

- Proprietary: `openai/gpt-5.6-terra`
- Open-weights: `local/gpt-oss:20b` through Ollama
- Shared reasoning effort: `medium`
- Shared prompt, structured JSON schema, filtering and grounding logic

## Setup

```bash
python3.12 -m venv .venv
source .venv/bin/activate
make install
```

Create `.env` from `.env.template` and add the required credentials. Never
commit `.env`.

## Controlled workflow

Prepare the fresh cohort:

```bash
./run_workflow.sh --skip-install
```

This performs the offline checks, one-log live preflight, fixed collection and
auditable triage. It stops before human annotation.

Create blind ground truth:

```bash
make annotate ANNOTATOR=your-stable-id
```

Run the mandatory five-log paired pilot:

```bash
make pilot
```

After reviewing the pilot, run the frozen full cohort:

```bash
make final
```

The full final command and every validation gate are documented in the
[controlled study runbook](docs/CONTROLLED_STUDY_RUNBOOK.md).

## Essential structure

```text
configs/thesis_fresh_2026.yaml       Fixed study protocol
run_workflow.sh                      Cohort preparation entry point
automated_scripts/
  preflight_study.py                 Environment and one-log check
  data_collection.py                 Immutable GitHub collection
  triage.py                          Eligibility and exclusion audit
  annotate_blind.py                  Model-independent ground truth
  benchmark_models.py                Paired pilot and final experiment
  study_utils.py                     Checksums and atomic storage
src/
  data_collection/                   GitHub Actions client
  api/                               Filtering, model and grounding core
  evaluation/                        Paired statistics and result chart
tests/                               Offline tests
docs/CONTROLLED_STUDY_RUNBOOK.md     Exact operating procedure
```

## Tests

```bash
make test
```

Tests are offline and do not call GitHub, OpenAI or Ollama.

## Data policy

Generated study data is stored under `data/studies/` and ignored by Git. Back
up the full study directory separately after collection. Historical datasets
under `data/_archive_*` are preserved but are not inputs to the controlled
workflow.
