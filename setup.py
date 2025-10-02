# setup.py - Deployment configuration and setup scripts

import os
import sys
import subprocess
import json
from pathlib import Path
from typing import Dict, List

class ProjectSetup:
    """Complete project setup and configuration"""
    
    def __init__(self, project_dir: str = "."):
        self.project_dir = Path(project_dir)
        self.config = {}
    
    def create_project_structure(self):
        """Create project directory structure"""
        directories = [
            "src",
            "src/api",
            "src/data_collection",
            "src/evaluation",
            "src/rag",
            "src/human_study",
            "data",
            "data/raw_logs",
            "data/annotated_logs",
            "data/test_set",
            "models",
            "results",
            "results/evaluation",
            "results/study",
            "docs",
            "tests",
            "configs",
            "notebooks"
        ]
        
        print("Creating project structure...")
        for directory in directories:
            dir_path = self.project_dir / directory
            dir_path.mkdir(parents=True, exist_ok=True)
            print(f"  Created: {directory}/")
        
        # Create __init__.py files
        for directory in directories:
            if directory.startswith("src/"):
                init_file = self.project_dir / directory / "__init__.py"
                init_file.touch()
    
    def generate_requirements(self):
        """Generate requirements.txt"""
        requirements = """# Core API dependencies
fastapi==0.104.1
uvicorn==0.24.0
pydantic==2.5.0
python-multipart==0.0.6

# LLM APIs
openai==1.3.0
anthropic==0.7.0

# Data processing
pandas==2.1.3
numpy==1.26.2
sqlite3

# Web scraping for RAG
requests==2.31.0
beautifulsoup4==4.12.2

# Vector database
chromadb==0.4.18
sentence-transformers==2.2.2

# Evaluation
scikit-learn==1.3.2
scipy==1.11.4
matplotlib==3.8.2
seaborn==0.13.0

# Human study web interface
flask==3.0.0

# Testing
pytest==7.4.3
pytest-asyncio==0.21.1

# Utilities
python-dotenv==1.0.0
tqdm==4.66.1
"""
        
        requirements_path = self.project_dir / "requirements.txt"
        with open(requirements_path, 'w') as f:
            f.write(requirements.strip())
        
        print(f"Generated requirements.txt")
    
    def generate_env_template(self):
        """Generate .env.template"""
        env_template = """# API Keys
OPENAI_API_KEY=your_openai_key_here
ANTHROPIC_API_KEY=your_anthropic_key_here

# GitHub (for data collection)
GITHUB_TOKEN=your_github_token_here

# Database
DATABASE_URL=sqlite:///cicd_diagnosis.db

# RAG Configuration
VECTOR_DB_PATH=./chroma_db
EMBEDDING_MODEL=all-MiniLM-L6-v2

# API Configuration
API_HOST=0.0.0.0
API_PORT=8000

# Study Configuration
STUDY_PORT=5000
"""
        
        env_path = self.project_dir / ".env.template"
        with open(env_path, 'w') as f:
            f.write(env_template.strip())
        
        print("Generated .env.template")
    
    def generate_docker_config(self):
        """Generate Dockerfile and docker-compose.yml"""
        
        # Dockerfile
        dockerfile = """FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \\
    gcc \\
    g++ \\
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY . .

# Expose ports
EXPOSE 8000
EXPOSE 5000

# Run application
CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
"""
        
        with open(self.project_dir / "Dockerfile", 'w') as f:
            f.write(dockerfile.strip())
        
        # docker-compose.yml
        docker_compose = """version: '3.8'

services:
  api:
    build: .
    ports:
      - "8000:8000"
    environment:
      - OPENAI_API_KEY=${OPENAI_API_KEY}
      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
    volumes:
      - ./data:/app/data
      - ./results:/app/results
      - ./chroma_db:/app/chroma_db
    command: uvicorn src.api.main:app --host 0.0.0.0 --port 8000 --reload

  study_interface:
    build: .
    ports:
      - "5000:5000"
    volumes:
      - ./data:/app/data
      - ./results:/app/results
    command: python src/human_study/human_study.py start 5000
    depends_on:
      - api

volumes:
  chroma_db:
  data:
  results:
"""
        
        with open(self.project_dir / "docker-compose.yml", 'w') as f:
            f.write(docker_compose.strip())
        
        print("Generated Docker configuration")
    
    def generate_readme(self):
        """Generate comprehensive README.md"""
        readme = """# CI/CD Log Diagnosis with LLMs

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
source venv/bin/activate  # On Windows: venv\\Scripts\\activate

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
python -m src.data_collection.data_collection \\
    --source github_actions \\
    --num-logs 500 \\
    --output data/raw_logs/
```

### Run Evaluation

```bash
python -m src.evaluation.evaluation \\
    --test-data data/test_set/annotated.json \\
    --output results/evaluation/
```

### Build RAG Index

```bash
python -m src.rag.rag_system build-index \\
    --sources npm maven pip docker \\
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
"""
        
        with open(self.project_dir / "README.md", 'w') as f:
            f.write(readme.strip())
        
        print("Generated README.md")
    
    def generate_makefile(self):
        """Generate Makefile for common tasks"""
        makefile = """# Makefile for CI/CD Diagnosis Project

.PHONY: help install setup test run clean docker

help:
\t@echo "Available commands:"
\t@echo "  make install       - Install dependencies"
\t@echo "  make setup         - Initial project setup"
\t@echo "  make run          - Run API server"
\t@echo "  make test         - Run tests"
\t@echo "  make collect      - Collect training data"
\t@echo "  make evaluate     - Run evaluation"
\t@echo "  make study        - Start human study"
\t@echo "  make docker       - Build and run with Docker"
\t@echo "  make clean        - Clean generated files"

install:
\tpip install -r requirements.txt

setup:
\tpython setup.py create_structure
\tcp .env.template .env
\t@echo "Setup complete! Edit .env with your API keys"

run:
\tuvicorn src.api.main:app --reload --host 0.0.0.0 --port 8000

test:
\tpytest tests/ -v

collect:
\tpython -m src.data_collection.data_collection --num-logs 500

evaluate:
\tpython -m src.evaluation.evaluation --test-data data/test_set/annotated.json

study:
\tpython -m src.human_study.human_study start 5000

docker:
\tdocker-compose up --build

clean:
\tfind . -type d -name __pycache__ -exec rm -rf {} +
\tfind . -type f -name "*.pyc" -delete
\trm -rf .pytest_cache
\trm -rf build dist *.egg-info
"""
        
        with open(self.project_dir / "Makefile", 'w') as f:
            f.write(makefile)
        
        print("Generated Makefile")
    
    def generate_github_actions(self):
        """Generate GitHub Actions CI/CD workflow"""
        workflow = """name: CI/CD

on:
  push:
    branches: [ main, develop ]
  pull_request:
    branches: [ main ]

jobs:
  test:
    runs-on: ubuntu-latest
    
    steps:
    - uses: actions/checkout@v3
    
    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: '3.11'
    
    - name: Install dependencies
      run: |
        python -m pip install --upgrade pip
        pip install -r requirements.txt
        pip install pytest pytest-cov
    
    - name: Run tests
      run: |
        pytest tests/ --cov=src --cov-report=xml
    
    - name: Upload coverage
      uses: codecov/codecov-action@v3
      with:
        file: ./coverage.xml

  lint:
    runs-on: ubuntu-latest
    
    steps:
    - uses: actions/checkout@v3
    
    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: '3.11'
    
    - name: Install linting tools
      run: |
        pip install flake8 black mypy
    
    - name: Run linters
      run: |
        flake8 src/ --max-line-length=120
        black --check src/
        mypy src/ --ignore-missing-imports
"""
        
        workflows_dir = self.project_dir / ".github" / "workflows"
        workflows_dir.mkdir(parents=True, exist_ok=True)
        
        with open(workflows_dir / "ci.yml", 'w') as f:
            f.write(workflow.strip())
        
        print("Generated GitHub Actions workflow")
    
    def setup_all(self):
        """Run complete project setup"""
        print("\n" + "="*50)
        print("CI/CD Log Diagnosis Project Setup")
        print("="*50 + "\n")
        
        self.create_project_structure()
        self.generate_requirements()
        self.generate_env_template()
        self.generate_docker_config()
        self.generate_readme()
        self.generate_makefile()
        self.generate_github_actions()
        
        print("\n" + "="*50)
        print("Setup Complete!")
        print("="*50)
        print("\nNext steps:")
        print("1. Edit .env with your API keys")
        print("2. Run: pip install -r requirements.txt")
        print("3. Run: make run")
        print("\nFor more information, see README.md")

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "create_structure":
        setup = ProjectSetup()
        setup.create_project_structure()
    else:
        setup = ProjectSetup()
        setup.setup_all()