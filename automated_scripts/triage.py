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

parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


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
            removed.append({"log_id": log_id, "reason": "cancelled_run", "repo": repo})
            continue

        # Rule 2: Skip our own token errors
        if is_token_error(content):
            removed.append({"log_id": log_id, "reason": "token_error", "repo": repo})
            continue

        # Rule 3: Skip extremely short logs
        if is_too_short(content, min_lines):
            removed.append({"log_id": log_id, "reason": "too_short", "repo": repo})
            continue

        # Rule 4: Deduplicate same error from same repo
        sig = compute_error_signature(content)
        sig_key = f"{repo}:{sig}"
        signature_counts[sig_key] += 1
        if signature_counts[sig_key] > max_duplicates:
            removed.append({"log_id": log_id, "reason": "duplicate_error", "repo": repo, "signature": sig})
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
    parser.add_argument(
        "--input",
        default=os.path.join(parent_dir, "data/raw_logs/github_actions/batch1.json"),
    )
    parser.add_argument(
        "--output",
        default=os.path.join(parent_dir, "data/raw_logs/github_actions/batch1_triaged.json"),
    )
    parser.add_argument("--min-lines", type=int, default=20, help="Skip logs shorter than this")
    parser.add_argument("--max-duplicates", type=int, default=2, help="Max same-error logs per repo")
    args = parser.parse_args()

    # Load
    with open(args.input) as f:
        logs = json.load(f)

    print()
    print("=" * 70)
    print("  Smart Log Triage")
    print("=" * 70)
    print(f"  Input             : {args.input}")
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
    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, "w") as f:
        json.dump(kept, f, indent=2)

    print(f"  Saved {len(kept)} triaged logs to: {args.output}")
    print()
    print("  Next step:")
    print("    1. Start API:   uvicorn src.api.main:app --reload")
    print("    2. Diagnose:    python automated_scripts/diagnose_logs.py")
    print()


if __name__ == "__main__":
    main()
