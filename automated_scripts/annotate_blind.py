#!/usr/bin/env python3
"""Create ground truth without exposing either model's diagnosis.

Two modes implement the kickoff decisions on ground-truth validity:

``--mode annotate``
    The first reviewer reads the numbered log, records the failure category, a
    written root cause and the supporting lines, and links the case to the
    evidence that makes the label checkable (decision D3): a documented
    historical fix, a recorded seeded defect, or an expert judgement.

``--mode verify``
    A second reviewer, who must not be the annotator, labels the same case
    without seeing the first reviewer's answer. The script then compares the two
    and requires a written adjudication wherever they disagree (decision D3's
    independent verification).

Neither mode ever shows model output.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from automated_scripts.study_utils import atomic_write_json, load_study_config, study_directory
from src.evaluation.ground_truth_audit import EVIDENCE_METHODS, MIN_ROOT_CAUSE_CHARS, root_cause_problem

SCHEMA_VERSION = 2

ERROR_TYPES = [
    "dependency_error",
    "test_failure",
    "build_configuration",
    "timeout",
    "permission_denied",
    "syntax_error",
    "network_error",
    "unknown",
]

EVIDENCE_PROMPTS = {
    "historical_fix": (
        "fixing_reference",
        "Fixing commit, pull request or issue URL",
    ),
    "seeded_defect": (
        "seed_reference",
        "Defect-seed identifier (fork, branch or patch id)",
    ),
    "expert_review": (
        "evidence_notes",
        "Expert reasoning and the repository evidence relied on",
    ),
    "combined_adjudicated": (
        "evidence_notes",
        "Which evidence sources were combined and how they were adjudicated",
    ),
}


def parse_line_numbers(value: str) -> list[int]:
    """Parse comma-separated numbers and inclusive ranges such as 4,8-10."""
    numbers = set()
    for part in value.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            start_text, end_text = part.split("-", 1)
            start, end = int(start_text), int(end_text)
            if start < 1 or end < start:
                raise ValueError("Line ranges must be positive and ascending")
            numbers.update(range(start, end + 1))
        else:
            number = int(part)
            if number < 1:
                raise ValueError("Line numbers must be positive")
            numbers.add(number)
    return sorted(numbers)


def prompt_required(label: str) -> str:
    while True:
        value = input(f"{label}: ").strip()
        if value.lower() == "q":
            raise KeyboardInterrupt
        if value:
            return value
        print("A value is required. Enter q to save and quit.")


def prompt_root_cause(label: str = "Actual root cause") -> str:
    """Require a written cause, not the category digit typed one prompt late."""
    while True:
        value = prompt_required(label)
        problem = root_cause_problem(value)
        if problem is None:
            return value
        print(f"  That root cause {problem}.")
        print(f"  Describe what actually broke, in at least {MIN_ROOT_CAUSE_CHARS} characters.")


def prompt_failure_lines() -> list[int]:
    while True:
        try:
            lines = parse_line_numbers(prompt_required("Supporting lines, e.g. 12,18-20"))
            if lines:
                return lines
        except ValueError as exc:
            print(f"Invalid line list: {exc}")


def choose_from(options: list[str], label: str) -> str:
    for index, option in enumerate(options, 1):
        print(f"  {index}. {option}")
    while True:
        value = prompt_required(label)
        if value.isdigit() and 1 <= int(value) <= len(options):
            return options[int(value) - 1]
        if value in options:
            return value
        print("Choose a listed number or name.")


def choose_error_type() -> str:
    return choose_from(ERROR_TYPES, "Actual error type")


def collect_evidence() -> dict:
    """Link the case to the evidence that makes its label independently checkable."""
    print("\n  Evidence for this label (kickoff decision D3):")
    method = choose_from(list(EVIDENCE_METHODS), "Evidence method")
    field_name, prompt = EVIDENCE_PROMPTS[method]
    evidence = {"evidence_method": method, field_name: prompt_required(prompt)}
    if field_name != "evidence_notes":
        notes = input("Additional evidence notes (optional): ").strip()
        if notes:
            evidence["evidence_notes"] = notes
    return evidence


def write_review_log(root: Path, log: dict) -> Path:
    path = root / "ground_truth" / "review_logs" / f"{log['log_id']}.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for number, line in enumerate(log["log_content"].splitlines(), 1):
            handle.write(f"{number:07d}  {line}\n")
    return path


def present_case(root: Path, log: dict, index: int, total: int, mode: str) -> None:
    review_path = write_review_log(root, log)
    print("\n" + "=" * 72)
    print(f"Case {index}/{total}: {log['repository']} — {log.get('workflow_name', '')}")
    print(f"Run: {log.get('url', '')}")
    print(f"Numbered log: {review_path}")
    if mode == "verify":
        print("No model output and no previous annotation are shown. Label the case independently.")
    else:
        print("No model output is shown. Review the numbered log before answering.")


def save(output_path: Path, payload: dict, annotations: dict) -> None:
    payload["annotations"] = list(annotations.values())
    payload["updated_at"] = datetime.now(timezone.utc).isoformat()
    atomic_write_json(output_path, payload)


def parse_args():
    parser = argparse.ArgumentParser(description="Blindly annotate or independently verify the thesis cohort")
    parser.add_argument("--study-config", default="configs/thesis_fresh_2026.yaml")
    parser.add_argument("--study-dir", default=None)
    parser.add_argument(
        "--mode",
        choices=("annotate", "verify"),
        default="annotate",
        help="annotate: first blind labelling. verify: independent second review and adjudication.",
    )
    parser.add_argument("--annotator", required=True, help="Stable reviewer identifier, not a secret")
    return parser.parse_args()


def run_annotate(logs: list[dict], root: Path, output_path: Path, payload: dict, annotator: str) -> int:
    annotations = {item["log_id"]: item for item in payload.get("annotations", [])}
    for index, log in enumerate(logs, 1):
        if log["log_id"] in annotations:
            continue
        present_case(root, log, index, len(logs), "annotate")
        try:
            error_type = choose_error_type()
            root_cause = prompt_root_cause()
            failure_lines = prompt_failure_lines()
            evidence = collect_evidence()
            notes = input("Notes or ambiguity flag (optional): ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nSaving annotation progress.")
            save(output_path, payload, annotations)
            return 0

        record = {
            "log_id": log["log_id"],
            "repository": log["repository"],
            "workflow_name": log.get("workflow_name", ""),
            "run_id": log.get("run_id"),
            "url": log.get("url", ""),
            "log_sha256": log.get("log_sha256", ""),
            "actual_error_type": error_type,
            "actual_root_cause": root_cause,
            "failure_lines": failure_lines,
            "notes": notes,
            "annotator": annotator,
            "annotated_at": datetime.now(timezone.utc).isoformat(),
        }
        record.update(evidence)
        annotations[log["log_id"]] = record
        save(output_path, payload, annotations)
        print(f"Saved {len(annotations)}/{len(logs)} annotations.")

    print(f"Blind annotation complete: {len(annotations)} cases in {output_path}")
    print("Run --mode verify with a different reviewer before using this file for accuracy claims.")
    return 0


def run_verify(logs: list[dict], root: Path, output_path: Path, payload: dict, verifier: str) -> int:
    """Second blind pass: label independently, then adjudicate any disagreement."""
    annotations = {item["log_id"]: item for item in payload.get("annotations", [])}
    pending = [log for log in logs if log["log_id"] in annotations and not annotations[log["log_id"]].get("verifier")]
    if not pending:
        print("Every annotated case already has an independent verification.")
        return 0

    for index, log in enumerate(pending, 1):
        record = annotations[log["log_id"]]
        if record.get("annotator") == verifier:
            print(f"\nSkipping {log['log_id']}: you annotated this case, so you cannot verify it.")
            continue
        present_case(root, log, index, len(pending), "verify")
        try:
            error_type = choose_error_type()
            root_cause = prompt_root_cause("Your root cause")
            failure_lines = prompt_failure_lines()
        except (KeyboardInterrupt, EOFError):
            print("\nSaving verification progress.")
            save(output_path, payload, annotations)
            return 0

        agreed = error_type == record.get("actual_error_type")
        print("\n  First reviewer recorded:")
        print(f"    category   : {record.get('actual_error_type')}")
        print(f"    root cause : {record.get('actual_root_cause')}")
        print(f"    lines      : {record.get('failure_lines')}")
        print(f"  You recorded category: {error_type}")

        adjudication = ""
        try:
            if agreed:
                print("  Categories agree.")
            else:
                print("  Categories DISAGREE. An adjudicated decision is required.")
                adjudication = prompt_required("Adjudicated decision and reasoning")
                final_type = choose_from(ERROR_TYPES, "Adjudicated error type")
                record["actual_error_type"] = final_type
                record["actual_root_cause"] = prompt_root_cause("Adjudicated root cause")
                record["failure_lines"] = prompt_failure_lines()
        except (KeyboardInterrupt, EOFError):
            print("\nSaving verification progress.")
            save(output_path, payload, annotations)
            return 0

        record.update(
            {
                "verifier": verifier,
                "verifier_error_type": error_type,
                "verifier_root_cause": root_cause,
                "verifier_failure_lines": failure_lines,
                "agreement": "agree" if agreed else "disagree",
                "adjudication": adjudication,
                "verified_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        save(output_path, payload, annotations)
        verified = sum(1 for item in annotations.values() if item.get("verifier"))
        print(f"Saved {verified}/{len(annotations)} verifications.")

    verified = sum(1 for item in annotations.values() if item.get("verifier"))
    agreements = sum(1 for item in annotations.values() if item.get("agreement") == "agree")
    print(f"\nIndependent verification: {verified}/{len(annotations)} cases")
    if verified:
        print(f"Raw category agreement before adjudication: {agreements}/{verified}")
    return 0


def main() -> int:
    args = parse_args()
    config, _ = load_study_config(args.study_config)
    root = study_directory(config, args.study_dir)
    input_path = root / "triaged" / "eligible_logs.json"
    output_path = root / "ground_truth" / "ground_truth.json"
    if not input_path.exists():
        print(f"ERROR: Eligible cohort does not exist: {input_path}")
        return 1

    logs = json.loads(input_path.read_text(encoding="utf-8"))
    if output_path.exists():
        payload = json.loads(output_path.read_text(encoding="utf-8"))
    elif args.mode == "verify":
        print(f"ERROR: Nothing to verify; no ground truth at {output_path}")
        return 1
    else:
        payload = {
            "schema_version": SCHEMA_VERSION,
            "study_id": config["study_id"],
            "annotation_method": "blind_human_review_with_evidence",
            "annotator": args.annotator,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "annotations": [],
        }
    if args.mode == "annotate" and payload.get("annotator") != args.annotator:
        print("ERROR: Existing ground truth belongs to a different annotator identifier.")
        return 1
    if args.mode == "verify" and payload.get("annotator") == args.annotator:
        print("ERROR: The verifier must not be the annotator who created this ground truth.")
        return 1
    if payload.get("study_id") != config["study_id"]:
        print("ERROR: Existing ground truth belongs to a different study.")
        return 1

    annotation_items = payload.get("annotations", [])
    annotation_ids = [item.get("log_id") for item in annotation_items]
    if len(annotation_ids) != len(set(annotation_ids)):
        print("ERROR: Existing ground truth contains duplicate log IDs.")
        return 1

    cohort_ids = {log["log_id"] for log in logs}
    if set(annotation_ids) - cohort_ids:
        print("ERROR: Existing ground truth contains cases outside this cohort.")
        return 1

    if args.mode == "verify":
        payload["verifier"] = args.annotator
        return run_verify(logs, root, output_path, payload, args.annotator)
    return run_annotate(logs, root, output_path, payload, args.annotator)


if __name__ == "__main__":
    raise SystemExit(main())
