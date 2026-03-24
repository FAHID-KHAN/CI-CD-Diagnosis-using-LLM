# Running the CI/CD Diagnosis System

## Prerequisites

- Python 3.11+
- OpenAI API key (required)
- Anthropic API key (optional, for Anthropic provider)
- GitHub token (for data collection -- classic token with `repo` + `workflow` scopes)
- Docker (optional, for containerized runs)

## Installation

```bash
cd /path/to/cicd_diagnosis_LLM
python -m venv .venv
source .venv/bin/activate

# Install as editable package
pip install -e .

# Set up environment variables
cp .env.template .env
# Edit .env and add OPENAI_API_KEY, GITHUB_TOKEN, etc.
```

## Full Workflow

The pipeline has 6 steps. Use `make help` to see all commands.

Alternatively, run the full pipeline with a single script:

```bash
./run_workflow.sh                          # Full 7-step pipeline
./run_workflow.sh --skip-collect --from 3  # Skip collection, resume from triage
./run_workflow.sh --skip-annotate          # Non-interactive (reuse ground truth)
./run_workflow.sh --only 7                 # Just regenerate evaluation
./run_workflow.sh --model gpt-4 --limit 10 # Custom model, limit logs
```

### 1. Collect logs

```bash
make collect
# Collects failed CI/CD logs from GitHub repos
# Backs up existing batch1.json before overwriting
# Output: data/raw_logs/github_actions/batch1.json
```

### 2. Triage logs

```bash
make triage
# Filters duplicates, cancelled runs, token errors
# Output: data/raw_logs/github_actions/batch1_triaged.json
```

### 3. Start the API

```bash
make run
# Starts FastAPI at http://localhost:8000
# Interactive docs at http://localhost:8000/docs
```

### 4. Diagnose logs (requires API running in another terminal)

```bash
make diagnose
# Sends triaged logs to the API for diagnosis
# Output: data/annotated_logs/diagnosed_batch1.json
```

### 5. Annotate ground truth

```bash
make annotate
# Interactive annotation of diagnosed logs for evaluation
# Records: error type correctness, root cause accuracy, fix quality
```

### 6. Evaluate

```bash
make evaluate
# Generates evaluation report with charts
# Output: results/ directory
```

## Smoke Test

With the API running:

```bash
python tests/test_smoke.py
```

## Docker

```bash
docker-compose up --build
# API: http://localhost:8000
```

## Configuration

YAML configs are in `configs/`:
- `api_config.yaml` -- API host, port, model settings
- `rag_config.yaml` -- RAG / vector DB settings
- `evaluation_config.yaml` -- evaluation parameters

These are loaded by `src/config.py`.

## Common Issues

- **Empty batch1.json**: Your GitHub token may be invalid. Generate a classic token with `repo` + `workflow` scopes.
- **Baselines show 0%**: Ground truth log IDs don't match the current raw data (likely caused by re-collecting). Re-annotate with `make annotate` to fix.
- **API 500 errors**: Check that `OPENAI_API_KEY` is set and valid in `.env`.
- **sentence-transformers fails**: Install `torch` first: `pip install --index-url https://download.pytorch.org/whl/cpu torch`
- **Tests call real LLM APIs**: Tests require the API running with valid keys. Consider adding a mock provider for CI.

## File Locations

| What | Where |
|---|---|
| Raw logs | `data/raw_logs/github_actions/` |
| Diagnosed logs | `data/annotated_logs/` |
| Evaluation output | `results/` |
| Vector DB (RAG) | `chroma_db/` |
| Configs | `configs/` |
