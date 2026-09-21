import sys
import os
import json
import argparse
import importlib.metadata
import logging
import platform
import shutil
from collections import Counter
from pathlib import Path
from dotenv import load_dotenv

parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(parent_dir, 'src'))
load_dotenv(os.path.join(parent_dir, '.env'))

from log_setup import setup_logging
from data_collection.data_collection import GitHubActionsCollector

from automated_scripts.pipeline_manifest import record_step
from automated_scripts.study_utils import (
    atomic_write_json,
    git_commit,
    load_study_config,
    sha256_file,
    study_directory,
    utc_now,
)

setup_logging()
logger = logging.getLogger(__name__)

# (owner, repo, logs_per_repo)
TARGET_REPOS = [
    ("tensorflow", "tensorflow", 10),
    ("pytorch", "pytorch", 10),
    ("scikit-learn", "scikit-learn", 10),
    ("pallets", "flask", 5),
    ("django", "django", 5),
    ("facebook", "react", 10),
    ("vercel", "next.js", 10),
    ("vuejs", "core", 5),
    ("angular", "angular", 5),
    ("spring-projects", "spring-boot", 5),
    ("elastic", "elasticsearch", 5),
    ("apache", "kafka", 5),
    ("kubernetes", "kubernetes", 5),
    ("hashicorp", "terraform", 5),
    ("rust-lang", "rust", 5),
    ("docker", "compose", 5),
    ("gradle", "gradle", 5),
]

AUTO_DISCOVER_LOGS = 0


def parse_args():
    parser = argparse.ArgumentParser(description="Collect failed CI/CD logs from GitHub Actions")
    parser.add_argument("--per-repo", type=int, default=None,
                        help="Override logs-per-repo for every target repo")
    parser.add_argument("--auto-discover", type=int, default=AUTO_DISCOVER_LOGS,
                        help="Extra logs via GitHub search across random repos")
    parser.add_argument("--output", type=str, default=None,
                        help="Output JSON path (default: data/raw_logs/github_actions/batch1.json)")
    parser.add_argument("--repos", type=str, nargs="*", default=None,
                        help="Specific owner/repo pairs (e.g. facebook/react vuejs/core)")
    parser.add_argument("--study-config", type=str, default=None,
                        help="YAML study protocol; enables immutable thesis-study storage")
    parser.add_argument("--study-dir", type=str, default=None,
                        help="Override the data/studies/<study_id> output directory")
    parser.add_argument("--resume", action="store_true",
                        help="Resume an interrupted study collection")
    return parser.parse_args()


def main():
    args = parse_args()

    if args.study_dir and not args.study_config:
        print("ERROR: --study-dir requires --study-config.")
        sys.exit(1)
    if args.study_config and (args.output or args.repos or args.per_repo or args.auto_discover):
        print("ERROR: --study-config cannot be combined with legacy collection overrides.")
        sys.exit(1)

    github_token = os.environ.get("GITHUB_TOKEN", "")
    if not github_token:
        print("ERROR: GITHUB_TOKEN is missing.")
        print("  Add it to .env or export it in your shell.")
        sys.exit(1)

    print("=" * 70)
    print("Multi-Repo Data Collection")
    print("=" * 70)
    print()

    collector = GitHubActionsCollector(github_token=github_token)
    all_logs = []

    study_config = None
    study_config_path = None
    study_dir = None
    study_manifest = None
    preflight_exclusions = {}

    if args.study_config:
        try:
            study_config, study_config_path = load_study_config(args.study_config)
        except (OSError, ValueError) as exc:
            print(f"ERROR: Invalid study config: {exc}")
            sys.exit(1)
        study_dir = study_directory(study_config, args.study_dir)
        output_file = str(study_dir / "raw" / "logs.json")
        manifest_path = study_dir / "collection_manifest.json"
        preflight_report_path = study_dir.parent / f"_preflight_{study_config['study_id']}" / "preflight_report.json"
        if preflight_report_path.exists():
            with preflight_report_path.open(encoding="utf-8") as handle:
                preflight_report = json.load(handle)
            if preflight_report.get("study_id") == study_config["study_id"]:
                preflight_exclusions.setdefault(preflight_report["repository"], set()).add(
                    int(preflight_report["run_id"])
                )
        repos = []
        for item in study_config["repositories"]:
            owner, repo = item["name"].split("/", 1)
            repos.append((owner, repo, item["max_logs"]))

        if Path(output_file).exists() and not args.resume:
            print(f"ERROR: Study raw data already exists: {output_file}")
            print("  Use --resume only for a genuinely interrupted collection.")
            sys.exit(1)
        if args.resume:
            if not Path(output_file).exists() or not manifest_path.exists():
                print("ERROR: Cannot resume without both raw logs and collection_manifest.json.")
                sys.exit(1)
            with manifest_path.open(encoding="utf-8") as handle:
                study_manifest = json.load(handle)
            if study_manifest.get("status") == "complete":
                print("ERROR: This study collection is already complete and immutable.")
                sys.exit(1)
            with open(output_file, encoding="utf-8") as handle:
                all_logs = json.load(handle)
        else:
            study_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(study_config_path, study_dir / "study_protocol.yaml")
            study_manifest = {
                "schema_version": 1,
                "study_id": study_config["study_id"],
                "status": "collecting",
                "collection_started_at": utc_now(),
                "collection_completed_at": None,
                "source": "GitHub Actions API",
                "study_config_source": str(study_config_path),
                "study_config_sha256": sha256_file(study_config_path),
                "git_commit": git_commit(),
                "runtime": {
                    "python": platform.python_version(),
                    "requests": importlib.metadata.version("requests"),
                    "platform": platform.platform(),
                },
                "repositories": study_config["repositories"],
                "repository_results": [],
                "collection_errors": [],
                "preflight_exclusions": [
                    {"repository": repository, "run_id": run_id}
                    for repository, run_ids in preflight_exclusions.items()
                    for run_id in sorted(run_ids)
                ],
                "raw_output": output_file,
            }
            atomic_write_json(manifest_path, study_manifest)
    elif args.repos:
        repos = []
        for r in args.repos:
            parts = r.split("/")
            if len(parts) != 2:
                print(f"  Skipping invalid format '{r}' (expected owner/repo)")
                continue
            per = args.per_repo if args.per_repo else 10
            repos.append((parts[0], parts[1], per))
    else:
        repos = TARGET_REPOS
        if args.per_repo:
            repos = [(owner, repo, args.per_repo) for owner, repo, _ in repos]

    total_target = sum(n for _, _, n in repos) + args.auto_discover
    print(f"Target: ~{total_target} logs from {len(repos)} repos")
    print()

    # Resolve legacy output path early so partial saves work.
    if not study_config:
        if args.output:
            output_file = args.output
        else:
            output_dir = os.path.join(parent_dir, 'data', 'raw_logs', 'github_actions')
            os.makedirs(output_dir, exist_ok=True)
            output_file = os.path.join(output_dir, 'batch1.json')

    # Back up existing data before overwriting so baselines survive re-collection
    if not study_config and os.path.exists(output_file):
        from datetime import datetime as _dt
        backup_name = output_file.replace('.json', f'_backup_{_dt.now().strftime("%Y%m%d_%H%M%S")}.json')
        shutil.copy2(output_file, backup_name)
        logger.info("Backed up existing %s -> %s", output_file, os.path.basename(backup_name))
        print(f"  Backed up existing data to {os.path.basename(backup_name)}")
        print()

    def _save(logs, label=""):
        """Deduplicate and write to disk."""
        seen_ids = set()
        unique = []
        for log in logs:
            if log['log_id'] not in seen_ids:
                seen_ids.add(log['log_id'])
                unique.append(log)
        if study_config:
            atomic_write_json(Path(output_file), unique)
            checksums = {log["log_id"]: log["log_sha256"] for log in unique}
            atomic_write_json(study_dir / "checksums" / "log_content_sha256.json", checksums)
            study_manifest["total_logs_collected"] = len(unique)
            study_manifest["unique_repositories"] = len({log["repository"] for log in unique})
            atomic_write_json(study_dir / "collection_manifest.json", study_manifest)
        else:
            with open(output_file, 'w') as f:
                json.dump(unique, f, indent=2)
        if label:
            logger.info("%s  Saved %d unique logs to %s", label, len(unique), output_file)
        return unique

    try:
        for i, (owner, repo, num_logs) in enumerate(repos, 1):
            repo_name = f"{owner}/{repo}"
            existing_ids = {
                int(log["run_id"]) for log in all_logs
                if log.get("repository") == repo_name and log.get("run_id") is not None
            }
            excluded_ids = existing_ids | preflight_exclusions.get(repo_name, set())
            remaining = max(0, num_logs - len(existing_ids))
            print(f"[{i}/{len(repos)}] {repo_name} (need {remaining}, target {num_logs})...", end=" ")
            try:
                logs = collector.collect_logs_from_repo(
                    owner, repo, num_logs=remaining, exclude_run_ids=excluded_ids
                ) if remaining else []
                all_logs.extend(logs)
                print(f"OK ({len(logs)} logs, total: {len(all_logs)})")
                if study_config:
                    study_manifest["repository_results"] = [
                        result for result in study_manifest["repository_results"]
                        if result.get("repository") != repo_name
                    ]
                    study_manifest["repository_results"].append({
                        "repository": repo_name,
                        "requested": num_logs,
                        "collected": len(existing_ids) + len(logs),
                        "completed_at": utc_now(),
                    })
            except Exception as e:
                print(f"FAILED: {e}")
                if study_config:
                    study_manifest["collection_errors"].append({
                        "repository": repo_name,
                        "error_type": type(e).__name__,
                        "message": str(e),
                        "timestamp": utc_now(),
                    })
            # Save after every repo so progress is never lost
            _save(all_logs)

        if args.auto_discover > 0:
            print(f"\nAuto-discovering {args.auto_discover} additional logs...")
            try:
                extra_logs = collector.collect_logs(num_logs=args.auto_discover)
                all_logs.extend(extra_logs)
                print(f"  Got {len(extra_logs)} additional logs")
            except Exception as e:
                print(f"  Auto-discovery failed: {e}")

    except KeyboardInterrupt:
        print("\n\nInterrupted! Saving partial results...")
        all_logs = _save(all_logs, "[partial]")
        if study_config:
            study_manifest["status"] = "interrupted"
            study_manifest["interrupted_at"] = utc_now()
            atomic_write_json(study_dir / "collection_manifest.json", study_manifest)
        _print_stats(all_logs, output_file)
        sys.exit(1)

    # Final deduplicate + save
    all_logs = _save(all_logs)

    if study_config:
        shortfalls = []
        counts = Counter(log["repository"] for log in all_logs)
        for owner, repo, requested in repos:
            repository = f"{owner}/{repo}"
            if counts.get(repository, 0) < requested:
                shortfalls.append({
                    "repository": repository,
                    "requested": requested,
                    "collected": counts.get(repository, 0),
                })
        study_manifest["collection_shortfalls"] = shortfalls
        study_manifest["status"] = "complete" if not shortfalls and not study_manifest["collection_errors"] else "complete_with_warnings"
        study_manifest["collection_completed_at"] = utc_now()
        study_manifest["raw_file_sha256"] = sha256_file(Path(output_file))
        atomic_write_json(study_dir / "collection_manifest.json", study_manifest)

    _print_stats(all_logs, output_file)

    # Record in pipeline manifest
    repo_counts = Counter(log['repository'] for log in all_logs)
    record_step(
        step="collect",
        config={"repos": len(repos), "auto_discover": args.auto_discover},
        inputs={"source": "GitHub Actions API"},
        outputs={"total_logs": len(all_logs), "unique_repos": len(repo_counts), "file": output_file},
        notes=f"Collected {len(all_logs)} logs from {len(repo_counts)} repos",
    )


def _print_stats(all_logs, output_file):
    repo_counts = Counter(log['repository'] for log in all_logs)
    workflow_counts = Counter(log['workflow_name'] for log in all_logs)

    print()
    print("=" * 70)
    print("Collection Statistics")
    print("=" * 70)
    print(f"Total logs collected : {len(all_logs)}")
    print(f"Unique repositories  : {len(repo_counts)}")
    print(f"Unique workflows     : {len(workflow_counts)}")
    print()

    print("Top 10 repositories:")
    for repo, count in repo_counts.most_common(10):
        print(f"  - {repo}: {count}")

    print()
    print("Top 10 workflows:")
    for workflow, count in workflow_counts.most_common(10):
        print(f"  - {workflow or '(unnamed)'}: {count}")

    if all_logs:
        sample = all_logs[0]
        print()
        print("=" * 70)
        print("Sample Log Preview")
        print("=" * 70)
        print(f"Repository : {sample['repository']}")
        print(f"Workflow   : {sample['workflow_name']}")
        print(f"URL        : {sample['url']}")
        print(f"Content    : {sample['log_content'][:500]}...")

    print()
    print("=" * 70)
    print(f"Done. {len(all_logs)} logs from {len(repo_counts)} repos saved to {output_file}")
    print("=" * 70)


if __name__ == "__main__":
    main()
