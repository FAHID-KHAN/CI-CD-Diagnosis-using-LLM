#!/usr/bin/env python3
"""Create a small, reproducible engineering cohort without changing source data."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from automated_scripts.study_utils import atomic_write_json, git_commit, sha256_file, utc_now


def stable_score(seed: int, value: str) -> str:
    return hashlib.sha256(f"{seed}:{value}".encode("utf-8")).hexdigest()


def select_smoke_cases(cases: list[dict], size: int, seed: int) -> list[dict]:
    """Select deterministically while maximizing repository diversity."""
    if size < 1:
        raise ValueError("Smoke cohort size must be positive")
    if size > len(cases):
        raise ValueError("Smoke cohort size exceeds the available case count")

    case_ids = [case.get("log_id") for case in cases]
    if None in case_ids or len(case_ids) != len(set(case_ids)):
        raise ValueError("Source cohort has missing or duplicate log IDs")

    by_repository: dict[str, list[dict]] = defaultdict(list)
    for case in cases:
        repository = case.get("repository")
        if not repository:
            raise ValueError(f"Case {case['log_id']} has no repository")
        if not case.get("log_sha256"):
            raise ValueError(f"Case {case['log_id']} has no log checksum")
        by_repository[repository].append(case)

    repositories = sorted(by_repository, key=lambda name: stable_score(seed, name))
    for repository, entries in by_repository.items():
        by_repository[repository] = sorted(entries, key=lambda case: stable_score(seed, case["log_id"]))

    selected = []
    offset = 0
    while len(selected) < size:
        added = False
        for repository in repositories:
            entries = by_repository[repository]
            if offset < len(entries):
                selected.append(entries[offset])
                added = True
                if len(selected) == size:
                    break
        if not added:
            break
        offset += 1
    return selected


def parse_args():
    parser = argparse.ArgumentParser(description="Create a reproducible engineering smoke-test cohort")
    parser.add_argument(
        "--input",
        default="data/studies/thesis_fresh_2026/triaged/eligible_logs.json",
        help="Eligible source cohort JSON",
    )
    parser.add_argument(
        "--output-dir",
        default="data/studies/system_smoke_001",
        help="New smoke-study directory",
    )
    parser.add_argument("--size", type=int, default=5)
    parser.add_argument("--seed", type=int, default=20260922)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    input_path = Path(args.input).expanduser().resolve()
    output_root = Path(args.output_dir).expanduser().resolve()
    cohort_path = output_root / "triaged" / "eligible_logs.json"
    manifest_path = output_root / "smoke_manifest.json"

    if not input_path.exists():
        print(f"ERROR: Source cohort does not exist: {input_path}")
        return 1
    if output_root.exists():
        print(f"ERROR: Smoke output already exists and will not be overwritten: {output_root}")
        return 1

    try:
        source_cases = json.loads(input_path.read_text(encoding="utf-8"))
        if not isinstance(source_cases, list):
            raise ValueError("Source cohort must be a JSON list")
        selected = select_smoke_cases(source_cases, args.size, args.seed)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"ERROR: Cannot create smoke cohort: {exc}")
        return 1

    atomic_write_json(cohort_path, selected)
    manifest = {
        "schema_version": 1,
        "cohort_id": output_root.name,
        "purpose": "engineering_smoke_test",
        "usable_as_final_thesis_evidence": False,
        "exclude_from_future_held_out_evaluation": True,
        "created_at": utc_now(),
        "git_commit": git_commit(),
        "source": {
            "file": str(input_path),
            "sha256": sha256_file(input_path),
            "case_count": len(source_cases),
        },
        "selection": {
            "method": "seeded_repository_round_robin",
            "seed": args.seed,
            "requested_size": args.size,
            "selected_size": len(selected),
        },
        "output": {
            "file": str(cohort_path),
            "sha256": sha256_file(cohort_path),
        },
        "selected_cases": [
            {
                "log_id": case["log_id"],
                "repository": case["repository"],
                "run_id": case.get("run_id"),
                "log_sha256": case["log_sha256"],
            }
            for case in selected
        ],
    }
    atomic_write_json(manifest_path, manifest)

    print(f"Created {len(selected)}-case engineering smoke cohort at {output_root}")
    for case in selected:
        print(f"  {case['repository']}: {case['log_id']}")
    print("This cohort is exploratory and must be excluded from the final held-out evaluation.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
