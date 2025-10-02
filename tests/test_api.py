import pytest
from fastapi.testclient import TestClient
from src.api.main import app

client = TestClient(app)

def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"

def test_diagnose_endpoint():
    test_log = "ERROR: Module not found: 'requests'"
    
    response = client.post(
        "/diagnose",
        json={
            "log_content": test_log,
            "provider": "openai",
            "model": "gpt-4",
            "temperature": 0.1
        }
    )
    
    assert response.status_code == 200
    assert "error_type" in response.json()