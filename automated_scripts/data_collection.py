import sys
import os
import json
import argparse
import logging
from collections import Counter
from dotenv import load_dotenv

parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(parent_dir, 'src'))
load_dotenv(os.path.join(parent_dir, '.env'))

from log_setup import setup_logging
from data_collection.data_collection import GitHubActionsCollector

from automated_scripts.pipeline_manifest import record_step

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
    return parser.parse_args()


def main():
    args = parse_args()

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

    if args.repos:
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

    # Resolve output path early so partial saves work
    if args.output:
        output_file = args.output
    else:
        output_dir = os.path.join(parent_dir, 'data', 'raw_logs', 'github_actions')
        os.makedirs(output_dir, exist_ok=True)
        output_file = os.path.join(output_dir, 'batch1.json')

    # Back up existing data before overwriting so baselines survive re-collection
    if os.path.exists(output_file):
        from datetime import datetime as _dt
        backup_name = output_file.replace('.json', f'_backup_{_dt.now().strftime("%Y%m%d_%H%M%S")}.json')
        import shutil
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
        with open(output_file, 'w') as f:
            json.dump(unique, f, indent=2)
        if label:
            logger.info("%s  Saved %d unique logs to %s", label, len(unique), output_file)
        return unique

    try:
        for i, (owner, repo, num_logs) in enumerate(repos, 1):
            print(f"[{i}/{len(repos)}] {owner}/{repo} (up to {num_logs})...", end=" ")
            try:
                logs = collector.collect_logs_from_repo(owner, repo, num_logs=num_logs)
                all_logs.extend(logs)
                print(f"OK ({len(logs)} logs, total: {len(all_logs)})")
            except Exception as e:
                print(f"FAILED: {e}")
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
        _print_stats(all_logs, output_file)
        sys.exit(1)

    # Final deduplicate + save
    all_logs = _save(all_logs)

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