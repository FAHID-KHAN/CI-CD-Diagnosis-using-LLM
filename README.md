# CI/CD Log Diagnosis with LLMs

Automated diagnosis of CI/CD pipeline failures using Large Language Models with Retrieval-Augmented Generation.

## 🎯 Overview

This project implements a comprehensive system for:
- Automated CI/CD failure diagnosis using LLMs
- Line-grounded error detection with hallucination prevention
- Retrieval-Augmented Generation (RAG) with official documentation
- Human evaluation framework for measuring real-world impact

## 📁 Project Structure

```
.
├── src/
│   ├── api/              # FastAPI diagnostic service
│   ├── data_collection/  # Log collection and annotation tools
│   ├── evaluation/       # Evaluation framework and metrics
│   ├── rag/             # RAG system for documentation retrieval
│   └── human_study/     # User study interface
├── data/                # Datasets and logs
├── results/             # Evaluation results
├── configs/             # Configuration files
└── notebooks/           # Jupyter notebooks for analysis
```

## 🚀 Quick Start

### 1. Installation

```bash
# Clone repository
git clone <your-repo-url>
cd cicd-diagnosis

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Configuration

```bash
# Copy environment template
cp .env.template .env

# Edit .env and add your API keys
nano .env
```

### 3. Run the API

```bash
# Start the diagnostic API
uvicorn src.api.main:app --reload

# API will be available at http://localhost:8000
# API documentation at http://localhost:8000/docs
```

### 4. Using Docker

```bash
# Build and run with Docker Compose
docker-compose up --build

# API: http://localhost:8000
# Study Interface: http://localhost:5000
```

## 📊 Usage Examples

### Diagnose a Log File

```python
import requests

with open('build_log.txt', 'r') as f:
    log_content = f.read()

response = requests.post(
    'http://localhost:8000/diagnose',
    json={
        'log_content': log_content,
        'provider': 'openai',
        'model': 'gpt-4',
        'use_filtering': True
    }
)

result = response.json()
print(f"Error Type: {result['error_type']}")
print(f"Root Cause: {result['root_cause']}")
print(f"Suggested Fix: {result['suggested_fix']}")
```

### Collect Training Data

```bash
python -m src.data_collection.data_collection \
    --source github_actions \
    --num-logs 500 \
    --output data/raw_logs/
```

### Run Evaluation

```bash
python -m src.evaluation.evaluation \
    --test-data data/test_set/annotated.json \
    --output results/evaluation/
```

### Build RAG Index

```bash
python -m src.rag.rag_system build-index \
    --sources npm maven pip docker \
    --output chroma_db/
```

### Conduct Human Study

```bash
python -m src.human_study.human_study start 5000
```

## 🔬 Research Components

### 1. Data Collection
- GitHub Actions log scraper
- BugSwarm dataset integration
- Annotation interface with error line detection

### 2. Diagnostic Engine
- Multi-provider LLM support (OpenAI, Anthropic)
- Log filtering strategies
- Grounding mechanism for hallucination prevention

### 3. RAG System
- Documentation scraper for npm, Maven, pip, Docker, etc.
- Vector database with semantic search
- Citation-enhanced fix suggestions

### 4. Evaluation Framework
- Baseline comparisons (regex, heuristics)
- Ablation studies (filtering, prompts, temperature)
- Hallucination rate measurement
- Per-error-type metrics

### 5. Human Study
- Web-based study interface
- Time-to-insight measurement
- Actionability assessment
- Statistical analysis tools

## 📈 Evaluation Metrics

- **Precision, Recall, F1**: Error line detection accuracy
- **Accuracy**: Error type classification
- **Hallucination Rate**: Percentage of ungrounded claims
- **Time-to-Insight**: Developer time savings
- **Actionability Score**: Human-rated fix quality

## 🤝 Contributing

This is a research project. For collaboration inquiries, please contact the authors.

## 📄 License

MIT License - see LICENSE file for details

## 📚 Citation

If you use this work in your research, please cite:

```bibtex
@mastersthesis{khan2025cicd,
  title={Leveraging Large Language Models for Automated Diagnosis of CI/CD Pipeline Failures},
  author={Khan, Fahid},
  year={2025},
  school={Tampere University}
}
```

## 👥 Authors

- Fahid Khan - Tampere University
- Supervisors: Jussi Rasko & Md Mahade Hasan

## 🙏 Acknowledgments

- BugSwarm dataset creators
- GitHub Actions community
- Open source contributors