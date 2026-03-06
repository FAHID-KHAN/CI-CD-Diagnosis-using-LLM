# src/config.py - Central configuration loaded from YAML files
#
# Usage:
#   from src.config import settings
#   settings.api.port          # 8000
#   settings.rag.vector_db_path  # "chroma_db"

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

import yaml

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_CONFIGS_DIR = _PROJECT_ROOT / "configs"


# ---------------------------------------------------------------------------
# Typed dataclasses (one per config file)
# ---------------------------------------------------------------------------

@dataclass
class APISettings:
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False
    default_provider: str = "openai"
    default_model: str = "gpt-4"
    temperature: float = 0.1
    max_tokens: int = 4096
    filtering_enabled: bool = True
    filtering_max_context_lines: int = 500
    filtering_window_size: int = 10
    grounding_enabled: bool = True
    grounding_threshold: float = 0.8


@dataclass
class RAGSettings:
    vector_db_path: str = "chroma_db"
    embedding_model: str = "all-MiniLM-L6-v2"
    documentation_sources: List[str] = field(
        default_factory=lambda: ["npm", "maven", "pip", "docker", "github_actions", "gradle", "pytest", "jest"]
    )
    max_pages_per_source: int = 50
    chunk_size: int = 500
    n_results: int = 5
    score_threshold: float = 0.7


@dataclass
class EvaluationSettings:
    test_data_path: str = "data/benchmark/annotated_test_set.json"
    output_dir: str = "results/evaluation"
    baseline_methods: List[str] = field(default_factory=lambda: ["regex", "heuristic"])
    ablation_filtering_strategies: List[object] = field(default_factory=lambda: [False, 500, 1000, 2000])
    ablation_temperature_values: List[float] = field(default_factory=lambda: [0.0, 0.1, 0.3, 0.5, 0.7, 1.0])
    metrics: List[str] = field(
        default_factory=lambda: ["precision", "recall", "f1_score", "accuracy", "hallucination_rate"]
    )


@dataclass
class Settings:
    api: APISettings = field(default_factory=APISettings)
    rag: RAGSettings = field(default_factory=RAGSettings)
    evaluation: EvaluationSettings = field(default_factory=EvaluationSettings)


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------

def _load_yaml(path: Path) -> dict:
    if path.exists():
        with open(path, "r") as f:
            return yaml.safe_load(f) or {}
    return {}


def load_settings() -> Settings:
    """Build a Settings object by merging YAML configs with defaults."""
    s = Settings()

    # --- api_config.yaml ---
    api_raw = _load_yaml(_CONFIGS_DIR / "api_config.yaml")
    api_section = api_raw.get("api", {})
    llm_section = api_raw.get("llm", {})
    filt_section = api_raw.get("filtering", {})
    gnd_section = api_raw.get("grounding", {})

    s.api.host = api_section.get("host", s.api.host)
    s.api.port = api_section.get("port", s.api.port)
    s.api.debug = api_section.get("debug", s.api.debug)
    s.api.default_provider = llm_section.get("default_provider", s.api.default_provider)
    s.api.default_model = llm_section.get("default_model", s.api.default_model)
    s.api.temperature = llm_section.get("temperature", s.api.temperature)
    s.api.max_tokens = llm_section.get("max_tokens", s.api.max_tokens)
    s.api.filtering_enabled = filt_section.get("enabled", s.api.filtering_enabled)
    s.api.filtering_max_context_lines = filt_section.get("max_context_lines", s.api.filtering_max_context_lines)
    s.api.filtering_window_size = filt_section.get("window_size", s.api.filtering_window_size)
    s.api.grounding_enabled = gnd_section.get("enabled", s.api.grounding_enabled)
    s.api.grounding_threshold = gnd_section.get("threshold", s.api.grounding_threshold)

    # --- rag_config.yaml ---
    rag_raw = _load_yaml(_CONFIGS_DIR / "rag_config.yaml")
    rag_section = rag_raw.get("rag", {})
    scraping = rag_raw.get("scraping", {})
    retrieval = rag_raw.get("retrieval", {})

    s.rag.vector_db_path = rag_section.get("vector_db_path", s.rag.vector_db_path)
    s.rag.embedding_model = rag_section.get("embedding_model", s.rag.embedding_model)
    s.rag.documentation_sources = rag_raw.get("documentation_sources", s.rag.documentation_sources)
    s.rag.max_pages_per_source = scraping.get("max_pages_per_source", s.rag.max_pages_per_source)
    s.rag.chunk_size = scraping.get("chunk_size", s.rag.chunk_size)
    s.rag.n_results = retrieval.get("n_results", s.rag.n_results)
    s.rag.score_threshold = retrieval.get("score_threshold", s.rag.score_threshold)

    # --- evaluation_config.yaml ---
    eval_raw = _load_yaml(_CONFIGS_DIR / "evaluation_config.yaml")
    eval_section = eval_raw.get("evaluation", {})
    baseline = eval_raw.get("baseline", {})
    ablation = eval_raw.get("ablation", {})
    metrics = eval_raw.get("metrics", None)

    s.evaluation.test_data_path = eval_section.get("test_data_path", s.evaluation.test_data_path)
    s.evaluation.output_dir = eval_section.get("output_dir", s.evaluation.output_dir)
    s.evaluation.baseline_methods = baseline.get("methods", s.evaluation.baseline_methods)
    if ablation:
        s.evaluation.ablation_filtering_strategies = ablation.get("filtering", {}).get(
            "strategies", s.evaluation.ablation_filtering_strategies
        )
        s.evaluation.ablation_temperature_values = ablation.get("temperature", {}).get(
            "values", s.evaluation.ablation_temperature_values
        )
    if metrics:
        s.evaluation.metrics = metrics

    return s


# Module-level singleton
settings = load_settings()
