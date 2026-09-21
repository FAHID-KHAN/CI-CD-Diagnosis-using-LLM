#!/usr/bin/env python3
"""
benchmark_models.py - Run the same logs through multiple LLMs and compare.

Uses LLMDiagnoser directly (no HTTP/API overhead) to benchmark each model
on the same set of triaged logs.

Usage:
    # Compare the thesis proprietary and open-weight conditions
    python automated_scripts/benchmark_models.py

    # Custom model list
    python automated_scripts/benchmark_models.py \
        --models openai/gpt-5.6-terra local/gpt-oss:20b

    # Limit to 10 logs for a quick test
    python automated_scripts/benchmark_models.py --limit 10

    # Use existing ground truth to compute accuracy
    python automated_scripts/benchmark_models.py --ground-truth data/evaluation/ground_truth.json

Output:
    results/benchmark/<timestamp>/
        results_<provider>_<model>.json   (per-model raw results)
        comparison_report.json            (side-by-side metrics)
        comparison_table.txt              (printable summary)
"""

import asyncio
import hashlib
import json
import os
import sys
import argparse
import importlib.metadata
import platform
import subprocess
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
from automated_scripts.pipeline_manifest import record_step


# ── Default model configurations ──────────────────────────────────────────

DEFAULT_MODELS = [
    "openai/gpt-5.6-terra",
    "local/gpt-oss:20b",
]


def parse_args():
    parser = argparse.ArgumentParser(description="Benchmark multiple LLMs on CI/CD log diagnosis")
    parser.add_argument(
        "--models", nargs="+", default=DEFAULT_MODELS,
        help="Models to benchmark in 'provider/model' format (e.g. openai/gpt-5.6-terra local/gpt-oss:20b)",
    )
    parser.add_argument(
        "--input", default=None,
        help="Input JSON file (default: batch1_triaged.json or batch1.json)",
    )
    parser.add_argument("--limit", type=int, default=None, help="Max logs to process")
    parser.add_argument(
        "--pilot", action="store_true",
        help="Run a five-log pilot (equivalent to --limit 5)",
    )
    parser.add_argument(
        "--temperature", type=float, default=0.0,
        help="Sampling temperature for legacy models; thesis reasoning models ignore it",
    )
    parser.add_argument(
        "--reasoning-effort", choices=["low", "medium", "high"], default="medium",
        help="Common reasoning level for both thesis models",
    )
    parser.add_argument(
        "--ground-truth", default=None,
        help="Ground truth JSON for accuracy computation",
    )
    parser.add_argument("--output-dir", default=None, help="Output directory")
    parser.add_argument("--max-tokens", type=int, default=12000, help="Max tokens for log filtering")
    return parser.parse_args()


def resolve_input(args):
    if args.input:
        return args.input
    triaged = os.path.join(parent_dir, "data/raw_logs/github_actions/batch1_triaged.json")
    raw = os.path.join(parent_dir, "data/raw_logs/github_actions/batch1.json")
    if os.path.exists(triaged):
        return triaged
    if os.path.exists(raw):
        return raw
    print("ERROR: No input logs found. Run data collection + triage first.")
    sys.exit(1)


def parse_model_spec(spec: str):
    """Parse 'provider/model' into (LLMProvider, model_name)."""
    parts = spec.split("/", 1)
    if len(parts) != 2:
        print(f"ERROR: Invalid model spec '{spec}'. Expected 'provider/model'.")
        sys.exit(1)
    provider_str, model_name = parts
    provider_map = {
        "openai": LLMProvider.OPENAI,
        "anthropic": LLMProvider.ANTHROPIC,
        "local": LLMProvider.LOCAL,
    }
    provider = provider_map.get(provider_str.lower())
    if provider is None:
        print(f"ERROR: Unknown provider '{provider_str}'. Use: openai, anthropic, local")
        sys.exit(1)
    return provider, model_name


def build_diagnoser(provider: LLMProvider, model: str, reasoning_effort: str) -> LLMDiagnoser:
    """Build an LLMDiagnoser with the right API key."""
    if provider == LLMProvider.OPENAI:
        api_key = os.getenv("OPENAI_API_KEY")
    elif provider == LLMProvider.ANTHROPIC:
        api_key = os.getenv("ANTHROPIC_API_KEY")
    else:
        api_key = None
    return LLMDiagnoser(
        provider=provider,
        model=model,
        api_key=api_key,
        reasoning_effort=reasoning_effort,
    )


async def diagnose_one(diagnoser, filtered_log, log_entry, temperature):
    """Run a single diagnosis and return the result dict + timing."""
    start = time.time()
    try:
        result = await diagnoser.diagnose(
            filtered_log,
            temperature=temperature,
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
    local_models = [
        parse_model_spec(spec)[1]
        for spec in model_specs
        if spec.lower().startswith("local/")
    ]
    if local_models:
        metadata["ollama_version"] = _run_metadata_command(["ollama", "--version"])
        metadata["ollama_list"] = _run_metadata_command(["ollama", "list"])
        metadata["ollama_models"] = {
            model: _run_metadata_command(["ollama", "show", model, "--verbose"])
            for model in local_models
        }
    return metadata


async def benchmark_model(
    provider, model, logs, temperature, max_tokens, reasoning_effort, checkpoint_file,
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
            diagnoser, filtered, log_entry, temperature,
        )

        if diagnosis:
            usage = diagnoser.last_usage
            evidence = [LogLine(**ev) for ev in diagnosis.get("grounded_evidence", [])]
            hallucination_detected, grounding_score = GroundingVerifier.verify_evidence(
                filtered, evidence,
            )
            results.append({
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
            })
            conf = diagnosis.get("confidence_score", 0)
            print(f"OK  {diagnosis.get('error_type','?')} ({conf:.0%}) [{elapsed_ms:.0f}ms]")
        else:
            print(f"FAIL  {error[:50] if error else '?'}")
            results.append({
                "status": "error",
                "log_id": log_id,
                "repository": repo,
                "workflow": workflow,
                "model": label,
                "execution_time_ms": elapsed_ms,
                "error": error or "Unknown diagnosis error",
            })

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
        "mean_grounding_score": round(
            sum(r.get("grounding_score", 0) for r in successful) / n, 3
        ) if n else 0.0,
        "hallucination_rate": round(
            sum(bool(r.get("hallucination_detected")) for r in successful) / n, 3
        ) if n else 0.0,
        "total_tokens": sum(r.get("total_tokens", 0) for r in successful),
        "total_cost_usd": round(sum(r.get("cost_usd", 0) for r in successful), 6),
        "cost_per_diagnosis_usd": round(
            sum(r.get("cost_usd", 0) for r in successful) / n, 6
        ) if n else 0.0,
    }

    # If ground truth is available, compute accuracy
    if ground_truth:
        gt_map = {a["log_id"]: a for a in ground_truth}
        type_correct = 0
        root_correct = 0
        matched = 0
        for r in successful:
            gt = gt_map.get(r["log_id"])
            if gt:
                matched += 1
                if r["error_type"] == gt["actual_error_type"]:
                    type_correct += 1
                # Root cause is harder to auto-evaluate; use GT flag if present
                if gt.get("root_cause_correct"):
                    root_correct += 1
        if matched > 0:
            metrics["matched_gt_logs"] = matched
            metrics["error_type_accuracy"] = round(type_correct / matched, 3)

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
    print(f"  Models: {', '.join(args.models)}")
    print(f"  Reasoning effort: {args.reasoning_effort}")
    print(f"  Legacy temperature: {args.temperature}")
    print()

    with open(input_file) as f:
        logs = json.load(f)
    effective_limit = 5 if args.pilot else args.limit
    if effective_limit:
        logs = logs[: effective_limit]
    print(f"  Logs to benchmark: {len(logs)}")
    print()

    # Load ground truth if provided
    ground_truth = None
    if args.ground_truth and os.path.exists(args.ground_truth):
        with open(args.ground_truth) as f:
            gt_data = json.load(f)
        ground_truth = gt_data.get("annotations", gt_data if isinstance(gt_data, list) else [])
        print(f"  Ground truth: {len(ground_truth)} annotations loaded")
        print()

    # Prepare output directory
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    if args.output_dir:
        out_dir = args.output_dir
    else:
        out_dir = os.path.join(parent_dir, "results", "benchmark", timestamp)
    os.makedirs(out_dir, exist_ok=True)

    runtime_metadata = collect_runtime_metadata(args.models)
    runtime_metadata["input_file"] = os.path.abspath(input_file)
    runtime_metadata["input_sha256"] = _sha256_file(input_file)
    runtime_metadata["log_filter"] = {
        "max_lines": 500,
        "window_size": 20,
        "max_tokens": args.max_tokens,
    }
    runtime_metadata["reasoning_effort"] = args.reasoning_effort
    runtime_metadata["legacy_temperature"] = args.temperature
    with open(os.path.join(out_dir, "run_metadata.json"), "w") as f:
        json.dump(runtime_metadata, f, indent=2)

    # ── Run each model ────────────────────────────────────────────────
    all_results = {}
    all_metrics = {}

    for model_spec in args.models:
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
                args.temperature,
                args.max_tokens,
                args.reasoning_effort,
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
        "temperature": args.temperature,
        "reasoning_effort": args.reasoning_effort,
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
                if r.get("status", "success") != "success":
                    continue
                gt = gt_map.get(r["log_id"])
                if gt:
                    preds.append(PredictionResult(
                        log_id=r["log_id"],
                        predicted_error_type=r["error_type"],
                        actual_error_type=gt["actual_error_type"],
                        predicted_lines=r.get("failure_lines", []),
                        actual_lines=gt.get("failure_lines", gt.get("actual_lines", [])),
                        confidence=r["confidence_score"],
                        hallucination_detected=r.get("hallucination_detected", False),
                        execution_time_ms=r["execution_time_ms"],
                        cost_usd=r.get("cost_usd", 0),
                    ))
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

    # Record in pipeline manifest
    record_step(
        step="benchmark",
        config={
            "models": args.models,
            "temperature": args.temperature,
            "reasoning_effort": args.reasoning_effort,
            "pilot": args.pilot,
        },
        inputs={"logs": len(logs), "file": input_file},
        outputs={
            "models_benchmarked": len(all_metrics),
            "output_dir": out_dir,
            **{f"{k}_diagnosed": m.get("total_logs", 0) for k, m in all_metrics.items()},
        },
        notes=f"{len(all_metrics)} models benchmarked on {len(logs)} logs",
    )


if __name__ == "__main__":
    asyncio.run(main())
