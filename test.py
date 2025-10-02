# test.py
import requests
import json

def test_diagnosis():
    """Test the CI/CD diagnostic API with OpenAI"""
    
    # Sample CI/CD failure log
    log_content = """[2024-10-01 10:23:45] Starting build...
[2024-10-01 10:23:46] Running npm install...
[2024-10-01 10:23:50] npm ERR! code ERESOLVE
[2024-10-01 10:23:50] npm ERR! ERESOLVE unable to resolve dependency tree
[2024-10-01 10:23:50] npm ERR! 
[2024-10-01 10:23:50] npm ERR! While resolving: my-app@1.0.0
[2024-10-01 10:23:50] npm ERR! Found: react@17.0.2
[2024-10-01 10:23:50] npm ERR! node_modules/react
[2024-10-01 10:23:50] npm ERR!   react@"^17.0.2" from the root project
[2024-10-01 10:23:50] npm ERR! 
[2024-10-01 10:23:50] npm ERR! Could not resolve dependency:
[2024-10-01 10:23:50] npm ERR! peer react@"^18.0.0" from react-router-dom@6.4.0
[2024-10-01 10:23:50] npm ERR! node_modules/react-router-dom
[2024-10-01 10:23:50] npm ERR!   react-router-dom@"^6.4.0" from the root project
[2024-10-01 10:23:51] npm ERR! 
[2024-10-01 10:23:51] npm ERR! Fix the upstream dependency conflict, or retry
[2024-10-01 10:23:51] npm ERR! this command with --force, or --legacy-peer-deps
[2024-10-01 10:23:51] Build failed with exit code 1"""

    print("=" * 70)
    print("🔍 Testing CI/CD Log Diagnosis with OpenAI")
    print("=" * 70)
    print()
    
    # API request
    print("📤 Sending request to API...")
    try:
        response = requests.post(
            'http://localhost:8000/diagnose',
            json={
                'log_content': log_content,
                'provider': 'openai',
                'model': 'gpt-4o-mini',
                'temperature': 0.1,
                'use_filtering': True,
                'max_context_lines': 500
            },
            timeout=30
        )
        
        print(f"📥 Response Status: {response.status_code}")
        print()
        
        if response.status_code == 200:
            result = response.json()
            
            print("✅ SUCCESS! Diagnosis completed.\n")
            print("=" * 70)
            print("📋 DIAGNOSIS RESULTS")
            print("=" * 70)
            print()
            
            print(f"🆔 Log ID: {result['log_id']}")
            print(f"🔴 Error Type: {result['error_type']}")
            print()
            
            print("💡 Root Cause:")
            print(f"   {result['root_cause']}")
            print()
            
            print("🔧 Suggested Fix:")
            print(f"   {result['suggested_fix']}")
            print()
            
            print(f"📊 Confidence Score: {result['confidence_score']:.2%}")
            print(f"⚡ Execution Time: {result['execution_time_ms']:.2f}ms")
            print(f"🤖 Model Used: {result['model_used']}")
            print(f"⚠️  Hallucination Detected: {'Yes' if result['hallucination_detected'] else 'No'}")
            print()
            
            print(f"🔍 Failure Lines Identified: {result['failure_lines']}")
            print()
            
            if result['grounded_evidence']:
                print("📝 Grounded Evidence:")
                for i, evidence in enumerate(result['grounded_evidence'][:3], 1):
                    print(f"   {i}. Line {evidence['line_number']}: {evidence['content'][:80]}...")
                print()
            
            print("🧠 Reasoning:")
            print(f"   {result['reasoning'][:200]}...")
            print()
            
            print("=" * 70)
            print("✅ Test completed successfully!")
            print("=" * 70)
            
            return True
            
        else:
            print(f"❌ ERROR: {response.status_code}")
            print()
            print("Response:")
            print(response.text)
            return False
            
    except requests.exceptions.ConnectionError:
        print("❌ ERROR: Cannot connect to API")
        print()
        print("Make sure the API is running:")
        print("   uvicorn src.api.main:app --reload --host 0.0.0.0 --port 8000")
        return False
        
    except requests.exceptions.Timeout:
        print("❌ ERROR: Request timed out")
        print()
        print("The API is taking too long to respond. This might be normal for first request.")
        print("Try running the test again.")
        return False
        
    except Exception as e:
        print(f"❌ ERROR: {type(e).__name__}")
        print(f"   {str(e)}")
        return False

def test_multiple_scenarios():
    """Test different types of CI/CD failures"""
    
    test_cases = [
        {
            "name": "NPM Dependency Error",
            "log": "npm ERR! code ERESOLVE\nnpm ERR! ERESOLVE unable to resolve dependency tree\nnpm ERR! Found: react@17.0.2\nnpm ERR! peer react@\"^18.0.0\" from react-router-dom@6.4.0"
        },
        {
            "name": "Test Failure",
            "log": "FAILED tests/test_user.py::test_login\nAssertionError: assert 200 == 404\nExpected status code 200 but got 404\nTest run failed"
        },
        {
            "name": "Build Configuration",
            "log": "ERROR: Could not find build.gradle in project root\nBuild configuration missing\nBuild failed with exit code 1"
        }
    ]
    
    print("\n")
    print("=" * 70)
    print("🧪 Testing Multiple Scenarios")
    print("=" * 70)
    print()
    
    results = []
    for i, test_case in enumerate(test_cases, 1):
        print(f"Test {i}/{len(test_cases)}: {test_case['name']}")
        
        try:
            response = requests.post(
                'http://localhost:8000/diagnose',
                json={
                    'log_content': test_case['log'],
                    'provider': 'openai',
                    'model': 'gpt-4o-mini',
                    'temperature': 0.1
                },
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                print(f"   ✓ Error Type: {result['error_type']}")
                print(f"   ✓ Confidence: {result['confidence_score']:.2%}")
                results.append(True)
            else:
                print(f"   ✗ Failed: {response.status_code}")
                results.append(False)
                
        except Exception as e:
            print(f"   ✗ Error: {str(e)}")
            results.append(False)
        
        print()
    
    print("=" * 70)
    print(f"Results: {sum(results)}/{len(results)} tests passed")
    print("=" * 70)

if __name__ == "__main__":
    # Run main test
    success = test_diagnosis()
    
    # If successful, run additional tests
    if success:
        user_input = input("\n🎯 Run additional test scenarios? (y/n): ")
        if user_input.lower() == 'y':
            test_multiple_scenarios()
    
    print("\n✨ Testing complete!")