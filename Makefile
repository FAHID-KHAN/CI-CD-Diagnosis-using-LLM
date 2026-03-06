# Makefile for CI/CD Diagnosis Project

.PHONY: help install run test collect triage diagnose annotate evaluate docker clean

help:
	@echo "Available commands:"
	@echo "  make install    - Install dependencies"
	@echo "  make run        - Run API server"
	@echo "  make test       - Run tests"
	@echo "  make collect    - Collect CI/CD logs from GitHub"
	@echo "  make triage     - Triage collected logs"
	@echo "  make diagnose   - Diagnose logs via API"
	@echo "  make annotate   - Annotate diagnosed logs (ground truth)"
	@echo "  make evaluate   - Run demonstration evaluation"
	@echo "  make docker     - Build and run with Docker"
	@echo "  make clean      - Clean generated files"

install:
	pip install -e .

run:
	uvicorn src.api.main:app --reload --host 0.0.0.0 --port 8000

test:
	pytest tests/ -v

collect:
	python automated_scripts/data_collection.py

triage:
	python automated_scripts/triage.py

diagnose:
	python automated_scripts/diagnose_logs.py

annotate:
	python automated_scripts/annotate.py

evaluate:
	python automated_scripts/evaluate_demo.py

docker:
	docker-compose up --build

clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	rm -rf .pytest_cache build dist *.egg-info
