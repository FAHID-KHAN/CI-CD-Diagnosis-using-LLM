# Makefile for CI/CD Diagnosis Project

.PHONY: help install setup test run clean docker

help:
	@echo "Available commands:"
	@echo "  make install       - Install dependencies"
	@echo "  make setup         - Initial project setup"
	@echo "  make run          - Run API server"
	@echo "  make test         - Run tests"
	@echo "  make collect      - Collect training data"
	@echo "  make evaluate     - Run evaluation"
	@echo "  make study        - Start human study"
	@echo "  make docker       - Build and run with Docker"
	@echo "  make clean        - Clean generated files"

install:
	pip install -r requirements.txt

setup:
	python setup.py create_structure
	cp .env.template .env
	@echo "Setup complete! Edit .env with your API keys"

run:
	uvicorn src.api.main:app --reload --host 0.0.0.0 --port 8000

test:
	pytest tests/ -v

collect:
	python -m src.data_collection.data_collection --num-logs 500

evaluate:
	python -m src.evaluation.evaluation --test-data data/test_set/annotated.json

study:
	python -m src.human_study.human_study start 5000

docker:
	docker-compose up --build

clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	rm -rf .pytest_cache
	rm -rf build dist *.egg-info
