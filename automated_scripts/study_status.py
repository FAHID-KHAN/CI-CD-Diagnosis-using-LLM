#!/usr/bin/env python3
"""Report the state of every study stage from the files on disk.

Nothing here trusts a log line or a remembered command: each stage is judged by
the artefacts it is supposed to have left behind, so an interrupted or partial
run is visible rather than assumed complete. The exit code is non-zero when a
stage that should be finished is not, which makes this usable as a gate in
``run_workflow.sh`` as well as a thing to read.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from automated_scripts.study_utils import load_study_config, study_directory
from src.evaluation.case_partitions import find_overlap, load_exclusions
from src.evaluation.ground_truth_audit import audit_ground_truth_file
from src.evaluation.report_comparison import load_experiment

DONE = "done"
PARTIAL = "partial"
TODO = "todo"
BLOCKED = "blocked"

MARKS = {DONE: "[x]", PARTIAL: "[~]", TODO: "[ ]", BLOCKED: "[!]"}

# A stage that is merely unstarted is not a failure; a stage that is started and
# broken, or that blocks the held-out run, is.
FAILING = (BLOCKED,)


class Stage:
    def __init__(self, name: str, state: str, detail: str = "", notes=None):
        self.name = name
        self.state = state
        self.detail = detail
        self.notes = notes or []

    def to_dict(self) -> dict:
        return {"name": self.name, "state": self.state, "detail": self.detail, "notes": self.notes}


def read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None


def count_list(path: Path):
    data = read_json(path)
    return len(data) if isinstance(data, list) else None


def stage_protocol(root: Path, config: dict) -> Stage:
    protocol = root / "study_protocol.yaml"
    repositories = config.get("repositories", [])
    detail = f"{len(repositories)} repositories, study_id={config.get('study_id')}"
    if not protocol.exists():
        return Stage("Study protocol frozen", TODO, detail)
    return Stage("Study protocol frozen", DONE, detail)


def stage_preflight(root: Path, config: dict) -> Stage:
    report = root.parent / f"_preflight_{config['study_id']}" / "preflight_report.json"
    data = read_json(report)
    if data is None:
        return Stage("Preflight", TODO, "no preflight report")
    checks = data.get("checks", {})
    failed = [name for name, ok in checks.items() if ok is False] if isinstance(checks, dict) else []
    if failed:
        return Stage("Preflight", BLOCKED, f"failed checks: {', '.join(failed)}")
    return Stage("Preflight", DONE, f"sample log from {data.get('repository', '?')}")


def stage_collection(root: Path) -> Stage:
    manifest = read_json(root / "collection_manifest.json")
    raw_count = count_list(root / "raw" / "logs.json")
    if manifest is None and raw_count is None:
        return Stage("Collection", TODO, "no raw logs")
    if manifest is None:
        return Stage("Collection", PARTIAL, f"{raw_count} raw logs but no manifest")
    status = manifest.get("status")
    errors = manifest.get("collection_errors") or []
    detail = f"{raw_count} raw logs from {len(manifest.get('repositories', []))} repositories"
    notes = [f"{len(errors)} collection error(s) recorded"] if errors else []
    if status != "complete":
        return Stage("Collection", PARTIAL, f"{detail}; status={status}", notes)
    return Stage("Collection", DONE, detail, notes)


def stage_triage(root: Path) -> Stage:
    manifest = read_json(root / "triage_manifest.json")
    eligible = count_list(root / "triaged" / "eligible_logs.json")
    excluded = count_list(root / "excluded" / "excluded_logs.json")
    if manifest is None or eligible is None:
        return Stage("Triage", TODO, "no eligible cohort")
    notes = []
    target = manifest.get("eligible_target") or {}
    minimum = target.get("minimum")
    if isinstance(minimum, int) and isinstance(eligible, int) and eligible < minimum:
        notes.append(f"below the configured minimum of {minimum} eligible logs")
    return Stage("Triage", DONE, f"{eligible} eligible, {excluded or 0} excluded with reasons", notes)


def stage_ground_truth(root: Path) -> Stage:
    cohort = count_list(root / "triaged" / "eligible_logs.json")
    path = root / "ground_truth" / "ground_truth.json"
    if not path.exists():
        return Stage("Ground truth", TODO, f"0 of {cohort or '?'} cases annotated")
    audit = audit_ground_truth_file(str(path))
    detail = f"{audit.case_count} of {cohort or '?'} annotated, " f"{audit.verified_cases} independently verified"
    notes = [line for line in audit.summary_lines()]
    if audit.is_defensible and cohort and audit.case_count >= cohort:
        return Stage("Ground truth", DONE, detail, notes)
    if audit.blocking:
        return Stage("Ground truth", BLOCKED, detail, notes)
    return Stage("Ground truth", PARTIAL, detail, notes)


def stage_derived_cohort(root: Path, manifest: dict) -> Stage:
    """A cohort selected from another study's cohort rather than collected."""
    cases = count_list(root / "triaged" / "eligible_logs.json")
    selection = manifest.get("selection", {})
    source = manifest.get("source", {})
    detail = (
        f"{cases or 0} cases selected from {Path(source.get('file', '?')).name} "
        f"by {selection.get('method', '?')} (seed {selection.get('seed', '?')})"
    )
    notes = []
    if manifest.get("exclude_from_future_held_out_evaluation"):
        notes.append("declared exploratory; excluded from the held-out evaluation by its manifest")
    if not manifest.get("usable_as_final_thesis_evidence", True):
        notes.append("not usable as final thesis evidence")
    return Stage("Derived cohort", DONE, detail, notes)


def stage_experiments(root: Path, studies_root: Path) -> list:
    stages = []
    experiments_dir = root / "experiments"
    if not experiments_dir.is_dir():
        return [Stage("Experiments", TODO, "no experiment directories")]
    for path in sorted(p for p in experiments_dir.iterdir() if p.is_dir()):
        report = load_experiment(str(path))
        if not report.model_labels:
            stages.append(Stage(f"Experiment {path.name}", PARTIAL, "no readable result files"))
            continue
        completion = [
            f"{label}: {report.metrics[label].get('successful_logs', 0)}"
            f"/{report.metrics[label].get('total_logs', 0)}"
            for label in report.model_labels
        ]
        issues = [issue for issue in report.issues if not issue.startswith("Ground truth ")]
        state = DONE if not issues else PARTIAL
        stages.append(Stage(f"Experiment {path.name}", state, "; ".join(completion), issues))
    return stages or [Stage("Experiments", TODO, "no experiment directories")]


def stage_partitions(root: Path, studies_root: Path) -> Stage:
    """Would a held-out run over this cohort reuse an exploratory case?"""
    cohort_path = root / "triaged" / "eligible_logs.json"
    logs = read_json(cohort_path)
    if not isinstance(logs, list):
        return Stage("Held-out separation", TODO, "no cohort to check")
    excluded, problems = load_exclusions(str(studies_root), str(cohort_path))
    overlap = find_overlap(logs, excluded)
    if overlap:
        cohorts = sorted({hit.cohort_id for hit in overlap})
        return Stage(
            "Held-out separation",
            BLOCKED,
            f"{len(overlap)} case(s) already used by {', '.join(cohorts)}",
            problems + [f"{hit.case_id} (from {hit.cohort_id})" for hit in overlap[:10]],
        )
    return Stage("Held-out separation", DONE, f"no overlap with {len(excluded)} exploratory case(s)", problems)


def collect_stages(config: dict, root: Path, studies_root: Path) -> list:
    derived = read_json(root / "smoke_manifest.json")
    if isinstance(derived, dict):
        stages = [stage_derived_cohort(root, derived), stage_ground_truth(root)]
    else:
        stages = [
            stage_protocol(root, config),
            stage_preflight(root, config),
            stage_collection(root),
            stage_triage(root),
            stage_ground_truth(root),
            stage_partitions(root, studies_root),
        ]
    stages.extend(stage_experiments(root, studies_root))
    return stages


def next_action(stages: list) -> str:
    """The single most useful next command, given where the study actually is."""
    by_name = {stage.name: stage for stage in stages}
    if "Collection" not in by_name:
        ground_truth = by_name["Ground truth"]
        if ground_truth.state != DONE:
            return "./run_workflow.sh annotate-smoke ANNOTATOR=<your-id>"
        if not any(stage.name.startswith("Experiment ") for stage in stages):
            return "./run_workflow.sh pilot"
        return "./run_workflow.sh compare"
    if by_name["Collection"].state in (TODO, PARTIAL):
        return "./run_workflow.sh cohort"
    if by_name["Triage"].state in (TODO, PARTIAL):
        return "./run_workflow.sh cohort --from 3"
    ground_truth = by_name["Ground truth"]
    if ground_truth.state == TODO:
        return "./run_workflow.sh annotate ANNOTATOR=<your-id>"
    if ground_truth.state in (PARTIAL, BLOCKED):
        if any("no_independent_verification" in note or "single_annotator" in note for note in ground_truth.notes):
            return "./run_workflow.sh verify VERIFIER=<second-reviewer-id>"
        return "./run_workflow.sh annotate ANNOTATOR=<your-id>"
    if by_name["Held-out separation"].state == BLOCKED:
        return "Build a final cohort that excludes the exploratory cases before running the held-out experiment."
    if not any(stage.name.startswith("Experiment ") for stage in stages):
        return "./run_workflow.sh pilot"
    return "./run_workflow.sh compare"


def print_report(study_id: str, root: Path, stages: list) -> None:
    print()
    print("=" * 78)
    print(f"  STUDY STATUS — {study_id}")
    print("=" * 78)
    print(f"  {root}")
    print()
    for stage in stages:
        print(f"  {MARKS[stage.state]} {stage.name:<26} {stage.detail}")
        for note in stage.notes:
            print(f"        - {note}")
    print()
    print("  Legend: [x] done   [~] partial   [ ] not started   [!] blocking")
    print()
    print(f"  Next: {next_action(stages)}")
    print()


def parse_args():
    parser = argparse.ArgumentParser(description="Report the state of every study stage")
    parser.add_argument("--study-config", default="configs/thesis_fresh_2026.yaml")
    parser.add_argument("--study-dir", default=None)
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    parser.add_argument(
        "--require",
        action="append",
        default=[],
        metavar="STAGE",
        help="Exit non-zero unless this stage is done; repeatable (substring match)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config, _ = load_study_config(args.study_config)
    root = study_directory(config, args.study_dir)
    studies_root = root.parent
    stages = collect_stages(config, root, studies_root)
    # With --study-dir the directory, not the base config, names the study.
    study_id = root.name if args.study_dir else config["study_id"]

    if args.json:
        print(
            json.dumps(
                {
                    "study_id": config["study_id"],
                    "root": str(root),
                    "stages": [stage.to_dict() for stage in stages],
                    "next": next_action(stages),
                },
                indent=2,
            )
        )
    else:
        print_report(study_id, root, stages)

    # Every unmet requirement is reported, not just the first, so one run of the
    # gate tells you everything that needs fixing.
    failed = False
    for requirement in args.require:
        matched = [stage for stage in stages if requirement.lower() in stage.name.lower()]
        if not matched:
            print(f"ERROR: No stage matches {requirement!r}.")
            failed = True
            continue
        for stage in (item for item in matched if item.state != DONE):
            print(f"ERROR: {stage.name} is {stage.state}: {stage.detail}")
            failed = True
    if failed:
        return 1

    return 1 if any(stage.state in FAILING for stage in stages) else 0


if __name__ == "__main__":
    raise SystemExit(main())
