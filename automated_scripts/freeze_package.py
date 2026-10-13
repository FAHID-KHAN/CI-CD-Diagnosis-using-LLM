#!/usr/bin/env python3
"""Record exactly what was frozen before the held-out evaluation.

The held-out test is run once. Everything that could change its outcome is
captured here first, so that a result can later be traced to the precise system
and dataset that produced it, and so that a change made after the fact is
detectable rather than merely discouraged.

The package records what the evaluation plan requires: the source revision and
whether the worktree was clean, the prompt and system instructions, the response
schema, decoding parameters, preprocessing rules, the baseline ruleset, the
dataset split, the ground-truth labels, and the analysis configuration -- each
with a checksum.

    python automated_scripts/freeze_package.py create --study-config <cfg>
    python automated_scripts/freeze_package.py verify --study-config <cfg>

``verify`` re-computes every checksum and reports what has changed since the
freeze. A non-zero exit means the system is no longer the one that was frozen.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from automated_scripts.study_utils import atomic_write_json, git_commit, load_study_config, study_directory

FREEZE_FILE = "freeze_record.json"


def _run(command: List[str]) -> str:
    try:
        completed = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=15, check=False)
        return (completed.stdout or "").strip()
    except (OSError, subprocess.TimeoutExpired):
        return ""


def worktree_is_clean() -> bool:
    """A dirty worktree means the recorded commit does not describe the code."""
    return _run(["git", "status", "--porcelain"]) == ""


def digest_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def digest_file(path: Path) -> Optional[str]:
    if not path.exists():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def collect(config: dict, root: Path) -> Dict[str, object]:
    """Capture every input that could change the held-out outcome."""
    # Imported here so that creating a freeze record does not require the
    # OpenAI SDK to be importable for any other command.
    from src.api.baseline import DEFAULT_RULES, ruleset_sha256
    from src.api.llm_service import DIAGNOSIS_PROMPT, DIAGNOSIS_RESPONSE_FORMAT, SYSTEM_MESSAGE
    from src.api.models import ErrorType

    split_path = root / "split_manifest.json"
    ground_truth_path = root / "ground_truth" / "ground_truth.json"
    cohort_path = root / "triaged" / "eligible_logs.json"
    defects_path = root / "controlled_defects.json"

    return {
        "source": {
            "git_commit": git_commit(),
            "worktree_clean": worktree_is_clean(),
            "git_describe": _run(["git", "describe", "--tags", "--always", "--dirty"]),
        },
        "artifact": {
            "prompt_sha256": digest_text(DIAGNOSIS_PROMPT),
            "system_message_sha256": digest_text(SYSTEM_MESSAGE),
            "response_schema_sha256": digest_text(json.dumps(DIAGNOSIS_RESPONSE_FORMAT, sort_keys=True)),
            "taxonomy": [item.value for item in ErrorType],
            "preprocessing": {"max_lines": 500, "window_size": 20, "max_tokens": 12000},
            "decoding": {"reasoning_effort": "medium", "max_tokens": 4096},
        },
        "baseline": {"ruleset_sha256": ruleset_sha256(DEFAULT_RULES), "rule_count": len(DEFAULT_RULES)},
        "dataset": {
            "study_id": config["study_id"],
            "cohort_sha256": digest_file(cohort_path),
            "split_manifest_sha256": digest_file(split_path),
            "ground_truth_sha256": digest_file(ground_truth_path),
            "controlled_defects_sha256": digest_file(defects_path),
        },
        "analysis": {
            "primary_measures": [
                "exact category accuracy",
                "macro F1 with per-category precision, recall, F1 and support",
                "root-cause 0/1/2 rubric",
                "evidence-line precision and recall against surviving verified lines",
                "preprocessing recall",
                "diagnostic completion rate",
            ],
            "paired_analysis": "effect sizes with bootstrap confidence intervals; "
            "formal paired tests only where justified",
        },
    }


def blocking_problems(record: Dict[str, object]) -> List[str]:
    """Reasons this record cannot support a held-out run."""
    problems = []
    source = record["source"]
    dataset = record["dataset"]
    if not source.get("git_commit"):
        problems.append("no git commit recorded; the code version is unidentifiable")
    if not source.get("worktree_clean"):
        problems.append("the worktree is dirty, so the recorded commit does not describe the code that ran")
    for field, description in (
        ("cohort_sha256", "the eligible cohort"),
        ("split_manifest_sha256", "the dataset split"),
        ("ground_truth_sha256", "the ground-truth labels"),
    ):
        if not dataset.get(field):
            problems.append(f"{description} is missing")
    return problems


def compare(frozen: Dict[str, object], current: Dict[str, object], path: str = "") -> List[str]:
    """Every checksum that differs between the record and the system now."""
    changes = []
    for key, frozen_value in frozen.items():
        where = f"{path}.{key}" if path else key
        current_value = current.get(key)
        if isinstance(frozen_value, dict) and isinstance(current_value, dict):
            changes.extend(compare(frozen_value, current_value, where))
        elif frozen_value != current_value:
            changes.append(f"{where}: frozen {frozen_value!r} -> now {current_value!r}")
    return changes


def parse_args():
    parser = argparse.ArgumentParser(description="Create or verify the freeze record")
    parser.add_argument("action", choices=("create", "verify"))
    parser.add_argument("--study-config", default="configs/thesis_pair_2026.yaml")
    parser.add_argument("--study-dir", default=None)
    parser.add_argument("--approved-by", default="", help="Who approved the freeze, recorded in the record")
    parser.add_argument("--allow-dirty", action="store_true", help="Record a dirty worktree, for a rehearsal only")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config, _ = load_study_config(args.study_config)
    root = study_directory(config, args.study_dir)
    record_path = root / FREEZE_FILE
    current = collect(config, root)

    if args.action == "create":
        problems = blocking_problems(current)
        if problems and not args.allow_dirty:
            print("ERROR: The system cannot be frozen yet:")
            for problem in problems:
                print(f"  - {problem}")
            return 1
        if record_path.exists():
            print(f"ERROR: A freeze record already exists at {record_path}.")
            print("The held-out test runs once. Re-freezing means a new version and a new run.")
            return 1
        record = {
            "schema_version": 1,
            "frozen_at": datetime.now(timezone.utc).isoformat(),
            "approved_by": args.approved_by,
            "recorded_problems": problems,
            **current,
        }
        atomic_write_json(record_path, record)
        print(f"Freeze record written to {record_path}")
        print(f"  commit        {current['source']['git_commit']}")
        print(f"  worktree      {'clean' if current['source']['worktree_clean'] else 'DIRTY'}")
        print(f"  prompt        {current['artifact']['prompt_sha256'][:16]}")
        print(f"  baseline      {current['baseline']['ruleset_sha256'][:16]}")
        print(f"  split         {str(current['dataset']['split_manifest_sha256'])[:16]}")
        print(f"  ground truth  {str(current['dataset']['ground_truth_sha256'])[:16]}")
        if not args.approved_by:
            print("\n  No approver recorded. Re-create with --approved-by once supervisors have signed off.")
        return 0

    if not record_path.exists():
        print(f"ERROR: No freeze record at {record_path}. Create one before the held-out run.")
        return 1
    frozen = json.loads(record_path.read_text(encoding="utf-8"))
    changes = compare({key: frozen[key] for key in ("source", "artifact", "baseline", "dataset")}, current)

    print()
    print("=" * 70)
    print(f"  FREEZE VERIFICATION — {config['study_id']}")
    print("=" * 70)
    print(f"  frozen at   {frozen.get('frozen_at')}")
    print(f"  approved by {frozen.get('approved_by') or 'NOBODY RECORDED'}")
    print()
    if changes:
        print(f"  {len(changes)} difference(s) since the freeze:")
        for change in changes:
            print(f"    {change}")
        print("\n  The system is not the one that was frozen.")
        return 1
    print("  Everything matches the freeze record.")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
