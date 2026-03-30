import sys
import os
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(parent_dir, 'src'))

import json
import requests
import time
import argparse

def parse_args():
    parser = argparse.ArgumentParser(description="Send collected logs to the diagnostic API")
    parser.add_argument("--input", default=None,
                        help="Input JSON file (default: batch1_triaged.json if exists, else batch1.json)")
    parser.add_argument("--output", default=None,
                        help="Output JSON file (default: data/annotated_logs/diagnosed_batch1.json)")
    parser.add_argument("--model", default="gpt-4o-mini", help="LLM model to use")
    parser.add_argument("--provider", default="openai", help="LLM provider (openai or anthropic)")
    parser.add_argument("--limit", type=int, default=None, help="Max number of logs to diagnose")
    parser.add_argument("--api-url", default="http://localhost:8000", help="API base URL")
    parser.add_argument("--yes", "-y", action="store_true", help="Skip confirmation prompt")
    return parser.parse_args()

args = parse_args()

print("="*70)
print("  Auto-Diagnosis of Collected Logs")
print("="*70)
print()

# Load collected logs -- prefer triaged version if it exists
if args.input:
    log_file = args.input
else:
    triaged = os.path.join(parent_dir, 'data/raw_logs/github_actions/batch1_triaged.json')
    raw = os.path.join(parent_dir, 'data/raw_logs/github_actions/batch1.json')
    if os.path.exists(triaged):
        log_file = triaged
        print(f"  Using triaged logs: {triaged}")
    else:
        log_file = raw
        print(f"  Using raw logs: {raw}")
        print("  (Run triage.py first for smarter selection)")
    print()

with open(log_file, 'r') as f:
    logs = json.load(f)

if args.limit:
    logs = logs[:args.limit]

print(f"  Loaded {len(logs)} logs")
print(f"  Model: {args.provider}/{args.model}")
print(f"  Estimated cost: ${len(logs) * 0.002:.2f} - ${len(logs) * 0.005:.2f}")
print()

if not args.yes:
    proceed = input("Proceed with diagnosis? (y/n): ")
    if proceed.lower() != 'y':
        print("Cancelled.")
        exit()

# Resolve output path early for checkpoint support
if args.output:
    output_file = args.output
else:
    output_dir = os.path.join(parent_dir, 'data/annotated_logs')
    os.makedirs(output_dir, exist_ok=True)
    output_file = os.path.join(output_dir, 'diagnosed_batch1.json')

# Load existing results for resume support
existing_results = []
already_diagnosed = set()
if os.path.exists(output_file):
    try:
        with open(output_file, 'r') as f:
            existing_results = json.load(f)
        already_diagnosed = {r['log_id'] for r in existing_results}
        if already_diagnosed:
            print(f"  Resuming: {len(already_diagnosed)} logs already diagnosed, skipping them.")
    except (json.JSONDecodeError, KeyError):
        pass

# Check API is running
print()
print("  Checking if API is running...")
try:
    response = requests.get(f'{args.api_url}/health', timeout=5)
    if response.status_code == 200:
        print("  API is running")
    else:
        print("  API not responding correctly")
        exit(1)
except:
    print("  API is not running!")
    print()
    print("  Please start the API in another terminal:")
    print("    source .venv/bin/activate")
    print("    uvicorn src.api.main:app --reload")
    exit(1)

print()
print("  Starting diagnosis...")
print()

results = list(existing_results)
errors = []

for i, log in enumerate(logs, 1):
    # Skip already-diagnosed logs (resume support)
    if log['log_id'] in already_diagnosed:
        print(f"[{i}/{len(logs)}] {log['repository']} - {log['workflow_name']}  SKIP (already diagnosed)")
        continue

    label = log.get('triage_priority', '')
    label_str = f" [{label}]" if label else ""
    print(f"[{i}/{len(logs)}] {log['repository']} - {log['workflow_name']}{label_str}", end=" ")
    
    try:
        response = requests.post(
            f'{args.api_url}/diagnose',
            json={
                'log_content': log['log_content'],
                'provider': args.provider,
                'model': args.model,
                'temperature': 0.1,
                'use_filtering': True,
                'repository': log.get('repository', ''),
                'workflow_name': log.get('workflow_name', ''),
                'ci_system': 'GitHub Actions',
                'run_url': log.get('url', ''),
            },
            timeout=60
        )
        
        if response.status_code == 200:
            diagnosis = response.json()
            
            results.append({
                'log_id': log['log_id'],
                'repository': log['repository'],
                'workflow': log['workflow_name'],
                'url': log['url'],
                'diagnosis': diagnosis
            })
            
            print(f"  OK  {diagnosis['error_type']} ({diagnosis['confidence_score']:.0%})")

            # Checkpoint: save after each successful diagnosis
            with open(output_file, 'w') as f:
                json.dump(results, f, indent=2)
        else:
            print(f"  FAIL  HTTP {response.status_code}")
            errors.append(log['log_id'])
            
    except Exception as e:
        print(f"  FAIL  {str(e)[:50]}")
        errors.append(log['log_id'])
    
    # Rate limiting
    time.sleep(0.5)

print()
print("="*70)
print("  Diagnosis Complete")
print("="*70)
print(f"  Success: {len(results)}/{len(logs)}")
print(f"  Failed : {len(errors)}/{len(logs)}")
print(f"  Skipped: {len(already_diagnosed)}/{len(logs)} (already diagnosed)")
print()

# Final save (also covers the case where all were resumed)
if results:
    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2)
    
    print(f"  Results saved to: {output_file}")
    print()
    
    # Statistics
    from collections import Counter
    error_types = Counter(r['diagnosis']['error_type'] for r in results)
    avg_confidence = sum(r['diagnosis']['confidence_score'] for r in results) / len(results)
    avg_time = sum(r['diagnosis']['execution_time_ms'] for r in results) / len(results)
    
    print("  Statistics:")
    print(f"    Average confidence: {avg_confidence:.1%}")
    print(f"    Average time: {avg_time:.0f}ms")
    print()
    print("    Error type distribution:")
    for error_type, count in error_types.most_common():
        pct = (count / len(results)) * 100
        print(f"      {error_type}: {count} ({pct:.1f}%)")

print()
print("="*70)
print("  Next step: python automated_scripts/annotate.py")
print("="*70)