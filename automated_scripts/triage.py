#!/usr/bin/env python3
"""
triage.py - Smart log triage before diagnosis.

Reads raw collected logs and filters out noise:
  - Cancelled runs (not real failures)
  - Duplicate errors from the same workflow (same error signature)
  - Extremely short logs (likely setup-only)
  - Runs where the log is just "Bad credentials" (our own token issue)

Produces a filtered batch ready for diagnosis.

Usage:
    python automated_scripts/triage.py
    python automated_scripts/triage.py --input data/raw_logs/github_actions/batch1.json
    python automated_scripts/triage.py --min-lines 20 --max-duplicates 2
"""

import sys
import os
import json
import argparse
import hashlib
import re
from collections import Counter, defaultdict
from pathlib import Path

parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, parent_dir)

from automated_scripts.pipeline_manifest import record_step
from automated_scripts.study_utils import (
    atomic_write_json,
    git_commit,
    load_study_config,
    sha256_file,
    study_directory,
    utc_now,
)


# ---------------------------------------------------------------------------
# Triage rules
# ---------------------------------------------------------------------------

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
    """Extract a rough error 'fingerprint' to detect duplicates."""
    lines = log_content.split("\n")
    error_lines = []
    for line in lines:
        lower = line.lower()
        if any(kw in lower for kw in ["error", "failed", "exception", "fatal", "traceback"]):
            # Normalize: strip timestamps, ANSI codes, line numbers
            cleaned = re.sub(r"\d{4}-\d{2}-\d{2}[\sT]\d{2}:\d{2}:\d{2}[.\d]*Z?", "", line)
            cleaned = re.sub(r"\x1b\[[0-9;]*m", "", cleaned)
            cleaned = re.sub(r"0x[0-9a-fA-F]+", "0xADDR", cleaned)
            cleaned = cleaned.strip()
            if len(cleaned) > 10:
                error_lines.append(cleaned[:200])

    signature_text = "\n".join(error_lines[:20])
    return hashlib.md5(signature_text.encode()).hexdigest()[:12]


def is_cancelled_run(log_content: str) -> bool:
    for pat in SKIP_PATTERNS:
        if re.search(pat, log_content, re.IGNORECASE):
            return True
    return False


def is_token_error(log_content: str) -> bool:
    for pat in TOKEN_ERROR_PATTERNS:
        if re.search(pat, log_content, re.IGNORECASE):
            return True
    return False


def is_too_short(log_content: str, min_lines: int = 20) -> bool:
    return len(log_content.split("\n")) < min_lines


def classify_log_priority(log_content: str) -> str:
    """Quick heuristic classification for triage priority."""
    lower = log_content.lower()
    if "traceback" in lower or "stack trace" in lower:
        return "high"
    if "error:" in lower or "fatal" in lower:
        return "high"
    if "failed" in lower or "failure" in lower:
        return "medium"
    if "warning" in lower:
        return "low"
    return "low"


def exclusion_record(log: dict, reason: str, **details) -> dict:
    """Keep enough provenance to join an exclusion back to the immutable raw log."""
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


# ---------------------------------------------------------------------------
# Main triage
# ---------------------------------------------------------------------------

def triage_logs(logs: list, min_lines: int = 20, max_duplicates: int = 2) -> tuple:
    """Apply triage rules and return (kept, removed_with_reasons)."""
    kept = []
    removed = []
    signature_counts: dict = defaultdict(int)
    signature_repo: dict = defaultdict(list)

    for log in logs:
        content = log.get("log_content", "")
        log_id = log.get("log_id", "unknown")
        repo = log.get("repository", "")

        # Rule 1: Skip cancelled runs
        if is_cancelled_run(content):
            removed.append(exclusion_record(log, "cancelled_run"))
            continue

        # Rule 2: Skip our own token errors
        if is_token_error(content):
            removed.append(exclusion_record(log, "token_error"))
            continue

        # Rule 3: Skip extremely short logs
        if is_too_short(content, min_lines):
            removed.append(exclusion_record(log, "too_short"))
            continue

        # Rule 4: Deduplicate same error from same repo
        sig = compute_error_signature(content)
        sig_key = f"{repo}:{sig}"
        signature_counts[sig_key] += 1
        if signature_counts[sig_key] > max_duplicates:
            removed.append(exclusion_record(log, "duplicate_error", error_signature=sig))
            continue

        # Passed all rules - add priority
        log["triage_priority"] = classify_log_priority(content)
        log["error_signature"] = sig
        kept.append(log)

    # Sort kept by priority (high first)
    priority_order = {"high": 0, "medium": 1, "low": 2}
    kept.sort(key=lambda x: priority_order.get(x.get("triage_priority", "low"), 2))

    return kept, removed


def main():
    parser = argparse.ArgumentParser(description="Smart triage of collected CI/CD logs")
    parser.add_argument("--input", default=None)
    parser.add_argument("--output", default=None)
    parser.add_argument("--excluded-output", default=None,
                        help="JSON audit trail of excluded log IDs and reasons")
    parser.add_argument("--study-config", default=None,
                        help="YAML protocol used for a study-specific triage run")
    parser.add_argument("--study-dir", default=None,
                        help="Override data/studies/<study_id>")
    parser.add_argument("--overwrite", action="store_true",
                        help="Explicitly replace existing derived triage outputs")
    parser.add_argument("--min-lines", type=int, default=20, help="Skip logs shorter than this")
    parser.add_argument("--max-duplicates", type=int, default=2, help="Max same-error logs per repo")
    args = parser.parse_args()

    study_config = None
    study_config_path = None
    if args.study_config:
        try:
            study_config, study_config_path = load_study_config(args.study_config)
        except (OSError, ValueError) as exc:
            parser.error(f"invalid study config: {exc}")
        root = study_directory(study_config, args.study_dir)
        input_path = Path(args.input) if args.input else root / "raw" / "logs.json"
        output_path = Path(args.output) if args.output else root / "triaged" / "eligible_logs.json"
        excluded_path = Path(args.excluded_output) if args.excluded_output else root / "excluded" / "excluded_logs.json"
    else:
        if args.study_dir:
            parser.error("--study-dir requires --study-config")
        input_path = Path(args.input) if args.input else Path(parent_dir) / "data/raw_logs/github_actions/batch1.json"
        output_path = Path(args.output) if args.output else Path(parent_dir) / "data/raw_logs/github_actions/batch1_triaged.json"
        excluded_path = Path(args.excluded_output) if args.excluded_output else output_path.with_name(
            f"{output_path.stem}_excluded.json"
        )

    if not input_path.exists():
        parser.error(f"input file does not exist: {input_path}")
    existing_outputs = [path for path in (output_path, excluded_path) if path.exists()]
    if existing_outputs and not args.overwrite:
        parser.error("derived output already exists; use --overwrite only if replacement is intentional: " +
                     ", ".join(str(path) for path in existing_outputs))

    # Load
    with input_path.open(encoding="utf-8") as f:
        logs = json.load(f)

    print()
    print("=" * 70)
    print("  Smart Log Triage")
    print("=" * 70)
    print(f"  Input             : {input_path}")
    print(f"  Total raw logs    : {len(logs)}")
    print(f"  Min lines         : {args.min_lines}")
    print(f"  Max duplicates    : {args.max_duplicates}/repo/error")
    print()

    # Triage
    kept, removed = triage_logs(logs, args.min_lines, args.max_duplicates)

    # Report
    removal_reasons = Counter(r["reason"] for r in removed)
    priority_counts = Counter(k.get("triage_priority", "?") for k in kept)

    print(f"  Kept for diagnosis: {len(kept)}")
    print(f"  Removed           : {len(removed)}")
    print()
    if removal_reasons:
        print("  Removal reasons:")
        for reason, count in removal_reasons.most_common():
            print(f"    {reason:20s}: {count}")
        print()
    print("  Priority breakdown (kept):")
    for priority in ["high", "medium", "low"]:
        print(f"    {priority:8s}: {priority_counts.get(priority, 0)}")
    print()

    # Save
    atomic_write_json(output_path, kept)
    atomic_write_json(excluded_path, removed)

    print(f"  Saved {len(kept)} triaged logs to: {output_path}")
    print(f"  Saved {len(removed)} exclusion records to: {excluded_path}")

    if study_config:
        triage_manifest = {
            "schema_version": 1,
            "study_id": study_config["study_id"],
            "step": "triage",
            "completed_at": utc_now(),
            "git_commit": git_commit(),
            "study_config_source": str(study_config_path),
            "study_config_sha256": sha256_file(study_config_path),
            "rules": {
                "minimum_log_lines": args.min_lines,
                "maximum_duplicate_error_signatures_per_repository": args.max_duplicates,
            },
            "input": {"file": str(input_path), "sha256": sha256_file(input_path), "count": len(logs)},
            "eligible": {"file": str(output_path), "sha256": sha256_file(output_path), "count": len(kept)},
            "excluded": {"file": str(excluded_path), "sha256": sha256_file(excluded_path), "count": len(removed)},
            "removal_reasons": dict(removal_reasons),
        }
        atomic_write_json(root / "triage_manifest.json", triage_manifest)

    # Record in pipeline manifest
    record_step(
        step="triage",
        config={"min_lines": args.min_lines, "max_duplicates": args.max_duplicates},
        inputs={"raw_logs": len(logs), "file": str(input_path)},
        outputs={"kept": len(kept), "removed": len(removed), "file": str(output_path),
                 "excluded_file": str(excluded_path)},
        notes=f"{len(kept)}/{len(logs)} kept; removed: {dict(removal_reasons)}",
    )
    print()
    print("  Next step:")
    print("    1. Start API:   uvicorn src.api.main:app --reload")
    print("    2. Diagnose:    python automated_scripts/diagnose_logs.py")
    print()


if __name__ == "__main__":
    main()
