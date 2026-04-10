#!/usr/bin/env python3
"""
annotate.py - Manual ground truth annotation for demonstration evaluation.

Walks through each diagnosed log, shows you the LLM's diagnosis, lets you
open the GitHub URL to verify, and records YOUR assessment as ground truth.

Usage:
    python automated_scripts/annotate.py
    python automated_scripts/annotate.py --start-from 5   # resume from log #5
    python automated_scripts/annotate.py --input data/annotated_logs/diagnosed_batch1.json

Output: data/evaluation/ground_truth.json
"""

import sys
import os
import json
import argparse
from datetime import datetime

parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, parent_dir)

from automated_scripts.pipeline_manifest import record_step

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

QUALITY_RATINGS = {
    "1": "Incorrect - diagnosis is wrong or misleading",
    "2": "Partially correct - identifies symptoms but misses root cause",
    "3": "Mostly correct - right direction, minor issues",
    "4": "Correct - accurate root cause and useful fix suggestion",
    "5": "Excellent - precise root cause, actionable fix, good evidence",
}


def load_diagnosed(path: str) -> list:
    with open(path) as f:
        return json.load(f)


def load_existing_annotations(path: str) -> dict:
    if os.path.exists(path):
        with open(path) as f:
            data = json.load(f)
        return {a["log_id"]: a for a in data.get("annotations", [])}
    return {}


def save_annotations(annotations: dict, output_path: str):
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    payload = {
        "created_at": datetime.now().isoformat(),
        "annotator": "manual",
        "total": len(annotations),
        "annotations": list(annotations.values()),
    }
    with open(output_path, "w") as f:
        json.dump(payload, f, indent=2)


def print_diagnosis(idx: int, total: int, entry: dict):
    diag = entry["diagnosis"]
    print()
    print("=" * 75)
    print(f"  Log {idx}/{total}:  {entry['repository']}  --  {entry['workflow']}")
    print(f"  URL: {entry['url']}")
    print("=" * 75)
    print()
    print(f"  LLM Error Type    : {diag['error_type']}")
    print(f"  LLM Confidence    : {diag['confidence_score']:.0%}")
    print(f"  Hallucination     : {'YES' if diag['hallucination_detected'] else 'no'}")
    print(f"  Failure Lines     : {diag['failure_lines']}")
    print(f"  Model             : {diag['model_used']}")
    print(f"  Execution Time    : {diag['execution_time_ms']:.0f}ms")
    print()
    print("  ROOT CAUSE (LLM):")
    for line in diag["root_cause"].split(". "):
        print(f"    {line.strip()}")
    print()
    print("  SUGGESTED FIX (LLM):")
    for line in diag["suggested_fix"].split(". "):
        print(f"    {line.strip()}")
    print()
    print("  EVIDENCE:")
    for ev in diag.get("grounded_evidence", []):
        marker = "[ERR]" if ev["is_error"] else "[   ]"
        print(f"    Line {ev['line_number']:>6} {marker} {ev['content'][:90]}")
    print()
    print("  REASONING:")
    reasoning = diag.get("reasoning", "")
    for line in reasoning.split(". "):
        print(f"    {line.strip()}")
    print()


def ask_error_type() -> str:
    print("  What is the ACTUAL error type?")
    for i, t in enumerate(ERROR_TYPES, 1):
        print(f"    {i}. {t}")
    print(f"    0. (same as LLM)")
    while True:
        choice = input("  > ").strip()
        if choice == "0":
            return "__same__"
        if choice.isdigit() and 1 <= int(choice) <= len(ERROR_TYPES):
            return ERROR_TYPES[int(choice) - 1]
        if choice in ERROR_TYPES:
            return choice
        print("    Invalid choice. Try again.")


def ask_quality() -> int:
    print("  Rate the overall diagnosis quality:")
    for k, v in QUALITY_RATINGS.items():
        print(f"    {k}. {v}")
    while True:
        choice = input("  > ").strip()
        if choice in QUALITY_RATINGS:
            return int(choice)
        print("    Enter 1-5.")


def ask_yes_no(prompt: str, default: bool = False) -> bool:
    suffix = " [Y/n]: " if default else " [y/N]: "
    ans = input(prompt + suffix).strip().lower()
    if not ans:
        return default
    return ans.startswith("y")


def ask_free_text(prompt: str, default: str = "") -> str:
    if default:
        print(f"  {prompt} (press Enter to keep: '{default[:60]}...')")
    else:
        print(f"  {prompt}")
    ans = input("  > ").strip()
    return ans if ans else default


def annotate_one(idx: int, total: int, entry: dict) -> dict:
    diag = entry["diagnosis"]
    print_diagnosis(idx, total, entry)

    # 1. Error type
    actual_type = ask_error_type()
    if actual_type == "__same__":
        actual_type = diag["error_type"]
    type_correct = actual_type == diag["error_type"]

    # 2. Is the root cause correct?
    root_cause_correct = ask_yes_no("  Is the root cause explanation correct?")

    # 3. Is the fix actionable?
    fix_actionable = ask_yes_no("  Is the suggested fix actionable and correct?")

    # 4. Are the cited lines real evidence?
    evidence_accurate = ask_yes_no("  Are the cited evidence lines accurate?", default=True)

    # 5. Overall quality
    quality = ask_quality()

    # 6. Optional notes
    notes = ask_free_text("Any notes? (optional)")

    # 7. Your own root cause (optional override)
    if not root_cause_correct:
        actual_root_cause = ask_free_text(
            "What is the actual root cause?", default=diag["root_cause"]
        )
    else:
        actual_root_cause = diag["root_cause"]

    return {
        "log_id": entry["log_id"],
        "repository": entry["repository"],
        "workflow": entry["workflow"],
        "url": entry["url"],
        "llm_error_type": diag["error_type"],
        "actual_error_type": actual_type,
        "type_correct": type_correct,
        "root_cause_correct": root_cause_correct,
        "fix_actionable": fix_actionable,
        "evidence_accurate": evidence_accurate,
        "quality_rating": quality,
        "notes": notes,
        "actual_root_cause": actual_root_cause,
        "llm_confidence": diag["confidence_score"],
        "hallucination_detected": diag["hallucination_detected"],
        "execution_time_ms": diag["execution_time_ms"],
        "model_used": diag["model_used"],
        "annotated_at": datetime.now().isoformat(),
    }


def main():
    parser = argparse.ArgumentParser(description="Annotate LLM diagnoses with ground truth")
    parser.add_argument(
        "--input",
        default=os.path.join(parent_dir, "data/annotated_logs/diagnosed_batch1.json"),
    )
    parser.add_argument(
        "--output",
        default=os.path.join(parent_dir, "data/evaluation/ground_truth.json"),
    )
    parser.add_argument("--start-from", type=int, default=1, help="Resume from log N")
    args = parser.parse_args()

    diagnosed = load_diagnosed(args.input)
    annotations = load_existing_annotations(args.output)

    print()
    print("=" * 75)
    print("  Ground Truth Annotation Tool")
    print("=" * 75)
    print(f"  Diagnosed logs : {len(diagnosed)}")
    print(f"  Already done   : {len(annotations)}")
    print(f"  Starting from  : #{args.start_from}")
    print()
    print("  For each log you will:")
    print("    1. See the LLM diagnosis")
    print("    2. Open the GitHub URL to verify")
    print("    3. Record whether the diagnosis is correct")
    print()
    print("  Type 'q' at any prompt to save and quit.")
    print("  Type 's' to skip a log.")
    print()

    for i, entry in enumerate(diagnosed, 1):
        if i < args.start_from:
            continue
        if entry["log_id"] in annotations:
            print(f"  [{i}/{len(diagnosed)}] {entry['log_id']} -- already annotated, skipping")
            continue

        try:
            result = annotate_one(i, len(diagnosed), entry)
            annotations[entry["log_id"]] = result
            save_annotations(annotations, args.output)
            print(f"\n  Saved. ({len(annotations)}/{len(diagnosed)} done)\n")
        except (KeyboardInterrupt, EOFError):
            print("\n\n  Interrupted. Saving progress...")
            save_annotations(annotations, args.output)
            print(f"  Saved {len(annotations)} annotations to {args.output}")
            sys.exit(0)

    save_annotations(annotations, args.output)
    print()
    print("=" * 75)
    print(f"  Done! {len(annotations)} annotations saved to {args.output}")
    print("=" * 75)
    print()
    print("  Next step: python automated_scripts/evaluate_demo.py")

    # Record in pipeline manifest
    record_step(
        step="annotate",
        config={"annotator": "manual"},
        inputs={"diagnosed_logs": len(diagnosed), "file": args.input},
        outputs={"annotations": len(annotations), "file": args.output},
        notes=f"{len(annotations)}/{len(diagnosed)} logs annotated",
    )


if __name__ == "__main__":
    main()
