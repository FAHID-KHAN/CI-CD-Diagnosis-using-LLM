#!/usr/bin/env python3
"""Create ground truth without exposing either model's diagnosis."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from automated_scripts.study_utils import atomic_write_json, load_study_config, study_directory

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


def choose_error_type() -> str:
    for index, error_type in enumerate(ERROR_TYPES, 1):
        print(f"  {index}. {error_type}")
    while True:
        value = prompt_required("Actual error type")
        if value.isdigit() and 1 <= int(value) <= len(ERROR_TYPES):
            return ERROR_TYPES[int(value) - 1]
        if value in ERROR_TYPES:
            return value
        print("Choose a listed number or category name.")


def write_review_log(root: Path, log: dict) -> Path:
    path = root / "ground_truth" / "review_logs" / f"{log['log_id']}.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for number, line in enumerate(log["log_content"].splitlines(), 1):
            handle.write(f"{number:07d}  {line}\n")
    return path


def parse_args():
    parser = argparse.ArgumentParser(description="Blindly annotate the controlled thesis cohort")
    parser.add_argument("--study-config", default="configs/thesis_fresh_2026.yaml")
    parser.add_argument("--study-dir", default=None)
    parser.add_argument("--annotator", required=True, help="Stable annotator identifier, not a secret")
    return parser.parse_args()


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
    else:
        payload = {
            "schema_version": 1,
            "study_id": config["study_id"],
            "annotation_method": "blind_human_review",
            "annotator": args.annotator,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "annotations": [],
        }
    if payload.get("annotator") != args.annotator:
        print("ERROR: Existing ground truth belongs to a different annotator identifier.")
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
    unexpected_ids = set(annotation_ids) - cohort_ids
    if unexpected_ids:
        print("ERROR: Existing ground truth contains cases outside this cohort.")
        return 1

    annotations = {item["log_id"]: item for item in annotation_items}
    for index, log in enumerate(logs, 1):
        if log["log_id"] in annotations:
            continue
        review_path = write_review_log(root, log)
        print("\n" + "=" * 72)
        print(f"Case {index}/{len(logs)}: {log['repository']} — {log.get('workflow_name', '')}")
        print(f"Run: {log.get('url', '')}")
        print(f"Numbered log: {review_path}")
        print("No model output is shown. Review the numbered log before answering.")
        try:
            error_type = choose_error_type()
            root_cause = prompt_required("Actual root cause")
            while True:
                try:
                    failure_lines = parse_line_numbers(prompt_required("Supporting lines, e.g. 12,18-20"))
                    if failure_lines:
                        break
                except ValueError as exc:
                    print(f"Invalid line list: {exc}")
            notes = input("Notes or ambiguity flag (optional): ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nSaving annotation progress.")
            payload["annotations"] = list(annotations.values())
            payload["updated_at"] = datetime.now(timezone.utc).isoformat()
            atomic_write_json(output_path, payload)
            return 0

        annotations[log["log_id"]] = {
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
            "annotator": args.annotator,
            "annotated_at": datetime.now(timezone.utc).isoformat(),
        }
        payload["annotations"] = list(annotations.values())
        payload["updated_at"] = datetime.now(timezone.utc).isoformat()
        atomic_write_json(output_path, payload)
        print(f"Saved {len(annotations)}/{len(logs)} annotations.")

    print(f"Blind annotation complete: {len(annotations)} cases in {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
