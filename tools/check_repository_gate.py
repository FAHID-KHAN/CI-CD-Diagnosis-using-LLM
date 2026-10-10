#!/usr/bin/env python3
"""Run the repository inclusion gate from the evaluation plan (§3.1).

A repository is kept only when all four criteria hold:

1. at least 30 failed runs still have downloadable logs;
2. at least half of the inspected runs concern build, test, dependency,
   configuration or environment failures;
3. at least 15 cases can be linked to a repair; and
4. the cases are not dominated by one repeated error or workflow.

Criteria 2 and 3 cannot be read off the runs listing, so this tool derives them:
the job type from the failing step, and the repair from the next passing run of
the same workflow on the same branch.

Run it on the repository most likely to fail first. Nothing here looks at model
output, and a repository must never be chosen by how well a model scores on it.

    python tools/check_repository_gate.py gradle/gradle --inspect 30
"""

from __future__ import annotations

import argparse
import collections
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from src.data_collection.data_collection import GitHubActionsCollector
from tools.scout_repositories import is_bot_run

API = "https://api.github.com"

# Job classification. Excluded patterns are tested first, because a job named
# "Build docs" is a documentation job, not a build job. Matching is on the job
# name and the name of the step that actually failed — the runs API does not
# expose the underlying shell command, so these names are a proxy and the
# printed breakdown is meant to be spot-checked.
EXCLUDED_PATTERNS = (
    ("docs", ("doc", "javadoc", "sphinx", "mkdocs", "readme", "changelog")),
    (
        "lint_format",
        (
            "lint",
            "flake8",
            "eslint",
            "prettier",
            "format",
            "style",
            "checkstyle",
            "ruff",
            "black",
            "isort",
            "spotless",
            "clippy",
        ),
    ),
    ("spell", ("spell", "codespell", "typo")),
    (
        "admin_other",
        (
            "commit message",
            "commit prefix",
            "conventional commit",
            "pr title",
            "label",
            "stale",
            "triage",
            "codeql",
            "scorecard",
            "license",
            "contributor",
            "welcome",
            "greet",
        ),
    ),
)

IN_SCOPE_PATTERNS = (
    "build",
    "compile",
    "assemble",
    "package",
    "gradle",
    "maven",
    "mvn",
    "make",
    "test",
    "pytest",
    "junit",
    "jest",
    "spec",
    "unittest",
    "integration",
    "e2e",
    "install",
    "dependenc",
    "resolve",
    "npm ci",
    "pip install",
    "bundle",
    "setup",
    "environment",
    "docker",
    "container",
    "provision",
    "sanity",
    "check",
)

IN_SCOPE = "build_test"
UNKNOWN = "unclassified"

# A repair should be a small, targeted follow-up. A branch that moved by dozens
# of commits before passing is not evidence of what fixed this failure.
MAX_REPAIR_COMMITS = 10

# GitHub's workflow-runs listing is not stable: identical requests minutes apart
# have returned pages of runs months apart. Runs older than the log-retention
# window are therefore dropped explicitly rather than trusted to be recent, and
# the inspected date range is printed so a stale page is visible.
DEFAULT_MAX_AGE_DAYS = 80


def classify(job_name: str, step_name: str) -> str:
    """Bucket a failed job from its name and the name of the step that failed."""
    text = f"{job_name} {step_name}".lower()
    for bucket, patterns in EXCLUDED_PATTERNS:
        if any(pattern in text for pattern in patterns):
            return bucket
    if any(pattern in text for pattern in IN_SCOPE_PATTERNS):
        return IN_SCOPE
    return UNKNOWN


def api_get(session: requests.Session, url: str, **params):
    try:
        response = session.get(url, params=params or None, timeout=30)
    except requests.RequestException:
        return None
    return response.json() if response.status_code == 200 else None


def log_available(session: requests.Session, owner: str, repo: str, run_id: int) -> bool:
    """Check the log endpoint without downloading the archive."""
    url = f"{API}/repos/{owner}/{repo}/actions/runs/{run_id}/logs"
    try:
        response = session.get(url, timeout=30, stream=True)
        available = response.status_code == 200
        response.close()
        return available
    except requests.RequestException:
        return False


def failing_step(session: requests.Session, owner: str, repo: str, run_id: int):
    """Return (job name, failing step name, job_count) for the first failed job.

    A run can fail with no jobs at all -- a workflow-level or startup failure.
    Those produce no log and nothing to diagnose, so the job count is returned
    and the caller drops them rather than counting them against the repository.
    """
    payload = api_get(session, f"{API}/repos/{owner}/{repo}/actions/runs/{run_id}/jobs", per_page=50)
    if not payload:
        return "", "", 0
    jobs = payload.get("jobs", []) or []
    for job in jobs:
        if job.get("conclusion") != "failure":
            continue
        for step in job.get("steps", []) or []:
            if step.get("conclusion") == "failure":
                return job.get("name", ""), step.get("name", ""), len(jobs)
        return job.get("name", ""), "", len(jobs)
    return "", "", len(jobs)


def find_repair(session: requests.Session, owner: str, repo: str, run: dict) -> Optional[dict]:
    """Find the next passing run of the same workflow and branch, and the diff."""
    workflow_id = run.get("workflow_id")
    branch = run.get("head_branch")
    if not workflow_id or not branch:
        return None
    payload = api_get(
        session,
        f"{API}/repos/{owner}/{repo}/actions/workflows/{workflow_id}/runs",
        branch=branch,
        status="success",
        per_page=20,
    )
    if not payload:
        return None
    later = [
        item for item in payload.get("workflow_runs", []) if item.get("created_at", "") > run.get("created_at", "")
    ]
    if not later:
        return None
    passing = min(later, key=lambda item: item["created_at"])

    compare = api_get(session, f"{API}/repos/{owner}/{repo}/compare/{run['head_sha']}...{passing['head_sha']}")
    if not compare:
        # A fork's head commit is often unreachable from the base repository.
        return {"passing_run_id": passing["id"], "commits": None, "files": None, "note": "diff unavailable"}
    return {
        "passing_run_id": passing["id"],
        "commits": compare.get("total_commits"),
        "files": len(compare.get("files", []) or []),
        "url": compare.get("html_url", ""),
    }


def inspect(owner: str, repo: str, inspect_count: int, token: str, max_age_days: int) -> dict:
    session = requests.Session()
    session.headers.update({"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"})

    collector = GitHubActionsCollector(token)
    runs = collector.get_workflow_runs(owner, repo, 100)
    real_runs = [run for run in runs if not is_bot_run(run)]

    cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
    recent, too_old = [], 0
    for run in sorted(real_runs, key=lambda item: item.get("created_at", ""), reverse=True):
        try:
            when = datetime.fromisoformat(run.get("created_at", "").replace("Z", "+00:00"))
        except ValueError:
            continue
        if when < cutoff:
            too_old += 1
            continue
        recent.append(run)
    # Over-sample: runs with no jobs are dropped below, so more than
    # inspect_count candidates are needed to reach inspect_count usable cases.
    selected = recent

    cases = []
    no_jobs = 0
    for run in selected:
        if len(cases) >= inspect_count:
            break
        print(f"  [{len(cases) + 1}/{inspect_count}] run {run['id']} ...", end="\r", flush=True)
        job_name, step_name, job_count = failing_step(session, owner, repo, run["id"])
        if job_count == 0:
            # Nothing executed, so there is no log and no failure to diagnose.
            no_jobs += 1
            continue
        repair = find_repair(session, owner, repo, run)
        linked = bool(repair and repair.get("commits") is not None and repair["commits"] <= MAX_REPAIR_COMMITS)
        cases.append(
            {
                "run_id": run["id"],
                "workflow": run.get("name", ""),
                "branch": run.get("head_branch", ""),
                "job": job_name,
                "failing_step": step_name,
                "classification": classify(job_name, step_name),
                "log_available": log_available(session, owner, repo, run["id"]),
                "repair": repair,
                "repair_linked": linked,
            }
        )
    print(" " * 60, end="\r")
    inspected_ids = {case["run_id"] for case in cases}
    dates = sorted(run.get("created_at", "")[:10] for run in selected if run["id"] in inspected_ids)
    return {
        "repository": f"{owner}/{repo}",
        "inspected": len(cases),
        "bot_runs_skipped": len(runs) - len(real_runs),
        "too_old_skipped": too_old,
        "no_job_skipped": no_jobs,
        "candidates_available": len(recent),
        "max_age_days": max_age_days,
        "date_range": [dates[0], dates[-1]] if dates else None,
        "cases": cases,
    }


def evaluate(result: dict, min_logs: int, min_repairs: int) -> dict:
    cases = result["cases"]
    inspected = len(cases)
    with_logs = sum(1 for case in cases if case["log_available"])
    in_scope = sum(1 for case in cases if case["classification"] == IN_SCOPE)
    linked = sum(1 for case in cases if case["repair_linked"])
    workflows = collections.Counter(case["workflow"] for case in cases)
    top_workflow, top_count = workflows.most_common(1)[0] if workflows else ("", 0)

    criteria = [
        (
            "1  Failed runs with downloadable logs",
            f"{with_logs} / {inspected}",
            with_logs >= min_logs,
            f"need >= {min_logs}",
        ),
        (
            "2  Build, test, dependency, config or environment",
            f"{in_scope} / {inspected}",
            inspected > 0 and in_scope * 2 >= inspected,
            "need >= half",
        ),
        ("3  Cases linkable to a repair", f"{linked} / {inspected}", linked >= min_repairs, f"need >= {min_repairs}"),
        (
            "4  Not dominated by one workflow",
            f"{top_count} / {inspected} ({top_workflow[:28]})",
            inspected > 0 and top_count * 2 <= inspected,
            "need <= half",
        ),
    ]
    result["criteria"] = [
        {"criterion": name, "value": value, "passed": passed, "requirement": need}
        for name, value, passed, need in criteria
    ]
    result["passed"] = all(passed for _, _, passed, _ in criteria)
    result["classification_counts"] = dict(collections.Counter(case["classification"] for case in cases))
    return result


def report(result: dict) -> None:
    print()
    print("=" * 78)
    print(f"  REPOSITORY GATE — {result['repository']}")
    print("=" * 78)
    window = result.get("date_range")
    print(
        f"  {result['inspected']} non-bot failed runs inspected" + (f", {window[0]} to {window[1]}" if window else "")
    )
    print(
        f"  skipped: {result['bot_runs_skipped']} bot runs, "
        f"{result.get('too_old_skipped', 0)} older than {result.get('max_age_days')} days, "
        f"{result.get('no_job_skipped', 0)} with no job executed"
    )
    print(f"  candidate pool after filtering: {result.get('candidates_available', 0)} runs")
    print()
    for item in result["criteria"]:
        mark = "PASS" if item["passed"] else "FAIL"
        print(f"  {item['criterion']:<52}{item['value']:>14}  {mark}  ({item['requirement']})")
    print()
    print(f"  VERDICT: {'PASS — repository is usable' if result['passed'] else 'FAIL — replace this repository'}")
    print()
    print("  Job types among the inspected failures:")
    for name, count in sorted(result["classification_counts"].items(), key=lambda kv: -kv[1]):
        print(f"    {name:<16}{count:>4}")
    print()
    print("  Spot-check the classification (job / failing step -> bucket):")
    for case in result["cases"][:8]:
        label = f"{case['job'][:28]} / {case['failing_step'][:26]}"
        print(f"    {label:<58} -> {case['classification']}")
    print()


def parse_args():
    parser = argparse.ArgumentParser(description="Run the repository inclusion gate")
    parser.add_argument("repositories", nargs="+", help="owner/repo, in the order to check")
    parser.add_argument("--inspect", type=int, default=30, help="Failed runs to inspect per repository")
    parser.add_argument("--min-logs", type=int, default=30, help="Criterion 1 threshold")
    parser.add_argument("--min-repairs", type=int, default=15, help="Criterion 3 threshold")
    parser.add_argument("--output", help="Write the full record as JSON")
    parser.add_argument(
        "--max-age-days",
        type=int,
        default=DEFAULT_MAX_AGE_DAYS,
        help="Ignore runs older than this; GitHub expires logs at about 90 days",
    )
    parser.add_argument("--stop-on-fail", action="store_true", help="Stop after the first failing repository")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    token = os.getenv("GITHUB_TOKEN")
    if not token:
        print("ERROR: GITHUB_TOKEN is missing from .env or the shell environment.")
        return 1

    results = []
    for name in args.repositories:
        if name.count("/") != 1:
            print(f"Skipping invalid repository name: {name!r}")
            continue
        owner, repo = name.split("/", 1)
        print(f"\nInspecting {name} ...")
        result = evaluate(inspect(owner, repo, args.inspect, token, args.max_age_days), args.min_logs, args.min_repairs)
        report(result)
        results.append(result)
        if args.stop_on_fail and not result["passed"]:
            print("  Stopping: this repository must be replaced before the next check.\n")
            break

    if args.output:
        payload = {
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "inspect_count": args.inspect,
            "thresholds": {
                "min_logs": args.min_logs,
                "min_repairs": args.min_repairs,
                "max_repair_commits": MAX_REPAIR_COMMITS,
                "max_age_days": args.max_age_days,
            },
            "results": results,
        }
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"  Record written to {args.output}")
    return 0 if all(item["passed"] for item in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
