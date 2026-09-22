#!/usr/bin/env python3
"""Apply the fixed eligibility rules to an immutable thesis dataset."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from automated_scripts.study_utils import (
    atomic_write_json,
    git_commit,
    load_study_config,
    sha256_file,
    study_directory,
    utc_now,
)
from src.evaluation.case_partitions import load_exclusions

SKIP_PATTERNS = [
    r"The operation was canceled",
    r"Cancelling since a higher priority waiting request",
    r"The runner has received a shutdown signal",
    r"Error: The operation was canceled",
]
TOKEN_ERROR_PATTERNS = [
    r"Bad credentials",
    r"401.*Unauthorized",
    r"Resource not accessible by integration",
]


def compute_error_signature(log_content: str) -> str:
    error_lines = []
    for line in log_content.splitlines():
        if any(keyword in line.lower() for keyword in ("error", "failed", "exception", "fatal", "traceback")):
            cleaned = re.sub(r"\d{4}-\d{2}-\d{2}[\sT]\d{2}:\d{2}:\d{2}[.\d]*Z?", "", line)
            cleaned = re.sub(r"\x1b\[[0-9;]*m", "", cleaned)
            cleaned = re.sub(r"0x[0-9a-fA-F]+", "0xADDR", cleaned).strip()
            if len(cleaned) > 10:
                error_lines.append(cleaned[:200])
    if not error_lines:
        error_lines = [line.strip()[:200] for line in log_content.splitlines()[-20:] if line.strip()]
    return hashlib.sha256("\n".join(error_lines[:20]).encode()).hexdigest()[:12]


def exclusion_record(log: dict, reason: str, **details) -> dict:
    record = {
        "log_id": log.get("log_id", "unknown"),
        "reason": reason,
        "repository": log.get("repository", ""),
        "workflow_name": log.get("workflow_name", ""),
        "run_id": log.get("run_id"),
        "url": log.get("url", ""),
        "log_sha256": log.get("log_sha256", ""),
    }
    record.update(details)
    return record


def triage_logs(
    logs: list,
    min_lines: int = 20,
    max_duplicates: int = 2,
    exploratory: dict | None = None,
) -> tuple[list, list]:
    kept = []
    excluded = []
    signature_counts = defaultdict(int)
    exploratory = exploratory or {}

    for log in logs:
        content = log.get("log_content", "")
        # A case an exploratory cohort has already used cannot carry held-out
        # evidence (kickoff decision D4). Excluding it here keeps the cohort
        # clean by construction, records the reason alongside every other
        # exclusion, and avoids spending annotation effort on an unusable case.
        used_by = exploratory.get(log.get("log_id"))
        if used_by is not None:
            excluded.append(
                exclusion_record(log, "used_in_exploratory_cohort", exploratory_cohort=used_by.cohort_id)
            )
            continue
        if any(re.search(pattern, content, re.IGNORECASE) for pattern in SKIP_PATTERNS):
            excluded.append(exclusion_record(log, "cancelled_run"))
            continue
        if any(re.search(pattern, content, re.IGNORECASE) for pattern in TOKEN_ERROR_PATTERNS):
            excluded.append(exclusion_record(log, "token_error"))
            continue
        if len(content.splitlines()) < min_lines:
            excluded.append(exclusion_record(log, "too_short"))
            continue

        signature = compute_error_signature(content)
        key = f"{log.get('repository', '')}:{signature}"
        signature_counts[key] += 1
        if signature_counts[key] > max_duplicates:
            excluded.append(exclusion_record(log, "duplicate_error", error_signature=signature))
            continue

        derived = dict(log)
        derived["error_signature"] = signature
        kept.append(derived)
    return kept, excluded


def parse_args():
    parser = argparse.ArgumentParser(description="Triage the controlled thesis dataset")
    parser.add_argument("--study-config", default="configs/thesis_fresh_2026.yaml")
    parser.add_argument("--study-dir", default=None)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        config, config_path = load_study_config(args.study_config)
    except (OSError, ValueError) as exc:
        print(f"ERROR: Invalid study protocol: {exc}")
        return 1

    root = study_directory(config, args.study_dir)
    raw_path = root / "raw" / "logs.json"
    eligible_path = root / "triaged" / "eligible_logs.json"
    excluded_path = root / "excluded" / "excluded_logs.json"
    manifest_path = root / "triage_manifest.json"

    if not raw_path.exists():
        print(f"ERROR: Raw study data does not exist: {raw_path}")
        return 1
    if not args.overwrite and any(path.exists() for path in (eligible_path, excluded_path, manifest_path)):
        print("ERROR: Triage output already exists; use --overwrite only for a documented rerun.")
        return 1

    logs = json.loads(raw_path.read_text(encoding="utf-8"))
    rules = config["eligibility"]
    min_lines = int(rules["minimum_log_lines"])
    max_duplicates = int(rules["maximum_duplicate_error_signatures_per_repository"])
    exploratory, manifest_problems = load_exclusions(str(root.parent), str(eligible_path))
    for problem in manifest_problems:
        print(f"WARNING: {problem}")
    eligible, excluded = triage_logs(logs, min_lines, max_duplicates, exploratory)
    atomic_write_json(eligible_path, eligible)
    atomic_write_json(excluded_path, excluded)

    target = config.get("target_eligible_logs", {})
    minimum = int(target.get("minimum", 0))
    maximum = int(target.get("maximum", len(logs)))
    target_met = minimum <= len(eligible) <= maximum
    reason_counts = Counter(item["reason"] for item in excluded)
    manifest = {
        "schema_version": 1,
        "study_id": config["study_id"],
        "completed_at": utc_now(),
        "git_commit": git_commit(),
        "study_config_sha256": sha256_file(config_path),
        "rules": {
            "minimum_log_lines": min_lines,
            "maximum_duplicate_error_signatures_per_repository": max_duplicates,
            "exploratory_cases_known": len(exploratory),
        },
        "input": {"file": str(raw_path), "sha256": sha256_file(raw_path), "count": len(logs)},
        "eligible": {"file": str(eligible_path), "sha256": sha256_file(eligible_path), "count": len(eligible)},
        "excluded": {"file": str(excluded_path), "sha256": sha256_file(excluded_path), "count": len(excluded)},
        "removal_reasons": dict(reason_counts),
        "eligible_target": {
            "minimum": minimum,
            "maximum": maximum,
            "met": target_met,
        },
    }
    atomic_write_json(manifest_path, manifest)
    print(f"Triage complete: {len(eligible)} eligible, {len(excluded)} excluded")
    if not target_met:
        print(f"ERROR: Eligible cohort size {len(eligible)} is outside the fixed range {minimum}-{maximum}.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
