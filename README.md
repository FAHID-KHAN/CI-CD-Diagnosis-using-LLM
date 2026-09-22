# Controlled CI/CD Failure Diagnosis Study

This repository contains one thesis workflow: collect a fixed set of failed
GitHub Actions logs, triage them with documented rules, create blind human
ground truth, and compare one proprietary model with one open-weights model.

**Methodology hold:** the 21 September kickoff review requires independent,
evidence-backed ground truth, a two-repository starting scope and a genuinely
held-out final set. Do not use the current pilot or final commands for thesis
evidence until the [evaluation roadmap](docs/thesis/THESIS_EXECUTION_ROADMAP_2026-09-21.md)
has reached its methodology-approval and tool-update gates.

![Architecture](docs/architecture/architecture.png)

The diagram separates the **artifact** being evaluated (filter, prompt, schema,
grounding check) from the **evaluation apparatus** that produces and checks the
evidence. It is generated from [docs/architecture/make_architecture.py](docs/architecture/make_architecture.py);
run `make architecture` after changing the system.

## Research conditions

- Proprietary: `openai/gpt-5.6-terra`
- Open-weights: `local/thesis-qwen3.5:9b-24k` through Ollama
- Shared reasoning effort: `medium`
- Shared prompt, structured JSON schema, filtering and grounding logic

The local condition is a reproducible Ollama model derived from the
`qwen3.5:9b` weights with a fixed 24,576-token runtime context.

## Setup

```bash
python3.12 -m venv .venv
source .venv/bin/activate
make install
make local-model
```

Create `.env` from `.env.template` and add the required credentials. Never
commit `.env`.

## Controlled workflow

`run_workflow.sh` is the single entry point for every stage. Each stage is
judged by the files it leaves on disk rather than by whether a command appeared
to succeed, so this is the truthful answer to "what have I actually got?":

```bash
./run_workflow.sh status
```

```text
  [x] Study protocol frozen      6 repositories, study_id=thesis_fresh_2026
  [x] Collection                 90 raw logs from 6 repositories
  [x] Triage                     74 eligible, 16 excluded with reasons
  [ ] Ground truth               0 of 74 cases annotated
  [!] Held-out separation        5 case(s) already used by system_smoke_001
  Next: ./run_workflow.sh annotate ANNOTATOR=<your-id>
```

`[!]` marks a blocking problem and makes the command exit non-zero, so the same
check gates the held-out run. Run `./run_workflow.sh --help` for every command.

Prepare the fresh cohort:

```bash
./run_workflow.sh --skip-install
```

This performs the offline checks, one-log live preflight, fixed collection and
auditable triage. It stops before human annotation.

For an engineering-only end-to-end check, run the whole path in one command.
It creates the five-case smoke cohort, runs the paired pilot and produces the
comparison, stopping with an explicit message at any step that needs a human:

```bash
./run_workflow.sh engineering
```

To verify the code itself offline — lint, type check and the full test suite:

```bash
./run_workflow.sh check
```

Create blind ground truth for those five cases:

```bash
make annotate-smoke ANNOTATOR=your-stable-id
```

Then run the paired smoke test:

```bash
make pilot
```

Pilot output is written to `pilot_002`; `pilot_001` is retained as the failed
`gpt-oss:20b` engineering attempt. The smoke cohort is recorded as exploratory and must not be reused in the
future held-out thesis evaluation.

After reviewing the pilot, run the frozen full cohort:

```bash
make final
```

The full final command and every validation gate are documented in the
[controlled study runbook](docs/architecture/CONTROLLED_STUDY_RUNBOOK.md). The kickoff
decisions and action items are checked against the code in the
[action-item verification](docs/thesis/KICKOFF_ACTION_ITEM_VERIFICATION.md).

`make final` refuses to run over cases an exploratory cohort has already used,
so the smoke cases cannot leak into the held-out evaluation.

## Ground truth

Kickoff decision D3 rules out the researcher's unaided judgement as the sole
basis for accuracy claims, so annotation runs in two blind passes and every case
must link to checkable evidence:

```bash
make annotate-smoke ANNOTATOR=your-stable-id   # first pass, with evidence
make verify-smoke VERIFIER=second-reviewer-id  # independent second pass
make audit-ground-truth                        # check before claiming accuracy
```

The verifier sees neither the model output nor the first reviewer's answer, and
every disagreement needs a written adjudication. The audit reports a blocking
finding for any case with no evidence method, no independent verifier, an
unusable root cause, or a missing evidence reference.

Ground truth reaches the score in one place: exact match of the failure
category, with an inference failure counted as incorrect. Supporting lines are
scored separately as evidence-line accuracy. Note that the **grounding score is
not accuracy** — it only checks that a cited line existed in the log the model
was given, never that it was the right line.

## Comparing the generated reports

Each run writes one result file per condition. To read those conditions against
each other instead of one file at a time:

```bash
make compare
```

This prints a terminal comparison of every experiment under `data/studies/` and
writes a self-contained `comparison_view.html` into each experiment directory:
the model scoreboard, side-by-side metric bars, the per-log outcome matrix
against blind ground truth, where the conditions disagree, confusion matrices,
the significance tests and the full diagnosis text from every condition.

Target one run, or compare several across time:

```bash
python automated_scripts/compare_reports.py --list
python automated_scripts/compare_reports.py \
  --experiment data/studies/system_smoke_001/experiments/pilot_002 --open
```

Metrics are recomputed from the per-log result files with the same definitions
the benchmark uses, so an interrupted run still compares correctly, and a
missing or truncated report file becomes a data note on the page rather than a
crash.

## Essential structure

```text
configs/thesis_fresh_2026.yaml       Fixed study protocol
run_workflow.sh                      Single entry point for every stage
automated_scripts/
  preflight_study.py                 Environment and one-log check
  data_collection.py                 Immutable GitHub collection
  triage.py                          Eligibility and exclusion audit
  annotate_blind.py                  Model-independent ground truth
  benchmark_models.py                Paired pilot and final experiment
  compare_reports.py                 Terminal and visual report comparison
  study_status.py                    Stage-by-stage state from the files on disk
  study_utils.py                     Checksums and atomic storage
src/
  data_collection/                   GitHub Actions client
  api/                               Filtering, model and grounding core
  evaluation/                        Paired statistics and result chart
    taxonomy.py                      Shared failure vocabulary
    study_io.py                      Tolerant readers for stored study JSON
    report_comparison.py             Report loading, alignment and metrics
    category_metrics.py              Per-category and evidence-line scoring
    ground_truth_audit.py            Evidence and independence requirements
    case_partitions.py               Held-out leakage guard
    comparison_view.py               Self-contained HTML comparison page
tests/                               Offline tests
docs/
  architecture/                      How the system works and how to run it
  thesis/                            Plan, action items and supervision record
  archive/                           Superseded, kept as history only
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
