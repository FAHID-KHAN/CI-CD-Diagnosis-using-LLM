import pytest
from fastapi.testclient import TestClient
from src.api.main import app

client = TestClient(app)

def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"

def test_diagnose_endpoint(monkeypatch):
    test_log = "ERROR: Module not found: 'requests'"

    async def fake_diagnose(self, *args, **kwargs):
        return {
            "error_type": "dependency_error",
            "failure_lines": [1],
            "root_cause": "The requests dependency is unavailable.",
            "suggested_fix": "Install the requests dependency.",
            "confidence_score": 0.9,
            "grounded_evidence": [],
            "reasoning": "The log explicitly reports the missing module.",
        }

    monkeypatch.setattr("src.api.main.LLMDiagnoser.diagnose", fake_diagnose)

    response = client.post(
        "/diagnose",
        json={
            "log_content": test_log,
            "provider": "openai",
            "model": "gpt-5.6-terra",
            "temperature": 0.1
        }
    )
    
    assert response.status_code == 200
    assert "error_type" in response.json()
