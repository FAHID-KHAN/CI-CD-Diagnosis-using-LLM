import sys
import os


parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(parent_dir, 'src'))

from data_collection.data_collection import GitHubActionsCollector
import json

print("="*70)
print("📦 Starting Data Collection")
print("="*70)
print()

# Your GitHub token
github_token = "git_token"

# Create collector
print("✓ Initializing GitHub Actions collector...")
collector = GitHubActionsCollector(github_token=github_token)

# Collect logs
print("🔍 Collecting 50 failed workflow logs...")
print("   This will take 5-10 minutes, please wait...")
print()

try:
    owner = "tensorflow"
    repo= "tensorflow"

    print(f"🔍 Collecting 10 failed workflow logs from {owner}/{repo}...")
    print("   This will take a few minutes, please wait...")
    print()
    logs = collector.collect_logs_from_repo(owner,repo,num_logs=10)
    
    print()
    print(f"✅ Successfully collected {len(logs)} logs!")
    print()
    
    # Save them (use parent directory)
    output_dir = os.path.join(parent_dir, 'data', 'raw_logs', 'github_actions')
    os.makedirs(output_dir, exist_ok=True)
    output_file = os.path.join(output_dir, 'batch1.json')
    
    with open(output_file, 'w') as f:
        json.dump(logs, f, indent=2)
    
    print(f"💾 Saved to: {output_file}")
    print()
    
    # Show statistics
    from collections import Counter
    
    repos = Counter(log['repository'] for log in logs)
    workflows = Counter(log['workflow_name'] for log in logs)
    
    print("="*70)
    print("📊 Collection Statistics")
    print("="*70)
    print(f"Total logs: {len(logs)}")
    print(f"Unique repositories: {len(repos)}")
    print()
    
    print("Top 5 repositories:")
    for repo, count in repos.most_common(5):
        print(f"  • {repo}: {count} logs")
    
    print()
    print("Top 5 workflows:")
    for workflow, count in workflows.most_common(5):
        print(f"  • {workflow}: {count} logs")
    
    # Preview first log
    if logs:
        print()
        print("="*70)
        print("📋 Sample Log Preview")
        print("="*70)
        print(f"Repository: {logs[0]['repository']}")
        print(f"Workflow: {logs[0]['workflow_name']}")
        print(f"URL: {logs[0]['url']}")
        print()
        print("Log content (first 300 chars):")
        print(logs[0]['log_content'][:300])
        print("...")
    
    print()
    print("="*70)
    print("✨ Collection Complete!")
    print("="*70)
    
except Exception as e:
    print()
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()