#!/usr/bin/env python3
"""Measure candidate repositories before committing a study to them.

Repository choice is a methodological decision (kickoff decision D2 and action
item A3), and it should rest on measurement rather than intuition. This samples
recent failed workflow runs from each candidate and reports what actually
matters for a log-diagnosis study:

* how many failed runs are available at all, and how many still have logs;
* how long those logs are;
* how much of a log survives filtering, which is what the model receives.

That last column is the one that decides feasibility. Above roughly 3,000 lines
the filter saturates its token budget, so the model sees a fixed-size window no
matter how large the log is, and the measurement starts testing the filter
rather than the model.

Selection here is on tractability and ecosystem contrast only. Nothing in this
script looks at model output, and repositories must never be chosen by how well
a model scores on them.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from src.api.filtering import LogFilter, _count_tokens
from src.data_collection.data_collection import GitHubActionsCollector

MAX_FILTER_TOKENS = 12000

# Dependency bots and scheduled scanners produce short, near-identical logs.
# They flatter a median while contributing nothing a diagnosis study can use:
# triage deduplicates them, and they exercise none of the failure taxonomy. They
# are counted separately so a repository is judged on its real CI failures.
BOT_MARKERS = (
    "dependabot",
    "renovate",
    " - update #",
    "scorecard",
    "codeql",
    "pre-commit.ci",
)


def is_bot_run(run: dict) -> bool:
    name = (run.get("name") or "").lower()
    actor = ((run.get("triggering_actor") or {}).get("login") or "").lower()
    if any(marker in name for marker in BOT_MARKERS):
        return True
    return "dependabot" in actor or "renovate" in actor


def parse_args():
    parser = argparse.ArgumentParser(description="Measure candidate repositories for a log-diagnosis study")
    parser.add_argument("repositories", nargs="*", help="owner/repo, repeatable")
    parser.add_argument("--candidates", help="File with one owner/repo per line")
    parser.add_argument("--samples", type=int, default=4, help="Failed runs to download per repository")
    parser.add_argument("--max-lines", type=int, default=1000, help="Tractability threshold for the verdict column")
    parser.add_argument("--output", help="Write the full measurements as JSON")
    return parser.parse_args()


def load_candidates(args) -> list:
    names = list(args.repositories)
    if args.candidates:
        text = Path(args.candidates).read_text(encoding="utf-8")
        names += [line.strip() for line in text.splitlines() if line.strip() and not line.startswith("#")]
    seen, ordered = set(), []
    for name in names:
        if name.count("/") != 1:
            print(f"Skipping invalid repository name: {name!r}")
            continue
        if name not in seen:
            seen.add(name)
            ordered.append(name)
    return ordered


def measure(collector: GitHubActionsCollector, name: str, samples: int) -> dict:
    owner, repo = name.split("/", 1)
    result = {
        "repository": name,
        "error": None,
        "failed_runs_available": 0,
        "real_runs_available": 0,
        "logs_sampled": 0,
        "lines": [],
    }
    try:
        runs = collector.get_workflow_runs(owner, repo, 100)
    except RuntimeError as exc:
        result["error"] = str(exc)[:160]
        return result

    result["failed_runs_available"] = len(runs)
    real_runs = [run for run in runs if not is_bot_run(run)]
    result["real_runs_available"] = len(real_runs)
    result["workflows"] = sorted({run.get("name", "") for run in real_runs})[:8]

    for run in real_runs:
        if result["logs_sampled"] >= samples:
            break
        content = collector.download_log(owner, repo, run["id"])
        if content is None:
            continue
        raw_lines = len(content.splitlines())
        filtered = LogFilter.apply_smart_filtering(content, max_lines=500, window_size=20, max_tokens=MAX_FILTER_TOKENS)
        result["lines"].append(
            {
                "run_id": run["id"],
                "workflow": run.get("name", ""),
                "raw_lines": raw_lines,
                "kept_lines": len(filtered.splitlines()),
                "tokens": _count_tokens(filtered),
            }
        )
        result["logs_sampled"] += 1
    return result


def summarise(result: dict, max_lines: int) -> dict:
    rows = result.get("lines") or []
    if not rows:
        return {**result, "median_lines": None, "median_coverage": None, "verdict": "no sample"}
    raw = [row["raw_lines"] for row in rows]
    coverage = [row["kept_lines"] / row["raw_lines"] for row in rows if row["raw_lines"]]
    median_raw = statistics.median(raw)
    under = sum(1 for value in raw if value <= max_lines)
    workflows = len({row["workflow"] for row in rows})
    if median_raw <= max_lines and under == len(raw):
        verdict = "tractable"
    elif median_raw <= max_lines:
        verdict = f"mixed ({under}/{len(raw)} small)"
    elif median_raw <= 3000:
        verdict = "workable"
    else:
        verdict = "too large"
    return {
        **result,
        "median_lines": int(median_raw),
        "min_lines": min(raw),
        "max_lines_seen": max(raw),
        "median_coverage": round(statistics.median(coverage), 4) if coverage else None,
        "under_threshold": under,
        "distinct_workflows_sampled": workflows,
        "verdict": verdict,
    }


def main() -> int:
    args = parse_args()
    candidates = load_candidates(args)
    if not candidates:
        print("ERROR: No candidate repositories given.")
        return 1
    token = os.getenv("GITHUB_TOKEN")
    if not token:
        print("ERROR: GITHUB_TOKEN is missing from .env or the shell environment.")
        return 1

    collector = GitHubActionsCollector(token)
    results = []
    for index, name in enumerate(candidates, 1):
        print(f"[{index}/{len(candidates)}] {name} ...", flush=True)
        results.append(summarise(measure(collector, name, args.samples), args.max_lines))

    results.sort(key=lambda item: (item["median_lines"] is None, item["median_lines"] or 0))

    print()
    print("=" * 96)
    print(f"  CANDIDATE REPOSITORIES  (threshold: {args.max_lines} lines)")
    print("=" * 96)
    header = f"  {'repository':<26}{'failed':>7}{'real':>6}{'sampled':>8}" f"{'median':>9}{'model sees':>12}  verdict"
    print(header)
    print("  " + "-" * 92)
    for item in results:
        if item["error"]:
            print(f"  {item['repository']:<26}{'-':>7}{'-':>6}{'-':>8}{'-':>9}{'-':>12}  ERROR: {item['error'][:30]}")
            continue
        median = f"{item['median_lines']:,}" if item["median_lines"] is not None else "-"
        coverage = f"{item['median_coverage'] * 100:.1f}%" if item["median_coverage"] is not None else "-"
        print(
            f"  {item['repository']:<26}{item['failed_runs_available']:>7}{item['real_runs_available']:>6}"
            f"{item['logs_sampled']:>8}{median:>9}{coverage:>12}  {item['verdict']}"
        )
    print()
    print("  'failed' counts all failed runs; 'real' excludes dependency bots and scanners,")
    print("  whose short repetitive logs flatter a median but are deduplicated by triage.")
    print("  'model sees' is the share surviving the filter at " f"{MAX_FILTER_TOKENS:,} tokens; a low share means")
    print("  the measurement is dominated by the filter rather than the model.")
    print()

    if args.output:
        payload = {
            "measured_at": datetime.now(timezone.utc).isoformat(),
            "samples_per_repository": args.samples,
            "max_lines_threshold": args.max_lines,
            "filter": {"max_lines": 500, "window_size": 20, "max_tokens": MAX_FILTER_TOKENS},
            "results": results,
        }
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"  Measurements written to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
