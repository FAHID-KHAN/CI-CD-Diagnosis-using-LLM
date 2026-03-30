# llm_service.py - LLM integration for diagnosis

import asyncio
import json
import logging
import re
from typing import Any, Dict, Optional

import anthropic
import openai

from src.api.models import LLMProvider

logger = logging.getLogger(__name__)

MAX_LLM_RETRIES = 3
LLM_BACKOFF = 2.0

# ── Per-token pricing (USD) ────────────────────────────────────────────
# Source: https://openai.com/api/pricing  /  https://docs.anthropic.com/
# Update these when pricing changes.
PRICING = {
    "gpt-4o-mini":          {"input": 0.15 / 1_000_000, "output": 0.60 / 1_000_000},
    "gpt-4o":               {"input": 2.50 / 1_000_000, "output": 10.0 / 1_000_000},
    "gpt-3.5-turbo":        {"input": 0.50 / 1_000_000, "output": 1.50 / 1_000_000},
    "claude-3-haiku-20240307":  {"input": 0.25 / 1_000_000, "output": 1.25 / 1_000_000},
    "claude-3-sonnet-20240229": {"input": 3.00 / 1_000_000, "output": 15.0 / 1_000_000},
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
    "error_type": "dependency_error|test_failure|build_configuration|timeout|permission_denied|syntax_error|network_error|unknown",
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
    """Thin wrapper around OpenAI / Anthropic for CI/CD log diagnosis."""

    # Default Ollama endpoint (OpenAI-compatible)
    OLLAMA_BASE_URL = "http://localhost:11434/v1"

    def __init__(
        self,
        provider: LLMProvider,
        model: str,
        api_key: Optional[str] = None,
        max_tokens: int = 4096,
        base_url: Optional[str] = None,
    ):
        self.provider = provider
        self.model = model
        self.max_tokens = max_tokens

        # Token usage from the most recent call
        self.last_usage: Dict[str, Any] = {}

        # Build a reusable client once (instead of per-request)
        if provider == LLMProvider.OPENAI:
            self._openai = openai.AsyncOpenAI(api_key=api_key)
        elif provider == LLMProvider.ANTHROPIC:
            self._anthropic = anthropic.AsyncAnthropic(api_key=api_key)
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
        temperature: float = 0.1,
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
                    return await self._diagnose_openai(prompt, temperature)
                elif self.provider == LLMProvider.ANTHROPIC:
                    return await self._diagnose_anthropic(prompt, temperature)
                elif self.provider == LLMProvider.LOCAL:
                    return await self._diagnose_local(prompt, temperature)
                else:
                    raise ValueError(f"Unsupported LLM provider: {self.provider}")
            except (openai.RateLimitError, anthropic.RateLimitError) as exc:
                wait = LLM_BACKOFF ** attempt
                logger.warning("Rate-limited (attempt %d/%d), retrying in %.1fs: %s",
                               attempt + 1, MAX_LLM_RETRIES, wait, exc)
                await asyncio.sleep(wait)
            except (openai.APIConnectionError, anthropic.APIConnectionError) as exc:
                wait = LLM_BACKOFF ** attempt
                logger.warning("Connection error (attempt %d/%d), retrying in %.1fs: %s",
                               attempt + 1, MAX_LLM_RETRIES, wait, exc)
                await asyncio.sleep(wait)

        # Final attempt without catching
        if self.provider == LLMProvider.OPENAI:
            return await self._diagnose_openai(prompt, temperature)
        elif self.provider == LLMProvider.LOCAL:
            return await self._diagnose_local(prompt, temperature)
        return await self._diagnose_anthropic(prompt, temperature)

    # -- private ---------------------------------------------------------

    def _compute_cost(self, prompt_tokens: int, completion_tokens: int) -> float:
        """Compute estimated USD cost for the most recent call."""
        rates = PRICING.get(self.model, {})
        return (
            prompt_tokens * rates.get("input", 0)
            + completion_tokens * rates.get("output", 0)
        )

    async def _diagnose_openai(self, prompt: str, temperature: float) -> Dict[str, Any]:
        response = await self._openai.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": SYSTEM_MESSAGE},
                {"role": "user", "content": prompt},
            ],
            temperature=temperature,
            response_format={"type": "json_object"},
        )
        usage = response.usage
        pt = usage.prompt_tokens if usage else 0
        ct = usage.completion_tokens if usage else 0
        self.last_usage = {
            "prompt_tokens": pt,
            "completion_tokens": ct,
            "total_tokens": pt + ct,
            "estimated_cost_usd": self._compute_cost(pt, ct),
        }
        return json.loads(response.choices[0].message.content)

    async def _diagnose_anthropic(self, prompt: str, temperature: float) -> Dict[str, Any]:
        response = await self._anthropic.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            temperature=temperature,
            messages=[{"role": "user", "content": prompt}],
        )
        usage = response.usage
        pt = usage.input_tokens if usage else 0
        ct = usage.output_tokens if usage else 0
        self.last_usage = {
            "prompt_tokens": pt,
            "completion_tokens": ct,
            "total_tokens": pt + ct,
            "estimated_cost_usd": self._compute_cost(pt, ct),
        }
        content = response.content[0].text
        json_match = re.search(r'\{.*\}', content, re.DOTALL)
        if json_match:
            return json.loads(json_match.group())
        return json.loads(content)

    async def _diagnose_local(self, prompt: str, temperature: float) -> Dict[str, Any]:
        """Diagnose via Ollama (or any OpenAI-compatible local server).

        Most local models do not support ``response_format: json_object``,
        so we extract JSON from the raw text response instead.
        """
        response = await self._local.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": SYSTEM_MESSAGE},
                {"role": "user", "content": prompt},
            ],
            temperature=temperature,
        )
        usage = response.usage
        pt = usage.prompt_tokens if usage else 0
        ct = usage.completion_tokens if usage else 0
        self.last_usage = {
            "prompt_tokens": pt,
            "completion_tokens": ct,
            "total_tokens": pt + ct,
            "estimated_cost_usd": 0.0,  # Local models have no API cost
        }
        content = response.choices[0].message.content
        json_match = re.search(r'\{.*\}', content, re.DOTALL)
        if json_match:
            return json.loads(json_match.group())
        return json.loads(content)
