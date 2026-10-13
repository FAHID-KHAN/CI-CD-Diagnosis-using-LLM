# How to run this

Every command in the order you would actually use them. No methodology here —
see [the runbook](CONTROLLED_STUDY_RUNBOOK.md) for why each step exists.

One rule worth knowing up front: **activate the virtual environment first.**

```bash
source .venv/bin/activate
```

Most commands go through one entry point:

```bash
./run_workflow.sh <command> [options]
./run_workflow.sh --help          # every command
```

---

## Where am I?

Run this any time. It reads the files on disk and tells you what is done, what
is missing and what to do next.

```bash
./run_workflow.sh status --study-config configs/thesis_pair_2026.yaml
```

`[x]` done · `[~]` partial · `[ ]` not started · `[!]` blocking

---

## First time only

```bash
python3.12 -m venv .venv
source .venv/bin/activate
make install
make local-model          # pulls qwen3.5:9b and builds the thesis model
cp .env.template .env     # then add GITHUB_TOKEN and OPENAI_API_KEY
```

Check the code is healthy at any point:

```bash
./run_workflow.sh check   # lint, type check, and the full offline test suite
```

---

## The main sequence

### 1. Collect and triage

```bash
./run_workflow.sh cohort --study-config configs/thesis_pair_2026.yaml --skip-install
```

Runs preflight, downloads the logs, records the failing job for each run, then
triages. Prints a count for every exclusion reason and a family report.

Takes a while — it downloads up to 200 logs.

### 2. Split into development, pilot and held-out

```bash
./run_workflow.sh split --study-config configs/thesis_pair_2026.yaml
```

Preview without writing anything:

```bash
python automated_scripts/make_split.py --study-config configs/thesis_pair_2026.yaml --dry-run
```

Once written, the split is fixed. Changing it needs
`--overwrite --reason "<why>"`.

### 3. Annotate

```bash
./run_workflow.sh annotate ANNOTATOR=your-id --study-config configs/thesis_pair_2026.yaml
```

One case at a time. Saves after every case, so `q` quits and you resume later.

Revisit only the cases the audit flags:

```bash
./run_workflow.sh recheck ANNOTATOR=your-id --study-config configs/thesis_pair_2026.yaml
```

Second reviewer, if you have one:

```bash
./run_workflow.sh verify VERIFIER=their-id --study-config configs/thesis_pair_2026.yaml
```

### 4. Check the ground truth is usable

```bash
./run_workflow.sh audit
```

Says `defensible` or `NOT defensible`, with the reason per case.

### 5. Controlled defects

```bash
./run_workflow.sh defects ACTION=add      # record one
./run_workflow.sh defects ACTION=audit    # what is recorded, what is missing
./run_workflow.sh defects ACTION=commit   # hash-commit the held-out ones
```

Capped at two per category and sixteen overall.

### 6. Run the models

Engineering rehearsal on the five-case smoke cohort:

```bash
./run_workflow.sh engineering
```

The real held-out run — refuses unless every gate passes:

```bash
./run_workflow.sh final --study-config configs/thesis_pair_2026.yaml
```

### 7. Score the root causes

```bash
./run_workflow.sh score SCORER=your-id EXPERIMENT=data/studies/thesis_pair_2026/experiments/final_001
```

The model behind each response is hidden and the order is shuffled.

### 8. Compare

```bash
./run_workflow.sh compare
```

Prints a table and writes `comparison_view.html` into the experiment directory.
Open that file in a browser.

---

## Before the held-out run

```bash
./run_workflow.sh freeze ACTION=create --study-config configs/thesis_pair_2026.yaml
./run_workflow.sh freeze ACTION=verify --study-config configs/thesis_pair_2026.yaml
```

`create` records the commit, prompt, schema, decoding parameters, preprocessing
rules, baseline ruleset, split, and ground-truth checksums. It refuses if the
worktree is dirty or the dataset is incomplete.

`verify` re-checks everything and exits non-zero if anything moved. `final` runs
this automatically.

---

## Choosing repositories

```bash
python tools/check_repository_gate.py gradle/gradle --inspect 30
python tools/scout_repositories.py --samples 5 django/django gradle/gradle
```

The gate reports evidence — log availability, job scope, repair linkage, family
counts — and deliberately does not emit a pass or fail.

---

## Housekeeping

```bash
./clean.sh                # caches and build artefacts
./clean.sh --dry-run      # show what would go
./clean.sh --studies      # also clear study data, after typing 'delete'
make architecture         # regenerate the architecture diagram
```

---

## When something goes wrong

| Symptom | Cause |
| --- | --- |
| `Virtual environment missing` | Run `source .venv/bin/activate` |
| `Study output already exists` | Study directories are immutable. Use a new `study_id` in a new config |
| `Eligible cohort size N is outside the fixed range` | Collection yielded more or fewer cases than the config expects. Adjust `target_eligible_logs`, or collect more |
| `Output directory belongs to another run` | The experiment directory was made by a different input or ground truth. Use a fresh directory |
| `case(s) in this input were already used by an exploratory cohort` | Held-out leakage guard. Build a cohort that excludes them |
| `The system no longer matches its freeze record` | Something changed after the freeze. Run `freeze ACTION=verify` to see what |
| `make: python: No such file or directory` | The virtual environment is not active |

---

## Everything else

`make help` lists the Makefile targets, which mirror the commands above.
