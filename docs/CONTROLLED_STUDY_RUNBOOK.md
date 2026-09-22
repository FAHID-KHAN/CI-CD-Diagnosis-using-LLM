# Controlled Thesis Study Runbook

This is the operational guide for the single supported repository workflow:
the fresh, controlled final-study dataset.

**Methodology hold:** this runbook describes the current implementation, but
the kickoff review identified unresolved research-validity requirements. Do
not execute the pilot or final study for thesis evidence until the ground-truth
and held-out design in
[the thesis evaluation roadmap](THESIS_EXECUTION_ROADMAP_2026-09-21.md) is
approved and implemented.

![Controlled architecture](architecture.png)

Generated from `docs/make_architecture.py` via `make architecture`. The current
system has no rule-based or heuristic baseline; whether one is in scope is an
open decision for the methodology review.

## Purpose and safety boundary

The controlled workflow enforces the following order:

```text
protocol → preflight → collection → triage → cohort freeze
         → blind annotation → five-log pilot → final paired experiment
         → scoring and thesis outputs
```

Ground truth must be created with `automated_scripts/annotate_blind.py`, which
never loads or displays model output.

## Engineering smoke test

The exploratory five-case workflow is separate from the future held-out thesis
evaluation:

```bash
make smoke-cohort
make annotate-smoke ANNOTATOR=<stable-id>
make pilot
```

`smoke_manifest.json` records the selection seed, source checksum, selected
case IDs and the requirement to exclude those cases from future held-out
evaluation. The command refuses to overwrite an existing smoke cohort.

## Current implementation status

| Phase | Status | Entry point |
|---|---|---|
| Study protocol | Ready | `configs/thesis_fresh_2026.yaml` |
| Offline and live preflight | Ready | `automated_scripts/preflight_study.py` |
| Immutable collection | Ready | `automated_scripts/data_collection.py --study-config ...` |
| Auditable triage | Ready | `automated_scripts/triage.py --study-config ...` |
| Blind ground-truth annotation | Ready | `automated_scripts/annotate_blind.py` |
| Five-log paired pilot | Ready after ground truth | `automated_scripts/benchmark_models.py --pilot` |
| Final paired experiment | Ready after pilot approval | `automated_scripts/benchmark_models.py` |

## Fixed study design

The versioned protocol is
[`configs/thesis_fresh_2026.yaml`](../configs/thesis_fresh_2026.yaml). It fixes:

- six repositories across Python, JavaScript/TypeScript and JVM ecosystems;
- no automatic repository discovery;
- at most 15 downloaded failures per repository;
- a maximum of 90 raw logs;
- a target of 50–70 eligible logs;
- minimum log length of 20 lines;
- at most two matching error signatures per repository;
- immutable raw records and recorded exclusion reasons.

Do not modify this protocol after collection starts. If the design must change,
create a new `study_id` and collect a separate dataset.

## Prerequisites

From the repository root:

```bash
source .venv/bin/activate
python --version
```

Expected Python version: 3.12 or newer.

The `.env` file must contain a valid GitHub token:

```env
GITHUB_TOKEN=github_pat_your_token
```

Later model phases also require:

```env
OPENAI_API_KEY=your_openai_key
```

The local condition requires Ollama and the tracked
`thesis-qwen3.5:9b-24k` model, but neither is required
for collection or triage.

## Checking where the study stands

Every phase below leaves artefacts on disk, and `run_workflow.sh status` judges
each phase by those artefacts rather than by whether a command appeared to
succeed. Run it between any two phases, or whenever you return to the project:

```bash
./run_workflow.sh status
./run_workflow.sh status --study-dir data/studies/system_smoke_001
```

States are `[x]` done, `[~]` partial, `[ ]` not started and `[!]` blocking. Any
`[!]` makes the command exit non-zero, and the same inspector gates the
held-out run, so `./run_workflow.sh final` refuses while ground truth is
incomplete or the cohort overlaps an exploratory set.

`./run_workflow.sh --help` lists every command. The stage commands map onto the
phases below: `cohort` (phases 1-2), `smoke`, `annotate` / `verify` / `audit`
(phases 4 and 7b), `pilot` (phase 6), `final` (phase 7) and `compare`
(phase 8). `./run_workflow.sh check` runs lint, type check and the offline test
suite; `./run_workflow.sh engineering` runs the whole engineering path in one
command and stops with an explicit message at any step that needs a human.

## Phase 1: preflight

Run the offline checks first:

```bash
python automated_scripts/preflight_study.py \
  --study-config configs/thesis_fresh_2026.yaml
```

The checks must confirm:

- Python version;
- valid study protocol structure;
- configured GitHub token;
- unused final output path;
- sufficient disk space;
- declared target equals the repository total.

Then perform the isolated one-log GitHub check:

```bash
python automated_scripts/preflight_study.py \
  --study-config configs/thesis_fresh_2026.yaml \
  --live
```

Expected outputs:

```text
data/studies/_preflight_thesis_fresh_2026/
├── sample_log.json
└── preflight_report.json
```

This smoke-test run ID is automatically excluded from the final cohort.

### Preflight gate

Do not start collection unless every offline check passes and the live check
downloads one complete log. `HTTP 401 Bad credentials` means the token in
`.env` must be replaced.

## Phase 2: collect and triage

The recommended command performs installation checks, preflight, collection
and triage in the controlled study mode:

```bash
./run_workflow.sh --skip-install
```

The workflow intentionally exits after triage. Annotation and model execution
remain explicit human-controlled phases.

To run the phases individually:

```bash
python automated_scripts/data_collection.py \
  --study-config configs/thesis_fresh_2026.yaml

python automated_scripts/triage.py \
  --study-config configs/thesis_fresh_2026.yaml
```

Expected study files:

```text
data/studies/thesis_fresh_2026/
├── study_protocol.yaml
├── collection_manifest.json
├── checksums/
│   └── log_content_sha256.json
├── raw/
│   └── logs.json
├── triaged/
│   └── eligible_logs.json
├── excluded/
│   └── excluded_logs.json
└── triage_manifest.json
```

### Collection gate

Inspect the collection manifest:

```bash
jq '{status, total_logs_collected, unique_repositories, collection_shortfalls, collection_errors}' \
  data/studies/thesis_fresh_2026/collection_manifest.json
```

Continue only when:

- the status is `complete`, or every warning is understood and documented;
- the raw count is plausible for the fixed protocol;
- all six repositories are represented, unless a shortfall is explicitly
  accepted before annotation;
- there are no unexplained authentication or download errors;
- the checksum file contains one entry per raw log.

### Triage gate

Inspect the eligible and excluded counts:

```bash
jq 'length' data/studies/thesis_fresh_2026/raw/logs.json
jq 'length' data/studies/thesis_fresh_2026/triaged/eligible_logs.json
jq 'group_by(.reason) | map({reason: .[0].reason, count: length})' \
  data/studies/thesis_fresh_2026/excluded/excluded_logs.json
```

Continue only when:

- every raw `log_id` appears exactly once in either eligible or excluded data;
- every exclusion has a recorded reason;
- approximately 50–70 eligible logs remain, or a deviation is justified;
- no repository dominates the cohort unexpectedly;
- the raw dataset remains unchanged.

## Recovery and reruns

Resume a genuinely interrupted collection:

```bash
./run_workflow.sh --from 2 --resume
```

Run only triage on an existing raw study:

```bash
./run_workflow.sh --from 3
```

The workflow preserves an existing triage result. Replace derived triage files
only when there is a documented methodological reason:

```bash
./run_workflow.sh --from 3 --overwrite-triage
```

Never overwrite a completed raw collection. A materially different collection
or selection protocol requires a new study identifier.

## Phase 3: freeze and back up the cohort

After the collection and triage gates pass:

1. Record the accepted raw and eligible counts.
2. Record any accepted repository shortfalls.
3. Copy the entire `data/studies/thesis_fresh_2026/` directory to a separate
   backed-up location.
4. Retain `collection_manifest.json`, `triage_manifest.json` and all checksum
   files with the backup.
5. Do not tune prompts, filters or selection rules against the final cohort.

The `data/studies/` directory is intentionally ignored by Git because it may
contain large public logs. Git is not the dataset backup.

## Phase 4: blind annotation

Run the blind annotation tool only after the cohort has been accepted and
backed up:

```bash
make annotate ANNOTATOR=your-stable-id
```

The tool:

- read `triaged/eligible_logs.json` directly;
- display the log and GitHub context without any model output;
- assign the approved failure category;
- record the actual root cause and supporting lines;
- checkpoint after every annotation;
- store annotator, timestamp and annotation-schema version;
- preserve the exact `log_id` values from the frozen cohort;
- write to `ground_truth/ground_truth.json`.

Do not run either model on the final cohort before this blind ground truth is
complete and validated.

### Annotation gate

Before the pilot, verify:

- annotation count equals eligible-log count;
- there are no duplicate or missing `log_id` values;
- every category is from the fixed taxonomy;
- every annotation contains an actual error type, root cause and evidence;
- ambiguous cases are flagged rather than silently guessed.

## Phase 5: model readiness

The paired experiment uses:

```text
Proprietary:  openai/gpt-5.6-terra
Open-weights: local/thesis-qwen3.5:9b-24k
Reasoning:    medium for both
```

The local model uses the `qwen3.5:9b` weights. Its tracked Modelfile fixes
Ollama's runtime context at 24,576 tokens so the shared 12,000-token filtered
input is not silently truncated by Ollama's 4K default on this machine.

Verify local availability:

```bash
ollama --version
make local-model
ollama show thesis-qwen3.5:9b-24k --verbose
```

The benchmark records the resolved model information, Ollama metadata, prompt
hash, input hash, schema, Git commit, token use, cost and run date.

## Phase 6: five-log paired pilot

After blind annotation and model readiness pass:

```bash
python automated_scripts/benchmark_models.py \
  --input data/studies/thesis_fresh_2026/triaged/eligible_logs.json \
  --ground-truth data/studies/thesis_fresh_2026/ground_truth/ground_truth.json \
  --pilot \
  --output-dir data/studies/system_smoke_001/experiments/pilot_002
```

### Pilot gate

Do not run the full cohort until:

- both models attempted the same five `log_id` values;
- all expected structured fields were parsed;
- evidence line numbers can be traced to the filtered log;
- failures and raw responses are preserved;
- model identities and Ollama digest/quantization are recorded;
- token, cost and execution-time metadata are populated;
- no prompt or schema change remains necessary.

If the prompt, schema, filtering behavior or reasoning configuration changes,
discard the pilot outputs and run a new numbered pilot.

## Phase 7: final paired experiment

Before any model call, the benchmark checks the input against every cohort that
declares itself exploratory (`exclude_from_future_held_out_evaluation: true` in
its manifest) and refuses to run if any case has already been used. This
enforces decision D4. A cohort never excludes its own cases, so the smoke run is
unaffected. To run anyway — never for thesis evidence — pass
`--allow-excluded-cases "reason"`; the reason is stored in `run_metadata.json`
under `partition_guard`.

After pilot approval, lock the configuration and run:

```bash
python automated_scripts/benchmark_models.py \
  --input data/studies/thesis_fresh_2026/triaged/eligible_logs.json \
  --ground-truth data/studies/thesis_fresh_2026/ground_truth/ground_truth.json \
  --output-dir data/studies/thesis_fresh_2026/experiments/final_001
```

Do not reuse the pilot directory. If a run is interrupted, reuse the same
final output directory so the benchmark can resume from its per-model
checkpoints.

Expected experiment artifacts include:

```text
run_metadata.json
results_openai_gpt-5.6-terra.json
results_local_thesis-qwen3.5_9b-24k.json
comparison_report.json
statistical_tests.json
cost_accuracy_tradeoff.png
```

## Phase 7b: verify and audit the ground truth

Kickoff decision D3 rules out the researcher's unaided judgement as the sole
basis for accuracy claims. Annotation therefore runs in two passes.

First pass, by the annotator:

```bash
make annotate-smoke ANNOTATOR=your-stable-id
```

Each case now also records the evidence that makes its label checkable:

| Evidence method | Required reference |
| --- | --- |
| `historical_fix` | fixing commit, pull request or issue URL |
| `seeded_defect` | defect-seed identifier (fork, branch or patch id) |
| `expert_review` | expert reasoning and the repository evidence relied on |
| `combined_adjudicated` | which sources were combined and how they were adjudicated |

Second pass, by a reviewer who is not the annotator:

```bash
make verify-smoke VERIFIER=second-reviewer-id
```

The verifier sees the numbered log and neither the model output nor the first
reviewer's answer. The script compares the two labels afterwards and requires a
written adjudication for every disagreement; the adjudicated values replace the
stored `actual_*` fields, and the raw agreement rate is reported so
inter-rater agreement can be quoted in the thesis.

Then check the file against the agreed requirements:

```bash
make audit-ground-truth
```

The audit reports a **blocking** finding for any case with no evidence method,
no independent verifier, an unusable root cause, an out-of-taxonomy category, or
an evidence method whose reference is missing. Ground truth with any blocking
finding must not be used for accuracy claims. The same verdict appears on the
comparison page and in its data notes.

## Phase 8: compare the generated reports

The benchmark writes one result file per condition. To read those conditions
against each other rather than one file at a time:

```bash
make compare                       # every experiment found under data/studies/
make compare-pilot                 # the pilot run only, plus a JSON export

python automated_scripts/compare_reports.py \
  --experiment data/studies/thesis_fresh_2026/experiments/final_001 \
  --open
```

Each invocation prints a terminal comparison and writes
`comparison_view.html` into the experiment directory: a self-contained page
with the model scoreboard, the side-by-side metric bars, the per-log outcome
matrix against blind ground truth, the four-way agreement split, the
ground-truth quality verdict, per-category precision/recall/F1 with macro F1,
evidence-line accuracy, per-condition confusion matrices, the significance tests
and the full diagnosis text from every condition.

Two metrics are easy to confuse and must be reported separately:

- **Grounding score** checks only that a line the model cited exists in the
  filtered log it was given. It never consults ground truth, so a model can
  score 100% while citing entirely the wrong lines.
- **Evidence-line accuracy** compares the model's `failure_lines` with the
  annotated supporting lines, and is the one that says whether the model found
  the right place in the log.

Passing several `--experiment` directories adds an across-runs section that
measures each model against its earliest run in that comparison. Runs use
different cohorts unless their input checksums match, so treat those deltas as
engineering signal, not as thesis evidence.

Every metric on the page is recomputed from the per-log
`results_<model>.json` files using the same definitions the benchmark applies,
so an interrupted run that never wrote its summary still compares correctly. A
missing or truncated report file is reported as a data note on the page instead
of failing the comparison.

Useful flags:

| Flag | Effect |
| --- | --- |
| `--experiment DIR` | Include one experiment; repeat for a cross-run comparison |
| `--list` | Show the experiments that were found, then exit |
| `--json PATH` | Also write the aligned comparison data as JSON |
| `--output PATH` | Write the page somewhere other than the experiment directory |
| `--no-html` | Terminal comparison only |
| `--open` | Open the page in the default browser |
| `--ground-truth PATH` | Override the annotations used for every experiment |

## Final verification checklist

- [ ] The study protocol was fixed before collection.
- [ ] The preflight sample is absent from the final cohort.
- [ ] Raw-log and configuration checksums are preserved.
- [ ] Exclusion reasons account for every removed log.
- [ ] The final cohort was annotated blind.
- [ ] Pilot and final experiments use separate directories.
- [ ] Both conditions use identical inputs, prompt, schema and reasoning level.
- [ ] Requested and resolved model identifiers are recorded.
- [ ] Every failed inference remains in the result files.
- [ ] Reported thesis values are generated from the preserved final outputs.
- [ ] The comparison page for the final run reports no data notes.
- [ ] `make audit-ground-truth` reports no blocking finding for the final cohort.
- [ ] Every final case is evidence-linked and verified by a second reviewer.
- [ ] The partition guard ran without an `--allow-excluded-cases` override.

The repository no longer contains the legacy API, RAG, human-study,
model-visible annotation or demonstration-evaluation paths. All supported
commands now operate on the controlled study design described here.
