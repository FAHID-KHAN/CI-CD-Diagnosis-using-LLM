#!/usr/bin/env python3
"""Run the controlled paired-model thesis experiment.

The two model conditions, shared reasoning effort, prompt, response schema and
filter limit are fixed in this file. Use ``--pilot`` for the required five-case
check, then use a new output directory for the final run.
"""

import argparse
import asyncio
import hashlib
import importlib.metadata
import json
import os
import platform
import subprocess
import sys
import time
from collections import Counter
from datetime import datetime, timezone

parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, parent_dir)

from dotenv import load_dotenv

load_dotenv(os.path.join(parent_dir, ".env"))

from src.api.llm_service import DIAGNOSIS_PROMPT, DIAGNOSIS_RESPONSE_FORMAT, LLMDiagnoser
from src.api.grounding import GroundingVerifier
from src.api.models import LLMProvider, LogLine
from src.api.filtering import LogFilter
from src.evaluation.evaluation import (
    PredictionResult,
    StatisticalTests,
    Visualizer,
)

# ── Default model configurations ──────────────────────────────────────────

DEFAULT_MODELS = [
    "openai/gpt-5.6-terra",
    "local/gpt-oss:20b",
]
REASONING_EFFORT = "medium"
MAX_FILTER_TOKENS = 12000


def parse_args():
    parser = argparse.ArgumentParser(description="Run the fixed paired-model CI/CD diagnosis experiment")
    parser.add_argument("--input", required=True, help="Frozen eligible cohort JSON")
    parser.add_argument(
        "--pilot",
        action="store_true",
        help="Run the required five-log pilot",
    )
    parser.add_argument("--ground-truth", required=True, help="Blind ground-truth JSON")
    parser.add_argument("--output-dir", required=True, help="Dedicated pilot or final output directory")
    return parser.parse_args()


def resolve_input(args):
    if not os.path.exists(args.input):
        print(f"ERROR: Input cohort does not exist: {args.input}")
        sys.exit(1)
    return args.input


def parse_model_spec(spec: str):
    """Parse 'provider/model' into (LLMProvider, model_name)."""
    parts = spec.split("/", 1)
    if len(parts) != 2:
        print(f"ERROR: Invalid model spec '{spec}'. Expected 'provider/model'.")
        sys.exit(1)
    provider_str, model_name = parts
    provider_map = {
        "openai": LLMProvider.OPENAI,
        "local": LLMProvider.LOCAL,
    }
    provider = provider_map.get(provider_str.lower())
    if provider is None:
        print(f"ERROR: Unknown provider '{provider_str}'. Use: openai or local")
        sys.exit(1)
    return provider, model_name


def build_diagnoser(provider: LLMProvider, model: str, reasoning_effort: str) -> LLMDiagnoser:
    """Build an LLMDiagnoser with the right API key."""
    if provider == LLMProvider.OPENAI:
        api_key = os.getenv("OPENAI_API_KEY")
    else:
        api_key = None
    return LLMDiagnoser(
        provider=provider,
        model=model,
        api_key=api_key,
        reasoning_effort=reasoning_effort,
    )


async def diagnose_one(diagnoser, filtered_log, log_entry):
    """Run a single diagnosis and return the result dict + timing."""
    start = time.time()
    try:
        result = await diagnoser.diagnose(
            filtered_log,
            repository=log_entry.get("repository", ""),
            workflow_name=log_entry.get("workflow_name", ""),
            ci_system="GitHub Actions",
            run_url=log_entry.get("url", ""),
        )
        elapsed_ms = (time.time() - start) * 1000
        return result, elapsed_ms, None
    except Exception as e:
        elapsed_ms = (time.time() - start) * 1000
        return None, elapsed_ms, str(e)


def save_checkpoint(path, results):
    """Atomically save benchmark progress after every attempted log."""
    tmp_path = f"{path}.tmp"
    with open(tmp_path, "w") as f:
        json.dump(results, f, indent=2)
    os.replace(tmp_path, path)


def _run_metadata_command(command):
    """Return reproducibility metadata without failing the benchmark."""
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        output = (completed.stdout or completed.stderr).strip()
        return {"returncode": completed.returncode, "output": output}
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"returncode": None, "output": str(exc)}


def _sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_inputs(logs, annotations):
    """Reject incomplete, duplicated, or stale ground truth before model calls."""
    if not isinstance(logs, list) or not logs:
        return "The eligible cohort must be a non-empty JSON list."
    if not isinstance(annotations, list) or not annotations:
        return "Ground truth must contain a non-empty annotations list."

    log_ids = [item.get("log_id") for item in logs]
    annotation_ids = [item.get("log_id") for item in annotations]
    if None in log_ids or len(log_ids) != len(set(log_ids)):
        return "The eligible cohort has missing or duplicate log IDs."
    if None in annotation_ids or len(annotation_ids) != len(set(annotation_ids)):
        return "Ground truth has missing or duplicate log IDs."

    missing = sorted(set(log_ids) - set(annotation_ids))
    unexpected = sorted(set(annotation_ids) - set(log_ids))
    if missing or unexpected:
        return f"Cohort/ground-truth ID mismatch (missing={missing}, unexpected={unexpected})."

    annotation_map = {item["log_id"]: item for item in annotations}
    stale = [
        item["log_id"]
        for item in logs
        if item.get("log_sha256") and annotation_map[item["log_id"]].get("log_sha256") != item["log_sha256"]
    ]
    if stale:
        return f"Ground truth was created from different log content: {stale}."
    return None


def collect_runtime_metadata(model_specs):
    """Capture enough environment detail to reproduce a thesis run."""
    metadata = {
        "run_started_at_utc": datetime.now(timezone.utc).isoformat(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "python_version": platform.python_version(),
        "openai_sdk_version": importlib.metadata.version("openai"),
        "models_requested": model_specs,
        "git_commit": _run_metadata_command(["git", "rev-parse", "HEAD"]),
        "prompt_sha256": hashlib.sha256(DIAGNOSIS_PROMPT.encode()).hexdigest(),
        "response_schema": DIAGNOSIS_RESPONSE_FORMAT,
    }
    local_models = [parse_model_spec(spec)[1] for spec in model_specs if spec.lower().startswith("local/")]
    if local_models:
        metadata["ollama_version"] = _run_metadata_command(["ollama", "--version"])
        metadata["ollama_list"] = _run_metadata_command(["ollama", "list"])
        metadata["ollama_models"] = {
            model: _run_metadata_command(["ollama", "show", model, "--verbose"]) for model in local_models
        }
    return metadata


async def benchmark_model(
    provider,
    model,
    logs,
    max_tokens,
    reasoning_effort,
    checkpoint_file,
):
    """Run all logs through one model with checkpoint/resume support."""
    diagnoser = build_diagnoser(provider, model, reasoning_effort)
    label = f"{provider.value}/{model}"
    results = []
    if os.path.exists(checkpoint_file):
        try:
            with open(checkpoint_file) as f:
                results = json.load(f)
        except (json.JSONDecodeError, OSError):
            results = []
    completed_ids = {r.get("log_id") for r in results}

    for i, log_entry in enumerate(logs, 1):
        log_id = log_entry["log_id"]
        repo = log_entry.get("repository", "")
        workflow = log_entry.get("workflow_name", "")

        if log_id in completed_ids:
            print(f"  [{i}/{len(logs)}] {repo} - {workflow} SKIP (checkpoint)")
            continue

        # Filter the log content
        filtered = LogFilter.apply_smart_filtering(
            log_entry["log_content"],
            max_lines=500,
            window_size=20,
            max_tokens=max_tokens,
        )

        print(f"  [{i}/{len(logs)}] {repo} - {workflow}", end=" ", flush=True)

        diagnosis, elapsed_ms, error = await diagnose_one(
            diagnoser,
            filtered,
            log_entry,
        )

        if diagnosis:
            usage = diagnoser.last_usage
            evidence = [LogLine(**ev) for ev in diagnosis.get("grounded_evidence", [])]
            hallucination_detected, grounding_score = GroundingVerifier.verify_evidence(
                filtered,
                evidence,
            )
            results.append(
                {
                    "status": "success",
                    "log_id": log_id,
                    "repository": repo,
                    "workflow": workflow,
                    "model": label,
                    "error_type": diagnosis.get("error_type", "unknown"),
                    "root_cause": diagnosis.get("root_cause", ""),
                    "suggested_fix": diagnosis.get("suggested_fix", ""),
                    "confidence_score": diagnosis.get("confidence_score", 0),
                    "failure_lines": diagnosis.get("failure_lines", []),
                    "grounded_evidence": [ev.model_dump(mode="json") for ev in evidence],
                    "reasoning": diagnosis.get("reasoning", ""),
                    "execution_time_ms": elapsed_ms,
                    "grounding_score": grounding_score,
                    "hallucination_detected": hallucination_detected,
                    "prompt_tokens": usage.get("prompt_tokens", 0),
                    "completion_tokens": usage.get("completion_tokens", 0),
                    "total_tokens": usage.get("total_tokens", 0),
                    "cost_usd": usage.get("estimated_cost_usd", 0.0),
                    "request_metadata": usage,
                    "raw_response": diagnoser.last_raw_response,
                }
            )
            conf = diagnosis.get("confidence_score", 0)
            print(f"OK  {diagnosis.get('error_type', '?')} ({conf:.0%}) [{elapsed_ms:.0f}ms]")
        else:
            print(f"FAIL  {error[:50] if error else '?'}")
            results.append(
                {
                    "status": "error",
                    "log_id": log_id,
                    "repository": repo,
                    "workflow": workflow,
                    "model": label,
                    "execution_time_ms": elapsed_ms,
                    "error": error or "Unknown diagnosis error",
                }
            )

        save_checkpoint(checkpoint_file, results)

        # Small delay to avoid rate limits
        await asyncio.sleep(0.3)

    return results


def compute_model_metrics(results, ground_truth=None):
    """Compute summary metrics for one model's results."""
    attempted = len(results)
    successful = [r for r in results if r.get("status", "success") == "success"]
    n = len(successful)
    if attempted == 0:
        return {
            "total_logs": 0,
            "successful_logs": 0,
            "failed_logs": 0,
            "avg_confidence": 0.0,
            "avg_execution_time_ms": 0.0,
            "mean_grounding_score": 0.0,
            "hallucination_rate": 0.0,
            "total_tokens": 0,
            "total_cost_usd": 0.0,
            "cost_per_diagnosis_usd": 0.0,
            "error_type_distribution": {},
        }

    avg_confidence = sum(r["confidence_score"] for r in successful) / n if n else 0.0
    avg_time = sum(r["execution_time_ms"] for r in successful) / n if n else 0.0
    error_dist = dict(Counter(r["error_type"] for r in successful))

    metrics = {
        "total_logs": attempted,
        "successful_logs": n,
        "failed_logs": attempted - n,
        "avg_confidence": round(avg_confidence, 3),
        "avg_execution_time_ms": round(avg_time, 1),
        "error_type_distribution": error_dist,
        "mean_grounding_score": round(sum(r.get("grounding_score", 0) for r in successful) / n, 3) if n else 0.0,
        "hallucination_rate": (
            round(sum(bool(r.get("hallucination_detected")) for r in successful) / n, 3) if n else 0.0
        ),
        "total_tokens": sum(r.get("total_tokens", 0) for r in successful),
        "total_cost_usd": round(sum(r.get("cost_usd", 0) for r in successful), 6),
        "cost_per_diagnosis_usd": round(sum(r.get("cost_usd", 0) for r in successful) / n, 6) if n else 0.0,
    }

    # Inference failures count as incorrect so this measures the complete
    # diagnostic system, not only the subset of successful model calls.
    if ground_truth:
        gt_map = {a["log_id"]: a for a in ground_truth}
        matched_results = [result for result in results if result.get("log_id") in gt_map]
        type_correct = sum(
            result.get("status", "success") == "success"
            and result.get("error_type") == gt_map[result["log_id"]]["actual_error_type"]
            for result in matched_results
        )
        if matched_results:
            metrics["matched_gt_logs"] = len(matched_results)
            metrics["error_type_accuracy"] = round(type_correct / len(matched_results), 3)

    return metrics


def print_comparison_table(all_metrics):
    """Print a formatted comparison table."""
    print()
    print("=" * 80)
    print("  BENCHMARK COMPARISON")
    print("=" * 80)

    header = f"  {'Model':<35} {'OK/All':>8} {'Accuracy':>9} {'Grounding':>10} {'Avg Time':>10} {'Cost':>10}"
    print(header)
    print("  " + "-" * 86)

    for model_label, m in all_metrics.items():
        acc = m.get("error_type_accuracy")
        acc_str = f"{acc:.1%}" if acc is not None else "N/A"
        cost = m.get("total_cost_usd", 0)
        if cost:
            cost_str = f"${cost:.4f}"
        elif model_label.startswith("local/"):
            cost_str = "$0 API"
        else:
            cost_str = "$0.0000"
        completion = f"{m.get('successful_logs', 0)}/{m.get('total_logs', 0)}"
        print(
            f"  {model_label:<35} {completion:>8} {acc_str:>9} "
            f"{m.get('mean_grounding_score', 0):>9.1%} {m['avg_execution_time_ms']:>8.0f}ms"
            f" {cost_str:>10}"
        )

    print("=" * 80)
    print()


async def main():
    args = parse_args()

    input_file = resolve_input(args)
    print()
    print("=" * 70)
    print("  Multi-Model Benchmark")
    print("=" * 70)
    print(f"  Input : {input_file}")
    print(f"  Models: {', '.join(DEFAULT_MODELS)}")
    print(f"  Reasoning effort: {REASONING_EFFORT}")
    print()

    with open(input_file) as f:
        logs = json.load(f)

    if not os.path.exists(args.ground_truth):
        print(f"ERROR: Ground truth does not exist: {args.ground_truth}")
        sys.exit(1)
    with open(args.ground_truth) as f:
        gt_data = json.load(f)
    if isinstance(gt_data, dict):
        ground_truth = gt_data.get("annotations", [])
    elif isinstance(gt_data, list):
        ground_truth = gt_data
    else:
        ground_truth = []
    validation_error = validate_inputs(logs, ground_truth)
    if validation_error:
        print(f"ERROR: {validation_error}")
        sys.exit(1)

    if args.pilot:
        logs = logs[:5]
    print(f"  Logs to benchmark: {len(logs)}")
    print(f"  Ground truth: {len(ground_truth)} annotations loaded")
    print()

    # Prepare output directory
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = args.output_dir
    os.makedirs(out_dir, exist_ok=True)
    metadata_path = os.path.join(out_dir, "run_metadata.json")
    expected_identity = {
        "input_sha256": _sha256_file(input_file),
        "ground_truth_sha256": _sha256_file(args.ground_truth),
        "pilot": args.pilot,
        "models_requested": DEFAULT_MODELS,
    }
    if os.path.exists(metadata_path):
        with open(metadata_path) as f:
            runtime_metadata = json.load(f)
        mismatches = [key for key, value in expected_identity.items() if runtime_metadata.get(key) != value]
        if mismatches:
            print(f"ERROR: Output directory belongs to another run ({', '.join(mismatches)} differ).")
            sys.exit(1)
        print("  Resuming the matching benchmark directory.")
    else:
        if os.listdir(out_dir):
            print("ERROR: Output directory is not empty and has no run metadata.")
            sys.exit(1)
        runtime_metadata = collect_runtime_metadata(DEFAULT_MODELS)
        runtime_metadata.update(expected_identity)
        runtime_metadata["input_file"] = os.path.abspath(input_file)
        runtime_metadata["ground_truth_file"] = os.path.abspath(args.ground_truth)
        runtime_metadata["log_filter"] = {
            "max_lines": 500,
            "window_size": 20,
            "max_tokens": MAX_FILTER_TOKENS,
        }
        runtime_metadata["reasoning_effort"] = REASONING_EFFORT
        with open(metadata_path, "w") as f:
            json.dump(runtime_metadata, f, indent=2)

    # ── Run each model ────────────────────────────────────────────────
    all_results = {}
    all_metrics = {}

    for model_spec in DEFAULT_MODELS:
        provider, model_name = parse_model_spec(model_spec)
        label = f"{provider.value}/{model_name}"
        safe_name = model_spec.replace("/", "_").replace(":", "_")
        model_file = os.path.join(out_dir, f"results_{safe_name}.json")

        print("-" * 70)
        print(f"  Benchmarking: {label}")
        print("-" * 70)

        try:
            results = await benchmark_model(
                provider,
                model_name,
                logs,
                MAX_FILTER_TOKENS,
                REASONING_EFFORT,
                model_file,
            )
        except Exception as e:
            print(f"  ERROR: Model {label} failed entirely: {e}")
            results = []

        all_results[label] = results

        # Save per-model results
        save_checkpoint(model_file, results)

        # Compute metrics
        metrics = compute_model_metrics(results, ground_truth)
        all_metrics[label] = metrics

        print(
            f"\n  {label}: {metrics.get('successful_logs', 0)}/{metrics.get('total_logs', 0)} "
            f"diagnosed, avg confidence {metrics.get('avg_confidence', 0):.1%}, "
            f"avg time {metrics.get('avg_execution_time_ms', 0):.0f}ms"
        )
        print()

    # ── Comparison report ─────────────────────────────────────────────
    report = {
        "timestamp": timestamp,
        "input_file": input_file,
        "total_logs": len(logs),
        "reasoning_effort": REASONING_EFFORT,
        "pilot": args.pilot,
        "runtime_metadata_file": "run_metadata.json",
        "models": all_metrics,
    }
    report_file = os.path.join(out_dir, "comparison_report.json")
    with open(report_file, "w") as f:
        json.dump(report, f, indent=2)

    print_comparison_table(all_metrics)

    # ── Statistical tests (when 2+ models and ground truth) ───────────
    model_labels = list(all_results.keys())
    if ground_truth and len(model_labels) >= 2:
        gt_map = {a["log_id"]: a for a in ground_truth}

        def _to_preds(results_list):
            preds = []
            for r in results_list:
                gt = gt_map.get(r["log_id"])
                if gt:
                    succeeded = r.get("status", "success") == "success"
                    preds.append(
                        PredictionResult(
                            log_id=r["log_id"],
                            predicted_error_type=r.get("error_type", "__inference_error__"),
                            actual_error_type=gt["actual_error_type"],
                            predicted_lines=r.get("failure_lines", []),
                            actual_lines=gt.get("failure_lines", gt.get("actual_lines", [])),
                            confidence=r.get("confidence_score", 0.0),
                            hallucination_detected=r.get("hallucination_detected", not succeeded),
                            execution_time_ms=r["execution_time_ms"],
                            cost_usd=r.get("cost_usd", 0),
                        )
                    )
            return preds

        # Pairwise McNemar's test between first two models
        a_label, b_label = model_labels[0], model_labels[1]
        preds_a = _to_preds(all_results[a_label])
        preds_b = _to_preds(all_results[b_label])

        if preds_a and preds_b:
            # Align by log_id
            ids_a = {p.log_id for p in preds_a}
            ids_b = {p.log_id for p in preds_b}
            common = sorted(ids_a & ids_b)
            map_a = {p.log_id: p for p in preds_a}
            map_b = {p.log_id: p for p in preds_b}
            aligned_a = [map_a[lid] for lid in common]
            aligned_b = [map_b[lid] for lid in common]

            mcnemar = StatisticalTests.mcnemar_test(aligned_a, aligned_b)
            ci_a = StatisticalTests.bootstrap_confidence_interval(aligned_a)
            ci_b = StatisticalTests.bootstrap_confidence_interval(aligned_b)
            perm = StatisticalTests.paired_permutation_test(aligned_a, aligned_b)

            stat_report = {
                "models_compared": [a_label, b_label],
                "n_common_logs": len(common),
                "mcnemar": mcnemar,
                "bootstrap_ci": {a_label: ci_a, b_label: ci_b},
                "permutation_test": perm,
            }
            report["statistical_tests"] = stat_report

            stat_file = os.path.join(out_dir, "statistical_tests.json")
            with open(stat_file, "w") as f:
                json.dump(stat_report, f, indent=2)

            print("\n  STATISTICAL TESTS")
            print("  " + "-" * 60)
            print(f"  McNemar's test ({a_label} vs {b_label}):")
            print(f"    chi2 = {mcnemar['chi2']}, p = {mcnemar['p_value']}")
            print(f"    → {mcnemar['verdict']}")
            print(f"  Bootstrap 95% CI ({a_label}): [{ci_a['ci_lower']:.1%}, {ci_a['ci_upper']:.1%}]")
            print(f"  Bootstrap 95% CI ({b_label}): [{ci_b['ci_lower']:.1%}, {ci_b['ci_upper']:.1%}]")
            print(f"  Permutation test: diff = {perm['observed_accuracy_diff']:.1%}, p = {perm['p_value']}")
            print()

    # ── Cost-accuracy trade-off chart ─────────────────────────────────
    if any(m.get("error_type_accuracy") is not None for m in all_metrics.values()):
        chart_data = {}
        for label, m in all_metrics.items():
            if m.get("error_type_accuracy") is not None:
                chart_data[label] = {
                    "accuracy": m["error_type_accuracy"],
                    "cost_per_diagnosis_usd": m.get("cost_per_diagnosis_usd", 0),
                    "avg_execution_time_ms": m.get("avg_execution_time_ms", 0),
                }
        if chart_data:
            chart_path = os.path.join(out_dir, "cost_accuracy_tradeoff.png")
            Visualizer.plot_cost_accuracy_tradeoff(chart_data, chart_path)

    # Overwrite report with new fields
    with open(report_file, "w") as f:
        json.dump(report, f, indent=2)

    print(f"  Results saved to: {out_dir}/")
    print()


if __name__ == "__main__":
    asyncio.run(main())
