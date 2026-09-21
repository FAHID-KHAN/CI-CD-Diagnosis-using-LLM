"""Offline tests for the controlled thesis model configuration."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.api.llm_service import DIAGNOSIS_RESPONSE_FORMAT, LLMDiagnoser
from src.api.models import LLMProvider

VALID_DIAGNOSIS = """{
  "error_type": "dependency_error",
  "failure_lines": [12],
  "root_cause": "A required package is missing.",
  "suggested_fix": "Install the required package.",
  "confidence_score": 0.9,
  "grounded_evidence": [
    {"line_number": 12, "content": "ModuleNotFoundError: requests", "is_error": true}
  ],
  "reasoning": "The cited line reports the missing module."
}"""


def _response(model: str):
    return SimpleNamespace(
        model=model,
        usage=SimpleNamespace(prompt_tokens=1000, completion_tokens=100),
        choices=[SimpleNamespace(message=SimpleNamespace(content=VALID_DIAGNOSIS))],
    )


def test_terra_uses_reasoning_and_strict_schema_without_temperature():
    diagnoser = LLMDiagnoser(
        LLMProvider.OPENAI,
        "gpt-5.6-terra",
        api_key="test-key",
        reasoning_effort="medium",
    )
    create = AsyncMock(return_value=_response("gpt-5.6-terra"))
    diagnoser._openai = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))

    result = asyncio.run(diagnoser.diagnose("[Line 12] ModuleNotFoundError: requests"))

    request = create.await_args.kwargs
    assert request["reasoning_effort"] == "medium"
    assert "temperature" not in request
    assert request["response_format"]["type"] == "json_schema"
    assert result["error_type"] == "dependency_error"
    assert diagnoser.last_usage["estimated_cost_usd"] == pytest.approx(0.0032)
    assert diagnoser.last_usage["resolved_model"] == "gpt-5.6-terra"


def test_gpt_oss_uses_same_reasoning_and_schema_without_temperature():
    diagnoser = LLMDiagnoser(
        LLMProvider.LOCAL,
        "gpt-oss:20b",
        reasoning_effort="medium",
    )
    create = AsyncMock(return_value=_response("gpt-oss:20b"))
    diagnoser._local = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))

    asyncio.run(diagnoser.diagnose("[Line 12] ModuleNotFoundError: requests"))

    request = create.await_args.kwargs
    assert request["reasoning_effort"] == "medium"
    assert "temperature" not in request
    assert request["response_format"] == DIAGNOSIS_RESPONSE_FORMAT
    assert diagnoser.last_usage["estimated_cost_usd"] == 0.0


def test_strict_schema_requires_all_evidence_fields():
    schema = DIAGNOSIS_RESPONSE_FORMAT["json_schema"]["schema"]
    assert schema["additionalProperties"] is False
    evidence_schema = schema["$defs"]["LogLine"]
    assert evidence_schema["additionalProperties"] is False
    assert set(evidence_schema["required"]) == {"line_number", "content", "is_error"}
