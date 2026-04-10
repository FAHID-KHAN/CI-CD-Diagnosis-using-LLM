#!/usr/bin/env python3
"""
evaluate_demo.py - Demonstration evaluation report generator.

Reads ground truth annotations (from annotate.py) and the original diagnosed
logs, then produces:
  1. A structured JSON evaluation report
  2. Console summary tables
  3. Matplotlib charts (saved to results/evaluation/)

Implements Jussi's "Path A" approach: qualitative demonstration evaluation
comparing the LLM diagnosis against your manual assessment.

Also runs regex and heuristic baselines on the same logs for comparison.

Usage:
    python automated_scripts/evaluate_demo.py
    python automated_scripts/evaluate_demo.py --ground-truth data/evaluation/ground_truth.json
"""

import sys
import os
import json
import argparse
from collections import Counter
from datetime import datetime
from typing import Dict, List

parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(parent_dir, "src"))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

# Import baselines from the existing evaluation module
from evaluation.evaluation import BaselineEvaluator

from automated_scripts.pipeline_manifest import record_step


def load_ground_truth(path: str) -> list:
    with open(path) as f:
        data = json.load(f)
    return data.get("annotations", [])


def load_diagnosed(path: str) -> dict:
    with open(path) as f:
        items = json.load(f)
    return {item["log_id"]: item for item in items}


def load_raw_logs(path: str) -> dict:
    with open(path) as f:
        items = json.load(f)
    return {item["log_id"]: item for item in items}


def build_log_content_index(*file_paths: str) -> dict:
    """Build a merged {log_id: {log_content, ...}} index from multiple JSON files.

    Searches raw logs, triaged logs, and any other source so that baselines
    can still run even if the raw file was overwritten by a new collection.
    """
    index: dict = {}
    for path in file_paths:
        if not os.path.exists(path):
            continue
        try:
            with open(path) as f:
                items = json.load(f)
            for item in items:
                lid = item.get("log_id")
                if lid and lid not in index and item.get("log_content"):
                    index[lid] = item
        except (json.JSONDecodeError, KeyError):
            continue
    return index


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

def compute_llm_metrics(annotations: list) -> dict:
    """Compute metrics from human annotations of LLM diagnoses."""
    n = len(annotations)
    if n == 0:
        return {}

    type_correct = sum(1 for a in annotations if a["type_correct"])
    root_correct = sum(1 for a in annotations if a["root_cause_correct"])
    fix_ok = sum(1 for a in annotations if a["fix_actionable"])
    evidence_ok = sum(1 for a in annotations if a["evidence_accurate"])
    halluc = sum(1 for a in annotations if a["hallucination_detected"])
    qualities = [a["quality_rating"] for a in annotations]
    confidences = [a["llm_confidence"] for a in annotations]
    times = [a["execution_time_ms"] for a in annotations]

    return {
        "total_logs": n,
        "error_type_accuracy": type_correct / n,
        "root_cause_accuracy": root_correct / n,
        "fix_actionability": fix_ok / n,
        "evidence_accuracy": evidence_ok / n,
        "hallucination_rate": halluc / n,
        "mean_quality_rating": sum(qualities) / n,
        "quality_distribution": dict(Counter(qualities)),
        "mean_confidence": sum(confidences) / n,
        "mean_execution_time_ms": sum(times) / n,
        "type_correct_count": type_correct,
        "root_correct_count": root_correct,
        "fix_ok_count": fix_ok,
        "evidence_ok_count": evidence_ok,
        "hallucination_count": halluc,
    }


def compute_baseline_metrics(annotations: list, log_index: dict) -> dict:
    """Run regex and heuristic baselines on the same logs, compare to ground truth.

    ``log_index`` is a merged dict built by ``build_log_content_index`` so that
    we can find log content even if the original raw file was overwritten.
    """
    results = {"regex": {"correct": 0, "total": 0}, "heuristic": {"correct": 0, "total": 0}}
    missing_ids: list[str] = []

    for ann in annotations:
        log_id = ann["log_id"]
        actual_type = ann["actual_error_type"]
        entry = log_index.get(log_id)
        if not entry:
            missing_ids.append(log_id)
            continue

        content = entry.get("log_content", "")
        if not content:
            missing_ids.append(log_id)
            continue

        results["regex"]["total"] += 1
        results["heuristic"]["total"] += 1

        regex_type, _ = BaselineEvaluator.regex_baseline(content)
        if regex_type == actual_type:
            results["regex"]["correct"] += 1

        heur_type, _ = BaselineEvaluator.heuristic_baseline(content)
        if heur_type == actual_type:
            results["heuristic"]["correct"] += 1

    if missing_ids:
        print(f"  [WARN] Could not find raw log content for {len(missing_ids)}/{len(annotations)} annotations.")
        print(f"         Baselines computed on {results['regex']['total']} logs only.")
        print(f"         Missing IDs: {missing_ids[:3]}{'...' if len(missing_ids) > 3 else ''}")
        print(f"         Tip: re-annotate after re-collecting so IDs match.")
        print()

    for method in results:
        t = results[method]["total"]
        c = results[method]["correct"]
        results[method]["accuracy"] = c / t if t else 0.0

    return results


def compute_per_type_breakdown(annotations: list) -> dict:
    """Break down LLM accuracy by error type."""
    by_type: Dict[str, dict] = {}
    for ann in annotations:
        t = ann["actual_error_type"]
        if t not in by_type:
            by_type[t] = {"total": 0, "type_correct": 0, "root_correct": 0, "qualities": []}
        by_type[t]["total"] += 1
        if ann["type_correct"]:
            by_type[t]["type_correct"] += 1
        if ann["root_cause_correct"]:
            by_type[t]["root_correct"] += 1
        by_type[t]["qualities"].append(ann["quality_rating"])

    breakdown = {}
    for t, d in by_type.items():
        n = d["total"]
        breakdown[t] = {
            "count": n,
            "type_accuracy": d["type_correct"] / n,
            "root_cause_accuracy": d["root_correct"] / n,
            "mean_quality": sum(d["qualities"]) / n,
        }
    return breakdown


# ---------------------------------------------------------------------------
# Visualizations
# ---------------------------------------------------------------------------

def plot_quality_distribution(annotations: list, output_path: str):
    qualities = [a["quality_rating"] for a in annotations]
    counts = Counter(qualities)
    labels = ["1\nIncorrect", "2\nPartial", "3\nMostly", "4\nCorrect", "5\nExcellent"]
    values = [counts.get(i, 0) for i in range(1, 6)]

    fig, ax = plt.subplots(figsize=(8, 5))
    bars = ax.bar(range(1, 6), values, color=["#d32f2f", "#f57c00", "#fbc02d", "#388e3c", "#1565c0"], alpha=0.85)
    for bar, v in zip(bars, values):
        if v > 0:
            ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.15, str(v),
                    ha="center", fontsize=12, fontweight="bold")
    ax.set_xticks(range(1, 6))
    ax.set_xticklabels(labels, fontsize=10)
    ax.set_ylabel("Number of Logs", fontsize=12)
    ax.set_title("LLM Diagnosis Quality Distribution", fontsize=14, fontweight="bold")
    ax.set_ylim(0, max(values) + 2)
    ax.grid(axis="y", alpha=0.3)
    plt.tight_layout()
    plt.savefig(output_path, dpi=200)
    plt.close()


def plot_accuracy_comparison(llm_metrics: dict, baseline_metrics: dict, output_path: str):
    methods = ["LLM (GPT-4o-mini)", "Regex Baseline", "Heuristic Baseline"]
    accuracies = [
        llm_metrics["error_type_accuracy"],
        baseline_metrics["regex"]["accuracy"],
        baseline_metrics["heuristic"]["accuracy"],
    ]
    colors = ["#1565c0", "#757575", "#757575"]

    fig, ax = plt.subplots(figsize=(8, 5))
    bars = ax.bar(methods, accuracies, color=colors, alpha=0.85)
    for bar, v in zip(bars, accuracies):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.02,
                f"{v:.0%}", ha="center", fontsize=12, fontweight="bold")
    ax.set_ylabel("Error Type Accuracy", fontsize=12)
    ax.set_title("LLM vs Baseline: Error Type Classification", fontsize=14, fontweight="bold")
    ax.set_ylim(0, 1.15)
    ax.grid(axis="y", alpha=0.3)
    plt.tight_layout()
    plt.savefig(output_path, dpi=200)
    plt.close()


def plot_llm_dimensions(llm_metrics: dict, output_path: str):
    dims = ["Error Type\nAccuracy", "Root Cause\nAccuracy", "Fix\nActionability", "Evidence\nAccuracy"]
    values = [
        llm_metrics["error_type_accuracy"],
        llm_metrics["root_cause_accuracy"],
        llm_metrics["fix_actionability"],
        llm_metrics["evidence_accuracy"],
    ]

    fig, ax = plt.subplots(figsize=(8, 5))
    bars = ax.barh(dims, values, color="#1565c0", alpha=0.85)
    for bar, v in zip(bars, values):
        ax.text(bar.get_width() + 0.02, bar.get_y() + bar.get_height() / 2,
                f"{v:.0%}", va="center", fontsize=12, fontweight="bold")
    ax.set_xlim(0, 1.15)
    ax.set_xlabel("Accuracy", fontsize=12)
    ax.set_title("LLM Diagnosis Accuracy Across Dimensions", fontsize=14, fontweight="bold")
    ax.grid(axis="x", alpha=0.3)
    plt.tight_layout()
    plt.savefig(output_path, dpi=200)
    plt.close()


def plot_per_type_breakdown(breakdown: dict, output_path: str):
    types = list(breakdown.keys())
    type_acc = [breakdown[t]["type_accuracy"] for t in types]
    root_acc = [breakdown[t]["root_cause_accuracy"] for t in types]
    counts = [breakdown[t]["count"] for t in types]

    x = np.arange(len(types))
    width = 0.35

    fig, ax = plt.subplots(figsize=(10, 5))
    ax.bar(x - width / 2, type_acc, width, label="Type Accuracy", color="#1565c0", alpha=0.85)
    ax.bar(x + width / 2, root_acc, width, label="Root Cause Accuracy", color="#388e3c", alpha=0.85)

    ax.set_xticks(x)
    ax.set_xticklabels([f"{t}\n(n={c})" for t, c in zip(types, counts)], fontsize=9)
    ax.set_ylabel("Accuracy", fontsize=12)
    ax.set_title("Accuracy Breakdown by Error Type", fontsize=14, fontweight="bold")
    ax.set_ylim(0, 1.15)
    ax.legend()
    ax.grid(axis="y", alpha=0.3)
    plt.tight_layout()
    plt.savefig(output_path, dpi=200)
    plt.close()


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def print_console_report(llm_metrics: dict, baseline_metrics: dict, breakdown: dict):
    print()
    print("=" * 70)
    print("  DEMONSTRATION EVALUATION REPORT")
    print("=" * 70)
    print()

    n = llm_metrics["total_logs"]
    print(f"  Total logs evaluated: {n}")
    print()

    print("  --- LLM Diagnosis Performance ---")
    print(f"  Error type accuracy   : {llm_metrics['error_type_accuracy']:.0%}  ({llm_metrics['type_correct_count']}/{n})")
    print(f"  Root cause accuracy   : {llm_metrics['root_cause_accuracy']:.0%}  ({llm_metrics['root_correct_count']}/{n})")
    print(f"  Fix actionability     : {llm_metrics['fix_actionability']:.0%}  ({llm_metrics['fix_ok_count']}/{n})")
    print(f"  Evidence accuracy     : {llm_metrics['evidence_accuracy']:.0%}  ({llm_metrics['evidence_ok_count']}/{n})")
    print(f"  Hallucination rate    : {llm_metrics['hallucination_rate']:.0%}  ({llm_metrics['hallucination_count']}/{n})")
    print(f"  Mean quality (1-5)    : {llm_metrics['mean_quality_rating']:.1f}")
    print(f"  Mean confidence       : {llm_metrics['mean_confidence']:.2f}")
    print(f"  Mean execution time   : {llm_metrics['mean_execution_time_ms']:.0f}ms")
    print()

    print("  Quality distribution:")
    labels = {1: "Incorrect", 2: "Partial", 3: "Mostly", 4: "Correct", 5: "Excellent"}
    for rating in range(1, 6):
        count = llm_metrics["quality_distribution"].get(rating, 0)
        bar = "#" * (count * 3)
        print(f"    {rating} ({labels[rating]:>10s}): {bar} {count}")
    print()

    print("  --- Baseline Comparison ---")
    print(f"  LLM error type acc    : {llm_metrics['error_type_accuracy']:.0%}")
    print(f"  Regex baseline acc    : {baseline_metrics['regex']['accuracy']:.0%}")
    print(f"  Heuristic baseline acc: {baseline_metrics['heuristic']['accuracy']:.0%}")
    print()

    print("  --- Per Error Type ---")
    for t, d in breakdown.items():
        print(f"    {t:24s}  n={d['count']:2d}  type_acc={d['type_accuracy']:.0%}  root_acc={d['root_cause_accuracy']:.0%}  quality={d['mean_quality']:.1f}")
    print()
    print("=" * 70)


def main():
    parser = argparse.ArgumentParser(description="Generate demonstration evaluation report")
    parser.add_argument(
        "--ground-truth",
        default=os.path.join(parent_dir, "data/evaluation/ground_truth.json"),
    )
    parser.add_argument(
        "--diagnosed",
        default=os.path.join(parent_dir, "data/annotated_logs/diagnosed_batch1.json"),
    )
    parser.add_argument(
        "--raw-logs",
        default=os.path.join(parent_dir, "data/raw_logs/github_actions/batch1.json"),
    )
    parser.add_argument(
        "--triaged-logs",
        default=os.path.join(parent_dir, "data/raw_logs/github_actions/batch1_triaged.json"),
    )
    parser.add_argument(
        "--output-dir",
        default=os.path.join(parent_dir, "results/evaluation/demonstration"),
    )
    args = parser.parse_args()

    # Load data
    annotations = load_ground_truth(args.ground_truth)
    if not annotations:
        print("No annotations found. Run annotate.py first:")
        print("  python automated_scripts/annotate.py")
        sys.exit(1)

    # Build a merged log content index from all available sources
    log_index = build_log_content_index(args.raw_logs, args.triaged_logs)

    # Compute metrics
    llm_metrics = compute_llm_metrics(annotations)
    baseline_metrics = compute_baseline_metrics(annotations, log_index)
    breakdown = compute_per_type_breakdown(annotations)

    # Console report
    print_console_report(llm_metrics, baseline_metrics, breakdown)

    # Save report JSON
    os.makedirs(args.output_dir, exist_ok=True)

    report = {
        "timestamp": datetime.now().isoformat(),
        "total_logs": llm_metrics["total_logs"],
        "llm_metrics": llm_metrics,
        "baseline_comparison": baseline_metrics,
        "per_type_breakdown": breakdown,
        "annotations_file": args.ground_truth,
    }
    report_path = os.path.join(args.output_dir, "evaluation_report.json")
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)
    print(f"  Report saved to: {report_path}")

    # Generate charts
    plot_quality_distribution(
        annotations,
        os.path.join(args.output_dir, "quality_distribution.png"),
    )
    plot_accuracy_comparison(
        llm_metrics,
        baseline_metrics,
        os.path.join(args.output_dir, "accuracy_comparison.png"),
    )
    plot_llm_dimensions(
        llm_metrics,
        os.path.join(args.output_dir, "llm_dimensions.png"),
    )
    plot_per_type_breakdown(
        breakdown,
        os.path.join(args.output_dir, "per_type_breakdown.png"),
    )
    print(f"  Charts saved to: {args.output_dir}/")
    print()
    print("  Done!")

    # Record in pipeline manifest
    record_step(
        step="evaluate",
        config={},
        inputs={"annotations": len(annotations), "file": args.ground_truth},
        outputs={
            "llm_accuracy": round(llm_metrics["error_type_accuracy"], 3),
            "regex_accuracy": round(baseline_metrics["regex"]["accuracy"], 3),
            "heuristic_accuracy": round(baseline_metrics["heuristic"]["accuracy"], 3),
            "report_file": report_path,
        },
        notes=f"LLM {llm_metrics['error_type_accuracy']:.0%} vs regex {baseline_metrics['regex']['accuracy']:.0%} vs heuristic {baseline_metrics['heuristic']['accuracy']:.0%}",
    )


if __name__ == "__main__":
    main()
