# Tools

Standalone utilities. Nothing in the study pipeline calls these, and the tool
runs without them. They are used occasionally, by hand, when setting up or
changing a study.

Everything in `automated_scripts/` is the opposite: the pipeline invokes it, and
removing any of it breaks `run_workflow.sh`.

## `scout_repositories.py`

Measures candidate repositories before you commit a study to them: how many real
(non-bot) failed runs exist, how long their logs are, and what share of a log
survives filtering.

```bash
python tools/scout_repositories.py --samples 5 --max-lines 1000 \
    django/django gradle/gradle prettier/prettier
```

Use it when choosing the repository pair. Selection is on log tractability and
ecosystem contrast only — never on how well a model scores.

## `carry_over_annotations.py`

Moves blind annotations into a new cohort when the log content is byte-identical,
matched on `log_sha256`. Use it when a study's repository pair changes and you do
not want to re-annotate cases you have already read.

```bash
python tools/carry_over_annotations.py \
    --study-config configs/thesis_pair_2026.yaml \
    --from-annotations path/to/previous/ground_truth.json --dry-run
```

Always dry-run first. An annotation is carried over only on an exact content
match, so a re-collected run whose log changed is left for fresh annotation.
