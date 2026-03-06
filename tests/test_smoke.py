# test_smoke.py - Smoke test for the diagnostic API
# Requires the API to be running: uvicorn src.api.main:app --reload
import requests
import json


def test_diagnosis():
    """Test the CI/CD diagnostic API with a sample log."""

    log_content = """[2024-10-01 10:23:45] Starting build...
[2024-10-01 10:23:46] Running npm install...
[2024-10-01 10:23:50] npm ERR! code ERESOLVE
[2024-10-01 10:23:50] npm ERR! ERESOLVE unable to resolve dependency tree
[2024-10-01 10:23:50] npm ERR! While resolving: my-app@1.0.0
[2024-10-01 10:23:50] npm ERR! Found: react@17.0.2
[2024-10-01 10:23:50] npm ERR! Could not resolve dependency:
[2024-10-01 10:23:50] npm ERR! peer react@"^18.0.0" from react-router-dom@6.4.0
[2024-10-01 10:23:51] npm ERR! Fix the upstream dependency conflict, or retry
[2024-10-01 10:23:51] npm ERR! this command with --force, or --legacy-peer-deps
[2024-10-01 10:23:51] Build failed with exit code 1"""

    print("=" * 70)
    print("Testing CI/CD Log Diagnosis")
    print("=" * 70)

    try:
        response = requests.post(
            "http://localhost:8000/diagnose",
            json={
                "log_content": log_content,
                "provider": "openai",
                "model": "gpt-4o-mini",
                "temperature": 0.1,
                "use_filtering": True,
                "max_context_lines": 500,
            },
            timeout=30,
        )

        print(f"Response Status: {response.status_code}")

        if response.status_code == 200:
            result = response.json()
            print(f"  Error Type:    {result['error_type']}")
            print(f"  Root Cause:    {result['root_cause']}")
            print(f"  Suggested Fix: {result['suggested_fix']}")
            print(f"  Confidence:    {result['confidence_score']:.2%}")
            print(f"  Exec Time:     {result['execution_time_ms']:.0f}ms")
            print(f"  Model:         {result['model_used']}")
            print(f"  Hallucination: {'Yes' if result['hallucination_detected'] else 'No'}")
            return True
        else:
            print(f"ERROR: {response.status_code}\n{response.text}")
            return False

    except requests.exceptions.ConnectionError:
        print("ERROR: Cannot connect to API. Start it with:")
        print("  uvicorn src.api.main:app --reload --host 0.0.0.0 --port 8000")
        return False
    except Exception as e:
        print(f"ERROR: {type(e).__name__}: {e}")
        return False


def test_multiple_scenarios():
    """Test different types of CI/CD failures."""

    test_cases = [
        {
            "name": "NPM Dependency Error",
            "log": 'npm ERR! code ERESOLVE\nnpm ERR! ERESOLVE unable to resolve dependency tree\nnpm ERR! Found: react@17.0.2\nnpm ERR! peer react@"^18.0.0" from react-router-dom@6.4.0',
        },
        {
            "name": "Test Failure",
            "log": "FAILED tests/test_user.py::test_login\nAssertionError: assert 200 == 404\nExpected status code 200 but got 404\nTest run failed",
        },
        {
            "name": "Build Configuration",
            "log": "ERROR: Could not find build.gradle in project root\nBuild configuration missing\nBuild failed with exit code 1",
        },
    ]

    print("\n" + "=" * 70)
    print("Testing Multiple Scenarios")
    print("=" * 70)

    results = []
    for i, tc in enumerate(test_cases, 1):
        print(f"\nTest {i}/{len(test_cases)}: {tc['name']}")
        try:
            resp = requests.post(
                "http://localhost:8000/diagnose",
                json={"log_content": tc["log"], "provider": "openai", "model": "gpt-4o-mini", "temperature": 0.1},
                timeout=30,
            )
            if resp.status_code == 200:
                r = resp.json()
                print(f"  -> {r['error_type']} (confidence: {r['confidence_score']:.2%})")
                results.append(True)
            else:
                print(f"  -> FAILED: {resp.status_code}")
                results.append(False)
        except Exception as e:
            print(f"  -> ERROR: {e}")
            results.append(False)

    print(f"\nResults: {sum(results)}/{len(results)} passed")


if __name__ == "__main__":
    success = test_diagnosis()
    if success:
        ans = input("\nRun additional test scenarios? (y/n): ")
        if ans.lower() == "y":
            test_multiple_scenarios()
    print("\nDone.")