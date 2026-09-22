# llm_service.py - LLM integration for diagnosis

import asyncio
import json
import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import openai

from src.api.models import LLMDiagnosis, LLMProvider

logger = logging.getLogger(__name__)

MAX_LLM_RETRIES = 3
LLM_BACKOFF = 2.0

# ── Per-token pricing (USD) ────────────────────────────────────────────
# Prices are recorded for reproducibility and should be frozen for a thesis run.
# GPT-5.6 Terra source (verified 2026-09-21):
# https://developers.openai.com/api/docs/models/gpt-5.6-terra
PRICING = {
    "gpt-5.6-terra": {"input": 2.00 / 1_000_000, "output": 12.00 / 1_000_000},
}

PRICING_AS_OF = "2026-09-21"


DIAGNOSIS_RESPONSE_FORMAT = {
    "type": "json_schema",
    "json_schema": {
        "name": "cicd_failure_diagnosis",
        "strict": True,
        "schema": LLMDiagnosis.model_json_schema(),
    },
}

SYSTEM_MESSAGE = "You are an expert DevOps engineer."

DIAGNOSIS_PROMPT = """You are an expert DevOps engineer analyzing CI/CD pipeline failures.

Analyze the following build log and provide a detailed diagnosis.
{context_block}
CRITICAL REQUIREMENTS:
1. You MUST cite exact log lines (with line numbers) as evidence
2. Every claim must reference specific lines from the log
3. Identify the root cause, not just symptoms
4. Provide actionable fix suggestions
5. Use the context information (repository, workflow, CI system) to inform your analysis

LOG CONTENT:
{log_content}

Respond in JSON format:
{{
    "error_type": "one category permitted by the response schema",
    "failure_lines": [line numbers where errors occur],
    "root_cause": "Clear explanation of the underlying issue",
    "suggested_fix": "Specific, actionable steps to resolve the issue",
    "confidence_score": 0.0-1.0,
    "grounded_evidence": [
        {{"line_number": X, "content": "exact line content", "is_error": true}}
    ],
    "reasoning": "Step-by-step analysis leading to this diagnosis"
}}"""


class LLMDiagnoser:
    """Run either of the two fixed thesis model conditions."""

    # Default Ollama endpoint (OpenAI-compatible). The local thesis model is
    # created from qwen3.5:9b with a fixed 24K context; see the tracked
    # Modelfile in configs/.
    OLLAMA_BASE_URL = "http://localhost:11434/v1"

    def __init__(
        self,
        provider: LLMProvider,
        model: str,
        api_key: Optional[str] = None,
        max_tokens: int = 4096,
        base_url: Optional[str] = None,
        reasoning_effort: str = "medium",
    ):
        self.provider = provider
        self.model = model
        self.max_tokens = max_tokens
        if reasoning_effort not in {"low", "medium", "high"}:
            raise ValueError("reasoning_effort must be one of: low, medium, high")
        self.reasoning_effort = reasoning_effort

        expected_models = {
            LLMProvider.OPENAI: "gpt-5.6-terra",
            LLMProvider.LOCAL: "thesis-qwen3.5:9b-24k",
        }
        if expected_models.get(provider) != model:
            raise ValueError(
                f"Unsupported thesis condition: {provider.value}/{model}. "
                "Use openai/gpt-5.6-terra or local/thesis-qwen3.5:9b-24k."
            )

        # Token usage from the most recent call
        self.last_usage: Dict[str, Any] = {}
        self.last_raw_response = ""

        # Build a reusable client once (instead of per-request)
        if provider == LLMProvider.OPENAI:
            self._openai = openai.AsyncOpenAI(api_key=api_key)
        elif provider == LLMProvider.LOCAL:
            # Ollama exposes an OpenAI-compatible API at /v1
            self._local = openai.AsyncOpenAI(
                api_key="ollama",  # Ollama ignores this but the client requires it
                base_url=base_url or self.OLLAMA_BASE_URL,
            )

    # -- public ----------------------------------------------------------

    def create_prompt(
        self,
        log_content: str,
        repository: str = "",
        workflow_name: str = "",
        ci_system: str = "",
        run_url: str = "",
    ) -> str:
        # Build a context block from available metadata
        context_lines = []
        if repository:
            context_lines.append(f"- Repository: {repository}")
        if workflow_name:
            context_lines.append(f"- Workflow: {workflow_name}")
        if ci_system:
            context_lines.append(f"- CI System: {ci_system}")
        if run_url:
            context_lines.append(f"- Run URL: {run_url}")

        if context_lines:
            context_block = "\nCONTEXT:\n" + "\n".join(context_lines) + "\n"
        else:
            context_block = ""

        return DIAGNOSIS_PROMPT.format(
            log_content=log_content,
            context_block=context_block,
        )

    async def diagnose(
        self,
        log_content: str,
        repository: str = "",
        workflow_name: str = "",
        ci_system: str = "",
        run_url: str = "",
    ) -> Dict[str, Any]:
        prompt = self.create_prompt(
            log_content,
            repository=repository,
            workflow_name=workflow_name,
            ci_system=ci_system,
            run_url=run_url,
        )

        for attempt in range(MAX_LLM_RETRIES):
            try:
                if self.provider == LLMProvider.OPENAI:
                    return await self._diagnose_openai(prompt)
                if self.provider == LLMProvider.LOCAL:
                    return await self._diagnose_local(prompt)
                raise ValueError(f"Unsupported LLM provider: {self.provider}")
            except openai.RateLimitError as exc:
                wait = LLM_BACKOFF**attempt
                logger.warning(
                    "Rate-limited (attempt %d/%d), retrying in %.1fs: %s", attempt + 1, MAX_LLM_RETRIES, wait, exc
                )
                await asyncio.sleep(wait)
            except openai.APIConnectionError as exc:
                wait = LLM_BACKOFF**attempt
                logger.warning(
                    "Connection error (attempt %d/%d), retrying in %.1fs: %s", attempt + 1, MAX_LLM_RETRIES, wait, exc
                )
                await asyncio.sleep(wait)

        # Final attempt without catching
        if self.provider == LLMProvider.OPENAI:
            return await self._diagnose_openai(prompt)
        elif self.provider == LLMProvider.LOCAL:
            return await self._diagnose_local(prompt)
        raise ValueError(f"Unsupported LLM provider: {self.provider}")

    # -- private ---------------------------------------------------------

    def _compute_cost(self, prompt_tokens: int, completion_tokens: int) -> float:
        """Compute estimated USD cost for the most recent call."""
        rates = PRICING.get(self.model, {})
        return prompt_tokens * rates.get("input", 0) + completion_tokens * rates.get("output", 0)

    @staticmethod
    def _parse_diagnosis(content: str) -> Dict[str, Any]:
        """Parse and validate the common structured diagnosis contract."""
        try:
            payload = json.loads(content)
        except json.JSONDecodeError:
            json_match = re.search(r"\{.*\}", content, re.DOTALL)
            if not json_match:
                raise
            payload = json.loads(json_match.group())
        return LLMDiagnosis.model_validate(payload).model_dump(mode="json")

    def _set_usage(self, response: Any, prompt_tokens: int, completion_tokens: int, *, local: bool) -> None:
        """Store reproducibility and cost metadata for the most recent request."""
        self.last_usage = {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
            "estimated_cost_usd": 0.0 if local else self._compute_cost(prompt_tokens, completion_tokens),
            "pricing_as_of": PRICING_AS_OF if self.model == "gpt-5.6-terra" else None,
            "cost_basis": "zero_marginal_api_cost" if local else "published_token_pricing",
            "requested_model": self.model,
            "resolved_model": getattr(response, "model", None) or self.model,
            "provider": self.provider.value,
            "reasoning_effort": self.reasoning_effort,
            "temperature_applied": None,
            "requested_at_utc": datetime.now(timezone.utc).isoformat(),
        }

    async def _diagnose_openai(self, prompt: str) -> Dict[str, Any]:
        request: Dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": SYSTEM_MESSAGE},
                {"role": "user", "content": prompt},
            ],
            "max_completion_tokens": self.max_tokens,
            "response_format": DIAGNOSIS_RESPONSE_FORMAT,
            "reasoning_effort": self.reasoning_effort,
        }

        response = await self._openai.chat.completions.create(**request)
        usage = response.usage
        pt = usage.prompt_tokens if usage else 0
        ct = usage.completion_tokens if usage else 0
        self._set_usage(response, pt, ct, local=False)
        self.last_raw_response = response.choices[0].message.content
        return self._parse_diagnosis(self.last_raw_response)

    async def _diagnose_local(self, prompt: str) -> Dict[str, Any]:
        """Diagnose via Ollama (or any OpenAI-compatible local server).

        The thesis open-weight condition uses the same strict JSON schema and
        reasoning level as the proprietary condition.
        """
        request: Dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": SYSTEM_MESSAGE},
                {"role": "user", "content": prompt},
            ],
            "max_tokens": self.max_tokens,
            "response_format": DIAGNOSIS_RESPONSE_FORMAT,
            "reasoning_effort": self.reasoning_effort,
        }

        response = await self._local.chat.completions.create(**request)
        usage = response.usage
        pt = usage.prompt_tokens if usage else 0
        ct = usage.completion_tokens if usage else 0
        self._set_usage(response, pt, ct, local=True)
        content = response.choices[0].message.content
        self.last_raw_response = content
        return self._parse_diagnosis(content)
