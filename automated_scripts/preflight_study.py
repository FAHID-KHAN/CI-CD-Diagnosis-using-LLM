#!/usr/bin/env python3
"""Validate a thesis study configuration and optionally download one smoke-test log."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

from dotenv import load_dotenv

parent_dir = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(parent_dir / "src"))
sys.path.insert(0, str(parent_dir))
load_dotenv(parent_dir / ".env")

from data_collection.data_collection import GitHubActionsCollector
from automated_scripts.study_utils import (
    atomic_write_json,
    git_commit,
    load_study_config,
    study_directory,
    utc_now,
)


def parse_args():
    parser = argparse.ArgumentParser(description="Preflight a fresh thesis dataset")
    parser.add_argument("--study-config", required=True)
    parser.add_argument("--study-dir", default=None)
    parser.add_argument("--live", action="store_true",
                        help="Download one failed workflow log into an isolated preflight directory")
    parser.add_argument("--repository", default=None,
                        help="Configured owner/repo to use for the live check")
    parser.add_argument("--overwrite-preflight", action="store_true")
    parser.add_argument("--allow-existing-output", action="store_true",
                        help="Permit existing raw data while validating an interrupted resume")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    checks = []

    def check(name: str, passed: bool, detail: str):
        checks.append({"name": name, "passed": passed, "detail": detail})
        marker = "PASS" if passed else "FAIL"
        print(f"[{marker}] {name}: {detail}")

    try:
        config, config_path = load_study_config(args.study_config)
        check("study protocol", True, f"{config['study_id']} ({len(config['repositories'])} repositories)")
    except (OSError, ValueError) as exc:
        check("study protocol", False, str(exc))
        return 1

    root = study_directory(config, args.study_dir)
    raw_path = root / "raw" / "logs.json"
    check("python", sys.version_info >= (3, 11), sys.version.split()[0])
    token = os.environ.get("GITHUB_TOKEN", "")
    check("GitHub token", bool(token), "configured" if token else "missing")
    output_ok = not raw_path.exists() or args.allow_existing_output
    check("final output", output_ok,
          "available" if not raw_path.exists() else
          ("existing interrupted output allowed" if args.allow_existing_output else f"already exists: {raw_path}"))

    free_gib = shutil.disk_usage(parent_dir).free / 1024**3
    check("disk space", free_gib >= 5, f"{free_gib:.1f} GiB free")
    target = sum(item["max_logs"] for item in config["repositories"])
    check("declared target", target == config.get("target_raw_logs"),
          f"repository total={target}, declared={config.get('target_raw_logs')}")

    configured_names = {item["name"] for item in config["repositories"]}
    repository = args.repository or config["repositories"][0]["name"]
    check("smoke repository", repository in configured_names, repository)

    failed = [item for item in checks if not item["passed"]]
    if failed:
        print(f"\nPreflight blocked by {len(failed)} failed check(s).")
        return 1

    if not args.live:
        print("\nOffline preflight passed. Re-run with --live for the one-log GitHub check.")
        return 0

    preflight_dir = root.parent / f"_preflight_{config['study_id']}"
    sample_path = preflight_dir / "sample_log.json"
    if sample_path.exists() and not args.overwrite_preflight:
        report_path = preflight_dir / "preflight_report.json"
        if report_path.exists():
            with report_path.open(encoding="utf-8") as handle:
                previous = json.load(handle)
            if previous.get("study_id") == config["study_id"]:
                print(f"[PASS] live GitHub check: reusing {previous.get('log_id', 'existing sample')}")
                print(f"Preflight sample: {sample_path}")
                return 0
        print(f"ERROR: Preflight sample exists without a matching valid report: {sample_path}")
        return 1

    owner, repo = repository.split("/", 1)
    print(f"\nDownloading one failed workflow log from {repository}...")
    try:
        logs = GitHubActionsCollector(token).collect_logs_from_repo(owner, repo, num_logs=1)
    except Exception as exc:
        print(f"ERROR: Live GitHub check failed: {exc}")
        return 1
    if not logs:
        print("ERROR: GitHub returned no downloadable failed workflow log.")
        return 1

    required = {"log_id", "repository", "run_id", "url", "log_content", "log_sha256", "collected_at"}
    missing = sorted(required - set(logs[0]))
    if missing:
        print(f"ERROR: Smoke-test record is missing: {', '.join(missing)}")
        return 1

    atomic_write_json(sample_path, logs[0])
    atomic_write_json(preflight_dir / "preflight_report.json", {
        "schema_version": 1,
        "study_id": config["study_id"],
        "completed_at": utc_now(),
        "repository": repository,
        "log_id": logs[0]["log_id"],
        "run_id": logs[0]["run_id"],
        "url": logs[0]["url"],
        "log_sha256": logs[0]["log_sha256"],
        "line_count": len(logs[0]["log_content"].splitlines()),
        "git_commit": git_commit(),
        "study_config": str(config_path),
        "checks": checks,
        "note": "Isolated smoke-test record; its run ID is automatically excluded from the final cohort.",
    })
    print(f"[PASS] live GitHub check: {logs[0]['log_id']}")
    print(f"Preflight sample: {sample_path}")
    print("This sample run ID is isolated and will be excluded from the final cohort.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
