# Structured diagnosis models shared by both thesis conditions.

from pydantic import BaseModel, ConfigDict, Field
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
    LOCAL = "local"


class LogLine(BaseModel):
    model_config = ConfigDict(extra="forbid")

    line_number: int
    content: str
    is_error: bool


class LLMDiagnosis(BaseModel):
    """Strict structured output requested from every diagnosis model."""

    model_config = ConfigDict(extra="forbid")

    error_type: ErrorType
    failure_lines: List[int]
    root_cause: str
    suggested_fix: str
    confidence_score: float = Field(ge=0, le=1)
    grounded_evidence: List[LogLine]
    reasoning: str
