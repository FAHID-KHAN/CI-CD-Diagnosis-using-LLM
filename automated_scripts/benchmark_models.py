#!/usr/bin/env python3
"""
benchmark_models.py - Run the same logs through multiple LLMs and compare.

Uses LLMDiagnoser directly (no HTTP/API overhead) to benchmark each model
on the same set of triaged logs.

Usage:
    # Compare GPT-4o-mini vs local Llama3 and Mistral (via Ollama)
    python automated_scripts/benchmark_models.py

    # Custom model list
    python automated_scripts/benchmark_models.py \
        --models openai/gpt-4o-mini local/llama3 local/mistral anthropic/claude-3-haiku-20240307

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
import json
import os
import sys
import argparse
import time
from collections import Counter
from datetime import datetime

parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, parent_dir)

from dotenv import load_dotenv
load_dotenv(os.path.join(parent_dir, ".env"))

from src.api.llm_service import LLMDiagnoser
from src.api.models import LLMProvider
from src.api.filtering import LogFilter


# ── Default model configurations ──────────────────────────────────────────

DEFAULT_MODELS = [
    "openai/gpt-4o-mini",
    "local/llama3",
    "local/mistral",
]


def parse_args():
    parser = argparse.ArgumentParser(description="Benchmark multiple LLMs on CI/CD log diagnosis")
    parser.add_argument(
        "--models", nargs="+", default=DEFAULT_MODELS,
        help="Models to benchmark in 'provider/model' format (e.g. openai/gpt-4o-mini local/llama3)",
    )
    parser.add_argument(
        "--input", default=None,
        help="Input JSON file (default: batch1_triaged.json or batch1.json)",
    )
    parser.add_argument("--limit", type=int, default=None, help="Max logs to process")
    parser.add_argument("--temperature", type=float, default=0.1)
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


def build_diagnoser(provider: LLMProvider, model: str) -> LLMDiagnoser:
    """Build an LLMDiagnoser with the right API key."""
    if provider == LLMProvider.OPENAI:
        api_key = os.getenv("OPENAI_API_KEY")
    elif provider == LLMProvider.ANTHROPIC:
        api_key = os.getenv("ANTHROPIC_API_KEY")
    else:
        api_key = None
    return LLMDiagnoser(provider=provider, model=model, api_key=api_key)


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


async def benchmark_model(provider, model, logs, temperature, max_tokens):
    """Run all logs through one model. Returns list of result dicts."""
    diagnoser = build_diagnoser(provider, model)
    label = f"{provider.value}/{model}"
    results = []

    for i, log_entry in enumerate(logs, 1):
        log_id = log_entry["log_id"]
        repo = log_entry.get("repository", "")
        workflow = log_entry.get("workflow_name", "")

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
            results.append({
                "log_id": log_id,
                "repository": repo,
                "workflow": workflow,
                "model": label,
                "error_type": diagnosis.get("error_type", "unknown"),
                "root_cause": diagnosis.get("root_cause", ""),
                "suggested_fix": diagnosis.get("suggested_fix", ""),
                "confidence_score": diagnosis.get("confidence_score", 0),
                "reasoning": diagnosis.get("reasoning", ""),
                "execution_time_ms": elapsed_ms,
                "hallucination_detected": False,  # grounding done separately
            })
            conf = diagnosis.get("confidence_score", 0)
            print(f"OK  {diagnosis.get('error_type','?')} ({conf:.0%}) [{elapsed_ms:.0f}ms]")
        else:
            print(f"FAIL  {error[:50] if error else '?'}")

        # Small delay to avoid rate limits
        await asyncio.sleep(0.3)

    return results


def compute_model_metrics(results, ground_truth=None):
    """Compute summary metrics for one model's results."""
    n = len(results)
    if n == 0:
        return {}

    avg_confidence = sum(r["confidence_score"] for r in results) / n
    avg_time = sum(r["execution_time_ms"] for r in results) / n
    error_dist = dict(Counter(r["error_type"] for r in results))

    metrics = {
        "total_logs": n,
        "avg_confidence": round(avg_confidence, 3),
        "avg_execution_time_ms": round(avg_time, 1),
        "error_type_distribution": error_dist,
    }

    # If ground truth is available, compute accuracy
    if ground_truth:
        gt_map = {a["log_id"]: a for a in ground_truth}
        type_correct = 0
        root_correct = 0
        matched = 0
        for r in results:
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

    header = f"  {'Model':<35} {'Logs':>5} {'Accuracy':>9} {'Confidence':>11} {'Avg Time':>10}"
    print(header)
    print("  " + "-" * 76)

    for model_label, m in all_metrics.items():
        acc = m.get("error_type_accuracy")
        acc_str = f"{acc:.1%}" if acc is not None else "N/A"
        print(
            f"  {model_label:<35} {m['total_logs']:>5} {acc_str:>9} "
            f"{m['avg_confidence']:>10.1%} {m['avg_execution_time_ms']:>8.0f}ms"
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
    print(f"  Temperature: {args.temperature}")
    print()

    with open(input_file) as f:
        logs = json.load(f)
    if args.limit:
        logs = logs[: args.limit]
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

    # ── Run each model ────────────────────────────────────────────────
    all_results = {}
    all_metrics = {}

    for model_spec in args.models:
        provider, model_name = parse_model_spec(model_spec)
        label = f"{provider.value}/{model_name}"

        print("-" * 70)
        print(f"  Benchmarking: {label}")
        print("-" * 70)

        try:
            results = await benchmark_model(
                provider, model_name, logs, args.temperature, args.max_tokens,
            )
        except Exception as e:
            print(f"  ERROR: Model {label} failed entirely: {e}")
            results = []

        all_results[label] = results

        # Save per-model results
        safe_name = model_spec.replace("/", "_")
        model_file = os.path.join(out_dir, f"results_{safe_name}.json")
        with open(model_file, "w") as f:
            json.dump(results, f, indent=2)

        # Compute metrics
        metrics = compute_model_metrics(results, ground_truth)
        all_metrics[label] = metrics

        print(f"\n  {label}: {len(results)} diagnosed, avg confidence {metrics.get('avg_confidence', 0):.1%}, avg time {metrics.get('avg_execution_time_ms', 0):.0f}ms")
        print()

    # ── Comparison report ─────────────────────────────────────────────
    report = {
        "timestamp": timestamp,
        "input_file": input_file,
        "total_logs": len(logs),
        "temperature": args.temperature,
        "models": all_metrics,
    }
    report_file = os.path.join(out_dir, "comparison_report.json")
    with open(report_file, "w") as f:
        json.dump(report, f, indent=2)

    print_comparison_table(all_metrics)

    print(f"  Results saved to: {out_dir}/")
    print()


if __name__ == "__main__":
    asyncio.run(main())
