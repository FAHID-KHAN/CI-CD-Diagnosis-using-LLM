# CI/CD Log Diagnosis with LLMs

Automated diagnosis of CI/CD pipeline failures using Large Language Models.

Master's thesis project -- Tampere University.

## Features

- **Multi-LLM support** -- OpenAI (GPT-4o-mini), Anthropic (Claude), and local models via Ollama (Llama3, Mistral, Mixtral)
- **Smart log filtering** -- keyword-based filtering with tiktoken token counting and intelligent middle-out truncation (configurable token budget, default 12 000)
- **Grounding verification** -- hallucination detection with exact + fuzzy matching (SequenceMatcher, threshold 0.75)
- **Checkpoint/resume** -- diagnosis pipeline resumes from where it left off on interruption
- **Multi-model benchmarking** -- compare LLMs side-by-side on the same logs without the API overhead
- **RAG system** -- ChromaDB + SentenceTransformers for documentation-augmented diagnosis (experimental)

## Project Structure

```
src/                        # Core library
  api/                      # FastAPI diagnostic service
    main.py                 #   Endpoints (/diagnose, /health, etc.)
    models.py               #   Pydantic models & enums
    filtering.py            #   Log filtering + tiktoken token counting
    llm_service.py          #   LLM integration (OpenAI / Anthropic / Ollama)
    grounding.py            #   Grounding verifier (exact + fuzzy matching)
  data_collection/          # GitHub Actions log collector
  evaluation/               # Metrics & ablation framework
  rag/                      # RAG system (ChromaDB + docs)
  human_study/              # Web-based user study interface
  config.py                 # YAML config loader
  log_setup.py              # Logging setup

automated_scripts/          # CLI workflow scripts
  data_collection.py        #   Collect logs from GitHub repos
  triage.py                 #   Filter & deduplicate collected logs
  diagnose_logs.py          #   Send logs to API for diagnosis (checkpoint/resume)
  annotate.py               #   Annotate ground truth interactively
  evaluate_demo.py          #   Generate evaluation report & charts
  benchmark_models.py       #   Multi-model benchmark (direct LLM, no API)

configs/                    # YAML configuration
  api_config.yaml
  rag_config.yaml
  evaluation_config.yaml

data/                       # Collected & annotated data
  raw_logs/                 #   Raw logs from GitHub Actions
  annotated_logs/           #   Diagnosed & annotated results

tests/                      # Tests
docs/                       # Documentation
```

## Quick Start

```bash
# 1. Create virtual environment
python -m venv .venv
source .venv/bin/activate

# 2. Install
pip install -e .

# 3. Set environment variables
cp .env.template .env
# Edit .env with your OPENAI_API_KEY, GITHUB_TOKEN, etc.

# 4. Start the API
make run
# -> http://localhost:8000/docs
```

### Local Models (Ollama)

To use local LLMs instead of cloud APIs:

```bash
# Install Ollama (macOS)
brew install ollama

# Pull models
ollama pull llama3
ollama pull mistral

# Start Ollama server (runs on port 11434)
ollama serve

# Diagnose with a local model
curl -X POST http://localhost:8000/diagnose \
  -H "Content-Type: application/json" \
  -d '{"log_content": "...", "provider": "local", "model": "llama3"}'
```

## Workflow

The full pipeline runs in 8 steps:

```bash
make collect     # 1. Collect failed CI/CD logs from GitHub
make triage      # 2. Filter duplicates, cancelled runs, etc.
make run         # 3. Start the diagnostic API (separate terminal)
make diagnose    # 4. Send triaged logs to API for diagnosis
make annotate    # 5. Manually annotate ground truth
make evaluate    # 6. Generate evaluation report & charts
make benchmark   # 7. Benchmark multiple LLMs side-by-side (no API needed)
```

Or use the all-in-one bash script:

```bash
./run_workflow.sh                              # Full pipeline (steps 1-8)
./run_workflow.sh --skip-collect --from 4      # Re-diagnose existing logs
./run_workflow.sh --skip-annotate              # Non-interactive (reuse ground truth)
./run_workflow.sh --only 8                     # Just run benchmark
./run_workflow.sh --provider local --model llama3  # Use local Ollama model
```

Run `make help` to see all available commands.

## Multi-Model Benchmarking

Compare different LLMs on the same set of logs:

```bash
# Default models (gpt-4o-mini, llama3, mistral)
python automated_scripts/benchmark_models.py

# Custom model list
python automated_scripts/benchmark_models.py \
    --models openai/gpt-4o-mini local/llama3 local/mistral anthropic/claude-3-haiku-20240307

# Quick test with 10 logs
python automated_scripts/benchmark_models.py --limit 10

# With ground truth for accuracy scoring
python automated_scripts/benchmark_models.py --ground-truth data/evaluation/ground_truth.json
```

Results are saved to `results/benchmark/<timestamp>/` with per-model results, a comparison report, and a printable summary table.

## Diagnose a Single Log

```python
import requests

response = requests.post(
    "http://localhost:8000/diagnose",
    json={
        "log_content": "<paste log here>",
        "provider": "openai",           # or "anthropic", "local"
        "model": "gpt-4o-mini",         # or "llama3", "mistral", "claude-..."
        "use_filtering": True,
        "repository": "owner/repo",          # optional context
        "workflow_name": "CI Tests",          # optional context
        "ci_system": "GitHub Actions",        # optional context
    },
)
result = response.json()
print(result["error_type"], result["root_cause"], result["suggested_fix"])
```

## Docker

```bash
docker-compose up --build
```

## Authors

- Fahid Khan -- Tampere University
- Supervisors: Jussi Rasku & Md Mahade Hasan