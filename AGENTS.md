# Instructions for coding agents

Read `CONTEXT.md` first for what this project is and where it stands.

This is a master's thesis tool. Its value comes from its results being
defensible, so several ordinary conveniences are forbidden here.

## Never do these

**Never write, edit or invent ground-truth annotations.** Ground truth lives in
`data/studies/*/ground_truth/ground_truth.json`. A human must read the log and
decide. If an agent writes a root cause, the ground truth becomes LLM-generated,
which is the `LLM-as-judge` path the supervisors called a last resort requiring
disclosure — and it would have to be declared as a validity threat against every
accuracy number in the thesis. Point at the evidence, never supply the answer.

**Never run the final experiment for thesis evidence.** `./run_workflow.sh final`
is under a methodology hold until supervisors approve the evaluation plan.

**Never select repositories or cases by model performance.** Selection is on log
tractability, pipeline stage and evidence availability only. Selecting by
predicted failure category is circular and invalidates the baseline comparison.

**Never edit a study config after its data was collected.** Manifests record the
config's SHA-256. Editing the file silently breaks the provenance link. If it
has already happened, `git checkout configs/<file>.yaml` restores it and the
change belongs in a new config with a new `study_id`.

**Never delete anything under `data/studies/` without explicit confirmation.** It
is gitignored, it holds hours of human annotation, and cohorts cannot be
re-collected — GitHub drops runs from its failure listing once they are re-run
successfully. Back up to a scratch directory first.

## How things work here

**One entry point.** `./run_workflow.sh <command>` runs every stage;
`./run_workflow.sh --help` lists them. `./run_workflow.sh status` reports the
state of each stage from the files on disk, not from whether a command appeared
to succeed.

**Study directories are immutable.** Collection refuses to overwrite an existing
study. A fresh cohort needs a new `study_id`, which means a new config file.

**Stages communicate through files.** Nothing calls anything else directly.
Every stage is checksummed and manifested.

**One definition per metric.** `compute_model_metrics` lives in
`src/evaluation/report_comparison.py`, and
`automated_scripts/benchmark_models.py` imports it. Do
not reimplement a metric that already exists.

**Reporting is read-only over stored results.** Anything in
`src/evaluation/comparison_view.py` or `src/evaluation/category_metrics.py`
recomputes from the
per-log `results_<model>.json` files, so a run interrupted before its summary
was written still reports correctly. Keep it that way.

## Layout

| Path | Rule |
| --- | --- |
| `automated_scripts/` | The pipeline. The runner invokes all of it. Removing any file breaks the tool. |
| `tools/` | Standalone utilities. The pipeline never calls these. |
| `src/api/` | Filtering, model client, grounding. |
| `src/evaluation/` | Scoring, audits, guards, reporting. |
| `docs/architecture/` | How the system works. |
| `docs/thesis/` | The research work. |
| `docs/archive/` | Superseded. Describes removed components. Never cite as current. |

## Before you finish

```bash
./run_workflow.sh check     # flake8, mypy, and the full offline test suite
```

Tests are offline and must stay that way — they never call GitHub, OpenAI or
Ollama. There are 70 of them.

Add tests for anything that enforces a methodological rule: leakage guards,
ground-truth audits, scoring. `tests/test_methodology_guards.py` is the home for
those, and each test names the decision it protects.

## Conventions

- Format with `black`, line length 120. Lint with `flake8`. Type-check `src/`
  with `mypy`.
- Comments explain **why**, not what. Most comments in this codebase record a
  methodological reason, and those are the ones worth preserving.
- Shell scripts must run on the bash 3.2 that ships with macOS. No `mapfile`,
  no associative arrays. Check with `/bin/bash -n`.
- Prefer failing loudly over degrading silently, except when reading stored
  study files — a truncated or missing report must become a reported issue, not
  an exception, so the rest of a run stays readable.
- The diagram is generated. Edit `docs/architecture/make_architecture.py` and
  run `make architecture`; never hand-edit the PNG or SVG.

## Housekeeping

```bash
./clean.sh              # caches and build artefacts
./clean.sh --dry-run    # show what would go
./clean.sh --studies    # also clear study data, after typing 'delete'
```
