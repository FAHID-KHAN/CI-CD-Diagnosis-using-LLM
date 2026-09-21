# CI/CD Log Diagnosis with LLMs

Automated diagnosis of CI/CD pipeline failures using Large Language Models.

Master's thesis project -- Tampere University.

## Features

- **Controlled thesis comparison** -- OpenAI GPT-5.6 Terra (proprietary) versus gpt-oss-20b (open-weights, local via Ollama)
- **Additional provider support** -- Anthropic and other OpenAI-compatible local models remain available outside the main experiment
- **Smart log filtering** -- keyword-based filtering with tiktoken token counting and intelligent middle-out truncation (configurable token budget, default 12 000)
- **Grounding verification** -- hallucination detection with exact + fuzzy matching (SequenceMatcher, threshold 0.75)
- **Checkpoint/resume** -- diagnosis pipeline resumes from where it left off on interruption
- **Cost tracking** -- per-request token usage and estimated USD cost from API response metadata (OpenAI, Anthropic, Ollama)
- **Multi-model benchmarking** -- compare LLMs side-by-side on the same logs with cost, accuracy, and latency comparison
- **Statistical significance tests** -- McNemar's test, bootstrap confidence intervals, paired permutation test for rigorous model comparison
- **Cost-accuracy trade-off chart** -- auto-generated scatter plot showing each model's accuracy vs cost per diagnosis
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
ollama pull gpt-oss:20b

# Start Ollama server (runs on port 11434)
ollama serve

# Diagnose with a local model
curl -X POST http://localhost:8000/diagnose \
  -H "Content-Type: application/json" \
  -d '{"log_content": "...", "provider": "local", "model": "gpt-oss:20b", "reasoning_effort": "medium"}'
```

## Workflow

The maintained system and thesis dataflow diagrams are in
[docs/architecture.md](docs/architecture.md).

The full pipeline runs in 8 steps:

```bash
make collect     # 1. Collect failed CI/CD logs from GitHub
make triage      # 2. Filter duplicates, cancelled runs, etc.
make run         # 3. Start the diagnostic API (separate terminal)
make diagnose    # 4. Send triaged logs to API for diagnosis
make annotate    # 5. Manually annotate ground truth
make evaluate    # 6. Generate evaluation report & charts
make benchmark   # 7. Benchmark multiple LLMs side-by-side (cost + accuracy + stats)
```

Or use the all-in-one bash script:

```bash
./run_workflow.sh                              # Full pipeline (steps 1-8)
./run_workflow.sh --skip-collect --from 4      # Re-diagnose existing logs
./run_workflow.sh --skip-annotate              # Non-interactive (reuse ground truth)
./run_workflow.sh --only 8                     # Just run benchmark
./run_workflow.sh --provider local --model gpt-oss:20b  # Use the thesis open-weight model
./run_workflow.sh --study                     # Fresh thesis preflight + collection + triage
```

Run `make help` to see all available commands.

### Fresh thesis dataset

The final thesis cohort uses the frozen protocol in
`configs/thesis_fresh_2026.yaml`. It is intentionally separate from the
legacy `batch1.json` workflow.

```bash
# Validate configuration, environment, token presence, output path and storage
make study-preflight

# Download one isolated smoke-test log (never included in the final cohort)
python automated_scripts/preflight_study.py \
  --study-config configs/thesis_fresh_2026.yaml --live

# Run the fixed six-repository collection once
make study-collect

# Produce eligible logs, exclusion records and a checksummed triage manifest
make study-triage
```

Study mode refuses to overwrite completed raw data. Use `--resume` only when a
collection was genuinely interrupted. Generated study data lives under
`data/studies/` and is excluded from Git; back it up separately after collection.

## Multi-Model Benchmarking

Compare different LLMs on the same set of logs:

```bash
# Default thesis models (proprietary versus open-weights)
python automated_scripts/benchmark_models.py

# Custom model list
python automated_scripts/benchmark_models.py \
    --models openai/gpt-5.6-terra local/gpt-oss:20b \
    --reasoning-effort medium

# Required five-log pilot before the final run
python automated_scripts/benchmark_models.py --pilot

# With ground truth for accuracy scoring
python automated_scripts/benchmark_models.py --ground-truth data/evaluation/ground_truth.json
```

Results are saved to `results/benchmark/<timestamp>/` with per-model results, a comparison report, a printable summary table, and (when ground truth is provided) statistical significance tests and a cost-accuracy trade-off chart.

### Benchmark Outputs

When ground truth is available, the benchmark automatically produces:

| File | Description |
|------|-------------|
| `results_<provider>_<model>.json` | Raw per-log diagnosis results with token usage and cost |
| `comparison_report.json` | Side-by-side metrics including cost and accuracy |
| `comparison_table.txt` | Printable summary table |
| `statistical_tests.json` | McNemar's test, bootstrap 95% CIs, permutation test |
| `cost_accuracy_tradeoff.png` | Scatter plot: cost per diagnosis vs accuracy |

## Diagnose a Single Log

```python
import requests

response = requests.post(
    "http://localhost:8000/diagnose",
    json={
        "log_content": "<paste log here>",
        "provider": "openai",           # or "anthropic", "local"
        "model": "gpt-5.6-terra",
        "reasoning_effort": "medium",
        "temperature": 0.0,              # ignored by thesis reasoning models
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
