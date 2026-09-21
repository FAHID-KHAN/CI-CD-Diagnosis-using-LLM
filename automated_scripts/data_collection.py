#!/usr/bin/env python3
"""Collect the immutable raw dataset defined by a thesis study protocol."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import logging
import os
import platform
import shutil
import sys
from collections import Counter
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from automated_scripts.study_utils import (
    atomic_write_json,
    git_commit,
    load_study_config,
    sha256_file,
    study_directory,
    utc_now,
)
from src.data_collection.data_collection import GitHubActionsCollector

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


def parse_args():
    parser = argparse.ArgumentParser(description="Collect the controlled thesis dataset")
    parser.add_argument("--study-config", default="configs/thesis_fresh_2026.yaml")
    parser.add_argument("--study-dir", default=None)
    parser.add_argument("--resume", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    token = os.environ.get("GITHUB_TOKEN", "")
    if not token:
        print("ERROR: GITHUB_TOKEN is missing from .env or the shell environment.")
        return 1

    try:
        config, config_path = load_study_config(args.study_config)
    except (OSError, ValueError) as exc:
        print(f"ERROR: Invalid study protocol: {exc}")
        return 1

    root = study_directory(config, args.study_dir)
    raw_path = root / "raw" / "logs.json"
    manifest_path = root / "collection_manifest.json"
    checksum_path = root / "checksums" / "log_content_sha256.json"
    preflight_path = root.parent / f"_preflight_{config['study_id']}" / "preflight_report.json"

    preflight_exclusions: dict[str, set[int]] = {}
    if preflight_path.exists():
        report = json.loads(preflight_path.read_text(encoding="utf-8"))
        if report.get("study_id") == config["study_id"]:
            preflight_exclusions.setdefault(report["repository"], set()).add(int(report["run_id"]))

    if args.resume:
        if not raw_path.exists() or not manifest_path.exists():
            print("ERROR: Resume requires existing raw data and collection_manifest.json.")
            return 1
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("status") == "complete":
            print("ERROR: The raw study collection is complete and immutable.")
            return 1
        logs = json.loads(raw_path.read_text(encoding="utf-8"))
    else:
        if raw_path.exists() or manifest_path.exists():
            print(f"ERROR: Study output already exists under {root}.")
            print("Use --resume only for a genuinely interrupted collection.")
            return 1
        root.mkdir(parents=True, exist_ok=True)
        shutil.copy2(config_path, root / "study_protocol.yaml")
        logs = []
        manifest = {
            "schema_version": 1,
            "study_id": config["study_id"],
            "status": "collecting",
            "collection_started_at": utc_now(),
            "collection_completed_at": None,
            "source": "GitHub Actions API",
            "study_config_source": str(config_path),
            "study_config_sha256": sha256_file(config_path),
            "git_commit": git_commit(),
            "runtime": {
                "python": platform.python_version(),
                "requests": importlib.metadata.version("requests"),
                "platform": platform.platform(),
            },
            "repositories": config["repositories"],
            "repository_results": [],
            "collection_errors": [],
            "preflight_exclusions": [
                {"repository": repository, "run_id": run_id}
                for repository, run_ids in preflight_exclusions.items()
                for run_id in sorted(run_ids)
            ],
            "raw_output": str(raw_path),
        }
        atomic_write_json(manifest_path, manifest)

    def save_progress():
        unique = {entry["log_id"]: entry for entry in logs}
        logs[:] = list(unique.values())
        atomic_write_json(raw_path, logs)
        atomic_write_json(checksum_path, {entry["log_id"]: entry["log_sha256"] for entry in logs})
        manifest["total_logs_collected"] = len(logs)
        manifest["unique_repositories"] = len({entry["repository"] for entry in logs})
        atomic_write_json(manifest_path, manifest)

    collector = GitHubActionsCollector(token)
    try:
        for index, item in enumerate(config["repositories"], 1):
            repository = item["name"]
            owner, repo = repository.split("/", 1)
            target = item["max_logs"]
            existing_ids = {
                int(entry["run_id"])
                for entry in logs
                if entry.get("repository") == repository and entry.get("run_id") is not None
            }
            remaining = max(0, target - len(existing_ids))
            excluded_ids = existing_ids | preflight_exclusions.get(repository, set())
            print(f"[{index}/{len(config['repositories'])}] {repository}: need {remaining}/{target}")
            try:
                new_logs = collector.collect_logs_from_repo(owner, repo, remaining, excluded_ids) if remaining else []
                logs.extend(new_logs)
                manifest["collection_errors"] = [
                    error for error in manifest["collection_errors"] if error["repository"] != repository
                ]
                manifest["repository_results"] = [
                    result for result in manifest["repository_results"] if result["repository"] != repository
                ]
                manifest["repository_results"].append(
                    {
                        "repository": repository,
                        "requested": target,
                        "collected": len(existing_ids) + len(new_logs),
                        "completed_at": utc_now(),
                    }
                )
            except Exception as exc:
                print(f"  FAILED: {exc}")
                manifest["collection_errors"].append(
                    {
                        "repository": repository,
                        "error_type": type(exc).__name__,
                        "message": str(exc),
                        "timestamp": utc_now(),
                    }
                )
            save_progress()
    except KeyboardInterrupt:
        manifest["status"] = "interrupted"
        manifest["interrupted_at"] = utc_now()
        save_progress()
        print("\nCollection interrupted; progress was saved. Resume with --resume.")
        return 130

    counts = Counter(entry["repository"] for entry in logs)
    shortfalls = [
        {"repository": item["name"], "requested": item["max_logs"], "collected": counts[item["name"]]}
        for item in config["repositories"]
        if counts[item["name"]] < item["max_logs"]
    ]
    save_progress()
    manifest["collection_shortfalls"] = shortfalls
    manifest["status"] = (
        "complete" if not shortfalls and not manifest["collection_errors"] else "complete_with_warnings"
    )
    manifest["collection_completed_at"] = utc_now()
    manifest["raw_file_sha256"] = sha256_file(raw_path)
    atomic_write_json(manifest_path, manifest)

    print(f"Collected {len(logs)} logs from {len(counts)} repositories into {raw_path}")
    if shortfalls or manifest["collection_errors"]:
        print("Collection completed with warnings; inspect collection_manifest.json before triage.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
