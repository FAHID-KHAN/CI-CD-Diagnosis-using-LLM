import sys
import os
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(parent_dir, 'src'))

import json
import requests
import time

print("="*70)
print("🤖 Auto-Diagnosis of Collected Logs")
print("="*70)
print()

# Load collected logs
log_file = os.path.join(parent_dir, 'data/raw_logs/github_actions/batch1.json')
with open(log_file, 'r') as f:
    logs = json.load(f)

print(f"📂 Loaded {len(logs)} logs")
print(f"💰 Estimated cost: ${len(logs) * 0.002:.2f} - ${len(logs) * 0.005:.2f}")
print()

proceed = input("Proceed with diagnosis? (y/n): ")
if proceed.lower() != 'y':
    print("Cancelled.")
    exit()

# Check API is running
print()
print("🔍 Checking if API is running...")
try:
    response = requests.get('http://localhost:8000/health', timeout=5)
    if response.status_code == 200:
        print("✓ API is running")
    else:
        print("❌ API not responding correctly")
        exit(1)
except:
    print("❌ API is not running!")
    print()
    print("Please start the API in another terminal:")
    print("  cd ~/cicd_diagnosis_thesis")
    print("  source .venv/bin/activate")
    print("  uvicorn src.api.main:app --reload")
    exit(1)

print()
print("🔄 Starting diagnosis...")
print()

results = []
errors = []

for i, log in enumerate(logs, 1):
    print(f"[{i}/{len(logs)}] {log['repository']} - {log['workflow_name']}", end=" ")
    
    try:
        response = requests.post(
            'http://localhost:8000/diagnose',
            json={
                'log_content': log['log_content'],
                'provider': 'openai',
                'model': 'gpt-4o-mini',
                'temperature': 0.1,
                'use_filtering': True
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
            
            print(f"✓ {diagnosis['error_type']} ({diagnosis['confidence_score']:.0%})")
        else:
            print(f"✗ HTTP {response.status_code}")
            errors.append(log['log_id'])
            
    except Exception as e:
        print(f"✗ {str(e)[:50]}")
        errors.append(log['log_id'])
    
    # Rate limiting
    time.sleep(0.5)

print()
print("="*70)
print("📊 Diagnosis Complete")
print("="*70)
print(f"Success: {len(results)}/{len(logs)}")
print(f"Failed: {len(errors)}/{len(logs)}")
print()

# Save results
if results:
    output_dir = os.path.join(parent_dir, 'data/annotated_logs')
    os.makedirs(output_dir, exist_ok=True)
    output_file = os.path.join(output_dir, 'diagnosed_batch1.json')
    
    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2)
    
    print(f"💾 Results saved to: {output_file}")
    print()
    
    # Statistics
    from collections import Counter
    error_types = Counter(r['diagnosis']['error_type'] for r in results)
    avg_confidence = sum(r['diagnosis']['confidence_score'] for r in results) / len(results)
    avg_time = sum(r['diagnosis']['execution_time_ms'] for r in results) / len(results)
    
    print("📈 Statistics:")
    print(f"  Average confidence: {avg_confidence:.1%}")
    print(f"  Average time: {avg_time:.0f}ms")
    print()
    print("  Error type distribution:")
    for error_type, count in error_types.most_common():
        pct = (count / len(results)) * 100
        print(f"    • {error_type}: {count} ({pct:.1f}%)")

print()
print("="*70)
print("✨ Done!")
print("="*70)