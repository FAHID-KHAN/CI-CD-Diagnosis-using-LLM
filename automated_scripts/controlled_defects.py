#!/usr/bin/env python3
"""Record controlled defects: known interventions with a known expected cause.

A controlled defect is a change made deliberately so that the correct diagnosis
is known in advance rather than inferred from a log. That makes it the only
case type whose ground truth needs no interpretation -- and also the reason it
must be reported separately, because seeded faults do not occur at the
frequency real ones do.

Every record captures what the evaluation plan requires: the injection
procedure, the intended cause, the affected component, the expected evidence,
the repair, and whether the failure actually reproduced. A defect missing any of
these is not usable, because without them nobody can check that the intervention
did what it was meant to do.

Defects reserved for the held-out set are hash-committed before any prompt,
filter or threshold tuning, so that a later change cannot be fitted to them.

    python automated_scripts/controlled_defects.py add --study-dir <dir>
    python automated_scripts/controlled_defects.py audit --study-dir <dir>
    python automated_scripts/controlled_defects.py commit --study-dir <dir> --partition held_out
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import List

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from automated_scripts.study_utils import atomic_write_json, git_commit
from src.evaluation.taxonomy import ERROR_TYPE_ORDER

MANIFEST = "controlled_defects.json"

# Caps agreed with the supervisors. Enforced here rather than trusted to
# discipline, because the cap is what keeps semi-synthetic cases a supplement
# rather than a substitute for real failures.
MAX_PER_CATEGORY = 2
MAX_TOTAL = 16

# Every field the plan requires. A record missing any of them cannot be used.
REQUIRED_FIELDS = (
    ("defect_id", "Short stable identifier, e.g. seed-timeout-01"),
    ("category", "Intended failure category"),
    ("repository", "Repository or fork the defect is injected into"),
    ("injection_procedure", "Exactly what was changed, so another person could repeat it"),
    ("intended_cause", "The root cause a correct diagnosis should identify"),
    ("affected_component", "The component the defect breaks"),
    ("expected_evidence", "What should appear in the log if the injection worked"),
    ("repair", "The change that restores the build"),
)


def load(path: Path) -> dict:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"schema_version": 1, "created_at": datetime.now(timezone.utc).isoformat(), "defects": []}


def record_problems(record: dict) -> List[str]:
    """Why this record cannot be used, or an empty list if it can."""
    problems = []
    for field, description in REQUIRED_FIELDS:
        value = record.get(field)
        if not isinstance(value, str) or not value.strip():
            problems.append(f"{field} is missing ({description.lower()})")
    category = record.get("category")
    if category and category not in ERROR_TYPE_ORDER:
        problems.append(f"category {category!r} is not in the taxonomy")
    if record.get("reproduced") is None:
        problems.append("reproduced is not recorded; an unverified injection proves nothing")
    elif record.get("reproduced") is False:
        problems.append("the failure did not reproduce, so the intended cause is unconfirmed")
    return problems


def audit(manifest: dict) -> dict:
    defects = manifest.get("defects", [])
    per_category = collections.Counter(record.get("category", "?") for record in defects)
    findings = []
    for record in defects:
        for problem in record_problems(record):
            findings.append({"defect_id": record.get("defect_id", "?"), "problem": problem})
    over_cap = [name for name, count in per_category.items() if count > MAX_PER_CATEGORY]
    if over_cap:
        findings.append(
            {"defect_id": "-", "problem": f"more than {MAX_PER_CATEGORY} defects in: {', '.join(over_cap)}"}
        )
    if len(defects) > MAX_TOTAL:
        findings.append({"defect_id": "-", "problem": f"{len(defects)} defects exceeds the cap of {MAX_TOTAL}"})
    return {
        "total": len(defects),
        "per_category": dict(per_category),
        "categories_covered": sorted(per_category),
        "categories_missing": [name for name in ERROR_TYPE_ORDER if name not in per_category],
        "usable": len(defects) - len({finding["defect_id"] for finding in findings if finding["defect_id"] != "-"}),
        "findings": findings,
    }


def defect_hash(record: dict) -> str:
    """Hash the fields that define the intervention, not its bookkeeping."""
    payload = {field: record.get(field, "") for field, _ in REQUIRED_FIELDS}
    payload["reproduced"] = record.get("reproduced")
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def prompt_record() -> dict:
    print("\nRecording a controlled defect. Every field is required.\n")
    record = {}
    for field, description in REQUIRED_FIELDS:
        if field == "category":
            print("  categories: " + ", ".join(ERROR_TYPE_ORDER))
        while True:
            value = input(f"  {field} ({description}): ").strip()
            if value:
                record[field] = value
                break
            print("    Required.")
    answer = ""
    while answer not in ("y", "n"):
        answer = input("  Did the failure reproduce? [y/n]: ").strip().lower()
    record["reproduced"] = answer == "y"
    record["notes"] = input("  Notes (optional): ").strip()
    record["recorded_at"] = datetime.now(timezone.utc).isoformat()
    return record


def parse_args():
    parser = argparse.ArgumentParser(description="Record and audit controlled defects")
    parser.add_argument("action", choices=("add", "audit", "commit"))
    parser.add_argument("--study-dir", required=True)
    parser.add_argument("--partition", default="held_out", help="Partition to hash-commit")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    path = Path(args.study_dir) / MANIFEST
    manifest = load(path)

    if args.action == "add":
        summary = audit(manifest)
        if summary["total"] >= MAX_TOTAL:
            print(f"ERROR: Already at the cap of {MAX_TOTAL} controlled defects.")
            return 1
        try:
            record = prompt_record()
        except (KeyboardInterrupt, EOFError):
            print("\nNothing recorded.")
            return 0
        existing = collections.Counter(item.get("category") for item in manifest["defects"])
        if existing[record["category"]] >= MAX_PER_CATEGORY:
            print(f"ERROR: {record['category']} already has {MAX_PER_CATEGORY} defects, which is the cap.")
            return 1
        problems = record_problems(record)
        if problems:
            print("ERROR: This record cannot be used:")
            for problem in problems:
                print(f"  - {problem}")
            return 1
        record["defect_sha256"] = defect_hash(record)
        manifest["defects"].append(record)
        manifest["updated_at"] = datetime.now(timezone.utc).isoformat()
        atomic_write_json(path, manifest)
        print(f"\nRecorded {record['defect_id']} ({record['category']}). {len(manifest['defects'])}/{MAX_TOTAL} used.")
        return 0

    if args.action == "audit":
        summary = audit(manifest)
        print()
        print("=" * 70)
        print(f"  CONTROLLED DEFECTS — {args.study_dir}")
        print("=" * 70)
        print(f"  recorded {summary['total']}/{MAX_TOTAL}, usable {summary['usable']}")
        print(f"  per category: {summary['per_category'] or 'none'}")
        print(f"  not yet covered: {', '.join(summary['categories_missing']) or 'none'}")
        if summary["findings"]:
            print("\n  Problems:")
            for finding in summary["findings"]:
                print(f"    [{finding['defect_id']}] {finding['problem']}")
        else:
            print("\n  Every record is complete.")
        print()
        return 1 if summary["findings"] else 0

    # commit: freeze the reserved defects before any tuning can see them.
    reserved = [item for item in manifest["defects"] if item.get("partition") == args.partition]
    if not reserved:
        print(f"ERROR: No defects are assigned to the {args.partition} partition.")
        return 1
    digest = hashlib.sha256(json.dumps(sorted(item["defect_sha256"] for item in reserved)).encode()).hexdigest()
    manifest.setdefault("commitments", []).append(
        {
            "partition": args.partition,
            "defect_ids": sorted(item["defect_id"] for item in reserved),
            "combined_sha256": digest,
            "git_commit": git_commit(),
            "committed_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    atomic_write_json(path, manifest)
    print(f"Committed {len(reserved)} {args.partition} defect(s): {digest[:16]}")
    print("Any later change to these records will not match this hash.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
