#!/usr/bin/env python3
"""Allocate the eligible cohort into development, pilot and held-out partitions.

Three rules govern the allocation, and the manifest records all three so the
split can be audited later:

* **Families move together.** The unit allocated is a causal failure family, not
  a case. A family straddling development and held-out would mean the system was
  tuned on the same underlying fault it is later tested against.
* **Repositories are represented in every partition.** The study compares
  performance across repositories, so each one is allocated proportionally
  rather than letting a shuffle concentrate a repository in one partition.
* **The split is reproducible.** A fixed seed and recorded checksums mean the
  same cohort always produces the same partitions.

The allocation is written once and then frozen. Re-running it against a changed
cohort produces a new manifest, which is a deliberate decision to record rather
than something to do casually.

    python automated_scripts/make_split.py --study-config configs/<study>.yaml --dry-run
"""

from __future__ import annotations

import argparse
import collections
import json
import random
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from automated_scripts.study_utils import atomic_write_json, git_commit, load_study_config, sha256_file, study_directory
from src.evaluation.failure_families import assign_families, build_families, check_no_family_spans_partitions

PARTITIONS = ("development", "pilot", "held_out")
DEFAULT_TARGETS = {"development": 15, "pilot": 15, "held_out": 50}


def allocate(cases: List[dict], targets: Dict[str, int], rule: str, seed: int) -> Dict[str, List[str]]:
    """Assign whole families to partitions, keeping repositories proportional.

    Partitions are filled in priority order -- development, then pilot, then
    held-out -- each to its proportional share of the repository. When a cohort
    is short of the overall target, that shortfall should land on the held-out
    set rather than on the two small sets needed to start work: development and
    pilot are fixed in size and used immediately, while the held-out set can
    grow with a later collection pass.

    Within a repository, families are shuffled with the seed so the allocation
    is reproducible but not ordered by collection sequence.
    """
    families = build_families(cases, rule)
    by_case = {case["log_id"]: case for case in cases if case.get("log_id")}

    per_repository: Dict[str, List] = collections.defaultdict(list)
    for family in families:
        repository = by_case.get(family.case_ids[0], {}).get("repository", "")
        per_repository[repository].append(family)

    total_cases = len(by_case)
    allocation: Dict[str, List[str]] = {name: [] for name in PARTITIONS}

    for repository in sorted(per_repository):
        group = per_repository[repository]
        repository_cases = sum(family.size for family in group)
        share = repository_cases / total_cases if total_cases else 0
        # This repository's slice of each partition's target.
        quota = {name: targets[name] * share for name in PARTITIONS}
        filled = {name: 0 for name in PARTITIONS}

        random.Random(f"{seed}:{repository}").shuffle(group)
        for family in group:
            # First partition, in priority order, that is still below its share.
            # Everything after the quotas are met falls to the last partition.
            chosen = PARTITIONS[-1]
            for name in PARTITIONS:
                if filled[name] < quota[name]:
                    chosen = name
                    break
            allocation[chosen].extend(family.case_ids)
            filled[chosen] += family.size

    return {name: sorted(ids) for name, ids in allocation.items()}


def summarise(allocation: Dict[str, List[str]], cases: List[dict], targets: Dict[str, int]) -> List[dict]:
    by_case = {case["log_id"]: case for case in cases if case.get("log_id")}
    rows = []
    for name in PARTITIONS:
        ids = allocation[name]
        repositories = collections.Counter(by_case.get(case_id, {}).get("repository", "?") for case_id in ids)
        rows.append(
            {
                "partition": name,
                "target": targets[name],
                "allocated": len(ids),
                "shortfall": max(0, targets[name] - len(ids)),
                "by_repository": dict(repositories),
            }
        )
    return rows


def parse_args():
    parser = argparse.ArgumentParser(description="Create the grouped development, pilot and held-out split")
    parser.add_argument("--study-config", default="configs/thesis_pair_2026.yaml")
    parser.add_argument("--study-dir", default=None)
    parser.add_argument("--rule", default="combined", help="Family grouping rule recorded in the manifest")
    parser.add_argument("--seed", type=int, default=20261010)
    parser.add_argument("--development", type=int, default=DEFAULT_TARGETS["development"])
    parser.add_argument("--pilot", type=int, default=DEFAULT_TARGETS["pilot"])
    parser.add_argument("--held-out", type=int, default=DEFAULT_TARGETS["held_out"])
    parser.add_argument("--dry-run", action="store_true", help="Report the split without writing the manifest")
    parser.add_argument("--overwrite", action="store_true", help="Replace an existing manifest, recording the reason")
    parser.add_argument("--reason", default="", help="Why an existing split is being replaced")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config, _ = load_study_config(args.study_config)
    root = study_directory(config, args.study_dir)
    cohort_path = root / "triaged" / "eligible_logs.json"
    manifest_path = root / "split_manifest.json"

    if not cohort_path.exists():
        print(f"ERROR: Eligible cohort does not exist: {cohort_path}")
        return 1
    if manifest_path.exists() and not args.overwrite and not args.dry_run:
        print(f"ERROR: A split already exists at {manifest_path}.")
        print("Re-splitting changes which cases the system may be tuned on.")
        print("Use --overwrite --reason '<why>' only for a documented re-split.")
        return 1
    if args.overwrite and not args.reason and not args.dry_run:
        print("ERROR: --overwrite requires --reason, which is recorded in the manifest.")
        return 1

    cases = json.loads(cohort_path.read_text(encoding="utf-8"))
    targets = {"development": args.development, "pilot": args.pilot, "held_out": args.held_out}
    allocation = allocate(cases, targets, args.rule, args.seed)

    assignment = assign_families(cases, args.rule)
    breaches = check_no_family_spans_partitions(allocation, assignment)

    rows = summarise(allocation, cases, targets)
    print()
    print("=" * 74)
    print(f"  SPLIT — {config['study_id']}   rule={args.rule}  seed={args.seed}")
    print("=" * 74)
    print(f"  {len(cases)} eligible cases in {len(set(assignment.values()))} families")
    print()
    print(f"  {'partition':<14}{'target':>8}{'allocated':>11}{'shortfall':>11}   by repository")
    for row in rows:
        repositories = ", ".join(f"{name}={count}" for name, count in sorted(row["by_repository"].items()))
        print(
            f"  {row['partition']:<14}{row['target']:>8}{row['allocated']:>11}{row['shortfall']:>11}   {repositories}"
        )
    print()
    if breaches:
        print(f"  ERROR: {len(breaches)} family/families span more than one partition:")
        for breach in breaches[:5]:
            print(f"    {breach['family_id']}: {', '.join(sorted(breach['partitions']))}")
        return 1
    print("  No family spans more than one partition.")
    total_short = sum(row["shortfall"] for row in rows)
    if total_short:
        print(f"  WARNING: {total_short} case(s) short of the targets. Collect more rather than")
        print("           weakening the eligibility rules.")
    print()

    if args.dry_run:
        print("  Dry run; no manifest was written.")
        return 0

    manifest = {
        "schema_version": 1,
        "study_id": config["study_id"],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "git_commit": git_commit(),
        "family_rule": args.rule,
        "seed": args.seed,
        "targets": targets,
        "source": {"file": str(cohort_path), "sha256": sha256_file(cohort_path), "case_count": len(cases)},
        "partitions": allocation,
        "summary": rows,
        "family_count": len(set(assignment.values())),
        "family_of_case": assignment,
        "replaced_previous": bool(args.overwrite),
        "replacement_reason": args.reason,
    }
    atomic_write_json(manifest_path, manifest)
    print(f"  Wrote {manifest_path}")
    print("  This split is now fixed. Re-splitting requires --overwrite --reason.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
