# CI/CD Log Diagnosis with LLMs

Automated diagnosis of CI/CD pipeline failures using Large Language Models.

Master's thesis project -- Tampere University.

## Project Structure

```
src/                        # Core library
  api/                      # FastAPI diagnostic service
    main.py                 #   Endpoints (/diagnose, /health, etc.)
    models.py               #   Pydantic models & enums
    filtering.py            #   Log filtering logic
    llm_service.py          #   LLM integration (OpenAI / Anthropic)
    grounding.py            #   Grounding verifier (hallucination check)
  data_collection/          # GitHub Actions log collector
  evaluation/               # Metrics & ablation framework
  rag/                      # RAG system (ChromaDB + docs)
  human_study/              # Web-based user study interface
  config.py                 # YAML config loader
  log_setup.py              # Logging setup

automated_scripts/          # CLI workflow scripts
  data_collection.py        #   Collect logs from GitHub repos
  triage.py                 #   Filter & deduplicate collected logs
  diagnose_logs.py          #   Send logs to API for diagnosis
  annotate.py               #   Annotate ground truth interactively
  evaluate_demo.py          #   Generate evaluation report & charts

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

## Workflow

The full pipeline runs in order:

```bash
make collect     # 1. Collect failed CI/CD logs from GitHub
make triage      # 2. Filter duplicates, cancelled runs, etc.
make run         # 3. Start the diagnostic API (separate terminal)
make diagnose    # 4. Send triaged logs to API for diagnosis
make annotate    # 5. Manually annotate ground truth
make evaluate    # 6. Generate evaluation report & charts
```

Run `make help` to see all available commands.

## Diagnose a Single Log

```python
import requests

response = requests.post(
    "http://localhost:8000/diagnose",
    json={
        "log_content": "<paste log here>",
        "provider": "openai",
        "model": "gpt-4o-mini",
        "use_filtering": True,
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