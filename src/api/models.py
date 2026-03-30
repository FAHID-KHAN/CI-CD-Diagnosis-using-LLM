# models.py - Pydantic models and enums for the diagnostic API

from pydantic import BaseModel, Field
from typing import List
from enum import Enum


class ErrorType(str, Enum):
    DEPENDENCY = "dependency_error"
    TEST_FAILURE = "test_failure"
    BUILD_CONFIG = "build_configuration"
    TIMEOUT = "timeout"
    PERMISSION = "permission_denied"
    SYNTAX = "syntax_error"
    NETWORK = "network_error"
    UNKNOWN = "unknown"


class LLMProvider(str, Enum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    LOCAL = "local"


class DiagnosisRequest(BaseModel):
    log_content: str = Field(..., description="Raw CI/CD log content")
    provider: LLMProvider = Field(default=LLMProvider.OPENAI)
    model: str = Field(default="gpt-4o-mini")
    temperature: float = Field(default=0.1, ge=0, le=2)
    use_filtering: bool = Field(default=True)
    max_context_lines: int = Field(default=500)
    # Optional metadata for context-enriched prompts
    repository: str = Field(default="", description="Repository name (e.g. pytorch/pytorch)")
    workflow_name: str = Field(default="", description="CI workflow name")
    ci_system: str = Field(default="GitHub Actions", description="CI/CD platform")
    run_url: str = Field(default="", description="URL to the failed run")


class LogLine(BaseModel):
    line_number: int
    content: str
    is_error: bool = False


class DiagnosisResult(BaseModel):
    log_id: str
    error_type: ErrorType
    failure_lines: List[int]
    root_cause: str
    suggested_fix: str
    confidence_score: float = Field(ge=0, le=1)
    grounded_evidence: List[LogLine]
    reasoning: str
    execution_time_ms: float
    model_used: str
    hallucination_detected: bool = False
