#!/usr/bin/env python3
"""Carry blind annotations into a new cohort when the log content is identical.

Changing a study's repository pair means re-collecting, and a repository that
survives the change usually returns the same failed runs. Re-annotating those is
wasted effort, and it is not even blind a second time -- the reviewer has
already read the log.

An annotation is carried over only when the new cohort contains a case whose
``log_sha256`` is byte-identical to the one that was annotated. Anything else is
left for fresh annotation. Each carried record keeps a note of where it came
from, so the provenance of every label stays visible.
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


def parse_args():
    parser = argparse.ArgumentParser(description="Carry annotations into a new cohort by log checksum")
    parser.add_argument("--study-config", default="configs/thesis_pair_2026.yaml")
    parser.add_argument("--study-dir", default=None)
    parser.add_argument("--from-annotations", required=True, help="Ground-truth JSON from the previous cohort")
    parser.add_argument("--dry-run", action="store_true", help="Report what would carry over, write nothing")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config, _ = load_study_config(args.study_config)
    root = study_directory(config, args.study_dir)
    cohort_path = root / "triaged" / "eligible_logs.json"
    output_path = root / "ground_truth" / "ground_truth.json"

    if not cohort_path.exists():
        print(f"ERROR: Eligible cohort does not exist: {cohort_path}")
        return 1
    source = Path(args.from_annotations).expanduser().resolve()
    if not source.exists():
        print(f"ERROR: Source annotations do not exist: {source}")
        return 1

    cohort = json.loads(cohort_path.read_text(encoding="utf-8"))
    payload = json.loads(source.read_text(encoding="utf-8"))
    incoming = payload.get("annotations", []) if isinstance(payload, dict) else payload

    # Match on content, never on run id: a re-collected run keeps its id even if
    # the log was regenerated, and only identical content justifies reusing a label.
    by_checksum = {case["log_sha256"]: case for case in cohort if case.get("log_sha256")}

    existing = {}
    if output_path.exists():
        current = json.loads(output_path.read_text(encoding="utf-8"))
        existing = {item["log_id"]: item for item in current.get("annotations", [])}
    else:
        current = {
            "schema_version": payload.get("schema_version", 2),
            "study_id": config["study_id"],
            "annotation_method": payload.get("annotation_method", "blind_human_review_with_evidence"),
            "annotator": payload.get("annotator"),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "annotations": [],
        }

    carried, skipped = [], []
    for record in incoming:
        checksum = record.get("log_sha256")
        case = by_checksum.get(checksum) if checksum else None
        if case is None:
            skipped.append((record.get("log_id"), "no case in the new cohort has this log content"))
            continue
        if case["log_id"] in existing:
            skipped.append((record.get("log_id"), "already annotated in the new cohort"))
            continue
        moved = dict(record)
        moved["log_id"] = case["log_id"]
        moved["repository"] = case.get("repository", record.get("repository", ""))
        moved["workflow_name"] = case.get("workflow_name", record.get("workflow_name", ""))
        moved["run_id"] = case.get("run_id", record.get("run_id"))
        moved["url"] = case.get("url", record.get("url", ""))
        moved["carried_over"] = {
            "from_study": payload.get("study_id") if isinstance(payload, dict) else None,
            "from_log_id": record.get("log_id"),
            "matched_on": "log_sha256",
            "carried_at": datetime.now(timezone.utc).isoformat(),
        }
        existing[case["log_id"]] = moved
        carried.append(case["log_id"])

    print(f"Cohort cases            : {len(cohort)}")
    print(f"Annotations offered     : {len(incoming)}")
    print(f"Carried over            : {len(carried)}")
    for log_id in carried:
        print(f"    + {log_id}")
    if skipped:
        print(f"Not carried             : {len(skipped)}")
        for log_id, reason in skipped:
            print(f"    - {log_id}: {reason}")
    remaining = len(cohort) - len(existing)
    print(f"Still to annotate       : {remaining}")

    if args.dry_run:
        print("\nDry run; nothing was written.")
        return 0

    current["annotations"] = list(existing.values())
    current["updated_at"] = datetime.now(timezone.utc).isoformat()
    atomic_write_json(output_path, current)
    print(f"\nWrote {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
