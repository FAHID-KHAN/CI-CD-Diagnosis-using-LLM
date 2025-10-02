#!/bin/bash

# Create main directories
mkdir -p .github/workflows
mkdir -p src/{api,data_collection,evaluation,rag,human_study}
mkdir -p data/{raw_logs/{github_actions,bugswarm},annotated_logs/exported,benchmark,documentation}
mkdir -p models
mkdir -p results/{evaluation/{baseline,ablation_filtering,ablation_temperature,rag_comparison,final_report},study}
mkdir -p configs
mkdir -p tests
mkdir -p notebooks
mkdir -p docs
mkdir -p examples
mkdir -p scripts
mkdir -p chroma_db

# Create .gitkeep files for empty directories
touch data/raw_logs/github_actions/.gitkeep
touch data/raw_logs/bugswarm/.gitkeep
touch data/annotated_logs/exported/.gitkeep
touch data/documentation/.gitkeep
touch models/.gitkeep
touch chroma_db/.gitkeep

# Create __init__.py files
touch src/__init__.py
touch src/api/__init__.py
touch src/data_collection/__init__.py
touch src/evaluation/__init__.py
touch src/rag/__init__.py
touch src/human_study/__init__.py
touch tests/__init__.py

echo "✓ Project structure created successfully!"