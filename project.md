# 🏗️ CI/CD Diagnosis System - Complete Architecture & Execution Guide

## 📋 Table of Contents
1. [System Architecture Overview](#system-architecture-overview)
2. [Component Details](#component-details)
3. [Data Flow Diagrams](#data-flow-diagrams)
4. [Complete Execution Guide](#complete-execution-guide)
5. [Thesis Evaluation Roadmap](#thesis-evaluation-roadmap)
6. [File Structure Reference](#file-structure-reference)

---

## 🎯 System Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                   CI/CD DIAGNOSIS SYSTEM                        │
│                 (Master's Thesis Project)                       │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Data Sources  │───▶│  Collection Layer│───▶│   Storage Layer │
└─────────────────┘    └──────────────────┘    └─────────────────┘
  • GitHub Actions           • Scrapers              • Raw Logs
  • BugSwarm Dataset         • API Clients           • JSON Files
  • Public Repos             • Filters               • Database
                                                     
                                 │
                                 ▼
                                 
┌─────────────────────────────────────────────────────────────────┐
│                      DIAGNOSTIC ENGINE                          │
├─────────────────┬───────────────────┬──────────────────────────┤
│   LLM Service   │  RAG System       │  Grounding Verifier      │
├─────────────────┼───────────────────┼──────────────────────────┤
│ • OpenAI API    │ • ChromaDB        │ • Citation Check         │
│ • Anthropic API │ • Vector Search   │ • Hallucination Detect   │
│ • Local Mock    │ • Documentation   │ • Confidence Scoring     │
└─────────────────┴───────────────────┴──────────────────────────┘
                                 
                                 │
                                 ▼
                                 
┌─────────────────────────────────────────────────────────────────┐
│                     EVALUATION FRAMEWORK                        │
├─────────────────┬───────────────────┬──────────────────────────┤
│   Baselines     │  Ablation Studies │  Human Evaluation        │
├─────────────────┼───────────────────┼──────────────────────────┤
│ • Regex         │ • Filtering       │ • Time-to-Insight        │
│ • Heuristics    │ • Temperature     │ • Actionability          │
│ • Rule-based    │ • RAG vs No-RAG   │ • User Satisfaction      │
└─────────────────┴───────────────────┴──────────────────────────┘
                                 
                                 │
                                 ▼
                                 
┌─────────────────────────────────────────────────────────────────┐
│                       THESIS OUTPUTS                            │
│  • Benchmark Dataset  • Evaluation Metrics  • Research Paper    │
│  • Open-Source Tool   • Human Study Data    • Presentation      │
└─────────────────────────────────────────────────────────────────┘
```

---

## 🔍 Component Details

### 1. Data Collection Layer (`src/data_collection/`)

**Purpose**: Gather real CI/CD failure logs from public sources

**Components**:
- `GitHubActionsCollector`: Scrapes failed workflows from GitHub
- `BugSwarmCollector`: Loads logs from BugSwarm dataset
- `LogAnnotationTool`: SQLite-based annotation interface
- `ErrorLineDetector`: Automated error detection

**Inputs**: 
- GitHub Personal Access Token
- BugSwarm dataset path

**Outputs**:
- `data/raw_logs/github_actions/*.json` - Raw collected logs
- `data/annotated_logs/*.json` - Annotated logs with ground truth

**Key Methods**:
```python
collector = GitHubActionsCollector(github_token)
logs = collector.collect_logs(num_logs=500)
collector.save_logs(logs, output_path)
```

---

### 2. Diagnostic API (`src/api/`)

**Purpose**: REST API for log diagnosis using LLMs

**Architecture**:
```
FastAPI Server (main.py)
    │
    ├─▶ LLMDiagnoser
    │     ├─▶ OpenAI Client
    │     ├─▶ Anthropic Client
    │     └─▶ Local Mock
    │
    ├─▶ LogFilter
    │     ├─▶ Keyword Filtering
    │     ├─▶ Context Windows
    │     └─▶ Smart Truncation
    │
    └─▶ GroundingVerifier
          ├─▶ Citation Checking
          ├─▶ Hallucination Detection
          └─▶ Confidence Scoring
```

**Endpoints**:
- `POST /diagnose` - Single log diagnosis
- `POST /diagnose/batch` - Batch processing
- `POST /upload` - File upload
- `GET /health` - Health check
- `GET /stats` - Usage statistics

**Request Format**:
```json
{
  "log_content": "string",
  "provider": "openai|anthropic|local",
  "model": "gpt-4o-mini",
  "temperature": 0.1,
  "use_filtering": true,
  "max_context_lines": 500
}
```

**Response Format**:
```json
{
  "log_id": "abc123",
  "error_type": "dependency_error",
  "failure_lines": [5, 6, 7],
  "root_cause": "string",
  "suggested_fix": "string",
  "confidence_score": 0.85,
  "grounded_evidence": [...],
  "execution_time_ms": 2341.5,
  "hallucination_detected": false
}
```

---

### 3. RAG System (`src/rag/`)

**Purpose**: Enhance diagnosis with documentation retrieval

**Architecture**:
```
RAG System
    │
    ├─▶ DocumentationScraper
    │     ├─▶ npm docs
    │     ├─▶ Maven docs
    │     ├─▶ pip docs
    │     └─▶ Docker docs
    │
    ├─▶ DocumentChunker
    │     └─▶ Section-based splitting
    │
    ├─▶ VectorStore (ChromaDB)
    │     ├─▶ SentenceTransformer
    │     └─▶ Semantic Search
    │
    └─▶ RAGEnhancedDiagnoser
          ├─▶ Context Detection
          ├─▶ Document Retrieval
          └─▶ Augmented Prompts
```

**Workflow**:
1. Scrape official documentation
2. Chunk into semantic sections
3. Generate embeddings
4. Store in ChromaDB
5. Retrieve relevant docs for each log
6. Augment LLM prompts with documentation

---

### 4. Evaluation Framework (`src/evaluation/`)

**Purpose**: Measure system performance scientifically

**Components**:

**A. Baseline Methods**
```python
class BaselineEvaluator:
    - regex_baseline()      # Pattern matching
    - heuristic_baseline()  # Rule-based
```

**B. Metrics Calculator**
```python
class MetricsCalculator:
    - calculate_line_overlap()        # Precision/Recall/F1
    - calculate_metrics()              # Overall metrics
    - calculate_per_error_type()       # Per-type breakdown
```

**C. Ablation Studies**
```python
class AblationStudy:
    - evaluate_filtering_strategies()  # Log filtering impact
    - evaluate_temperature_settings()  # Temperature sensitivity
    - evaluate_prompt_variations()     # Prompt engineering
```

**D. Visualization**
```python
class Visualizer:
    - plot_comparison()            # Bar charts
    - plot_confusion_matrix()      # Error classification
    - plot_hallucination_analysis() # Hallucination patterns
```

**Key Metrics**:
- **Precision**: TP / (TP + FP)
- **Recall**: TP / (TP + FN)
- **F1 Score**: 2 × (Precision × Recall) / (Precision + Recall)
- **Accuracy**: Correct classifications / Total
- **Hallucination Rate**: Ungrounded claims / Total claims
- **Mean Confidence**: Average confidence scores
- **Execution Time**: Average processing time

---

### 5. Human Study Interface (`src/human_study/`)

**Purpose**: Measure real-world developer impact

**Architecture**:
```
Flask Web Application
    │
    ├─▶ Consent Form
    ├─▶ Participant Demographics
    ├─▶ Task Interface
    │     ├─▶ Log Display
    │     ├─▶ Tool Output (conditional)
    │     └─▶ Response Form
    │
    ├─▶ Database (SQLite)
    │     ├─▶ Participants
    │     ├─▶ Tasks
    │     └─▶ Responses
    │
    └─▶ Analysis Tools
          ├─▶ Time Analysis
          ├─▶ Accuracy Analysis
          └─▶ Statistical Tests
```

**Study Protocol**:
1. Informed consent
2. Demographics collection
3. 8 diagnostic tasks (4 with tool, 4 without)
4. Ratings: confidence, difficulty, helpfulness
5. Statistical analysis (t-tests, effect sizes)

**Measured Variables**:
- Time-to-insight (seconds)
- Diagnostic accuracy (%)
- Confidence ratings (1-5)
- Tool helpfulness (1-5)
- Experience level effects

---

## 📊 Data Flow Diagrams

### End-to-End System Flow

```
START
  │
  ▼
┌─────────────────────┐
│  1. DATA COLLECTION │
└─────────────────────┘
  │
  ├─▶ GitHub API ────────┐
  ├─▶ BugSwarm Dataset ──┤
  └─▶ Manual Uploads ────┤
                         │
                         ▼
              ┌──────────────────┐
              │  Raw Log Storage │
              │  (JSON files)    │
              └──────────────────┘
                         │
                         ▼
┌─────────────────────────────────┐
│  2. AUTOMATED DIAGNOSIS         │
│  (via FastAPI)                  │
└─────────────────────────────────┘
  │
  ├─▶ Log Filtering
  ├─▶ LLM Analysis (OpenAI/Claude)
  ├─▶ RAG Enhancement (optional)
  └─▶ Grounding Verification
                         │
                         ▼
              ┌──────────────────────┐
              │  Diagnosis Results   │
              │  (JSON with metadata)│
              └──────────────────────┘
                         │
                         ▼
┌─────────────────────────────────┐
│  3. MANUAL ANNOTATION           │
│  (Ground Truth Creation)        │
└─────────────────────────────────┘
  │
  └─▶ Review AI diagnoses
  └─▶ Correct error types
  └─▶ Mark failure lines
  └─▶ Add fix descriptions
                         │
                         ▼
              ┌──────────────────────┐
              │  Benchmark Dataset   │
              │  (Annotated Test Set)│
              └──────────────────────┘
                         │
                         ▼
┌─────────────────────────────────┐
│  4. EVALUATION                  │
└─────────────────────────────────┘
  │
  ├─▶ Baseline Comparison
  ├─▶ Ablation Studies
  ├─▶ RAG vs No-RAG
  └─▶ Per-error-type Analysis
                         │
                         ▼
              ┌──────────────────┐
              │  Metrics Report  │
              │  (JSON + Plots)  │
              └──────────────────┘
                         │
                         ▼
┌─────────────────────────────────┐
│  5. HUMAN STUDY                 │
└─────────────────────────────────┘
  │
  ├─▶ Participant Recruitment
  ├─▶ Task Completion (web UI)
  └─▶ Statistical Analysis
                         │
                         ▼
              ┌──────────────────┐
              │  Study Results   │
              │  (Statistical)   │
              └──────────────────┘
                         │
                         ▼
┌─────────────────────────────────┐
│  6. THESIS WRITING              │
└─────────────────────────────────┘
  │
  └─▶ Combine all results
  └─▶ Generate tables/figures
  └─▶ Write analysis
  └─▶ Draw conclusions
                         │
                         ▼
                      END
```

---

### Diagnostic Request Flow

```
User/Script
    │
    │ HTTP POST /diagnose
    │ {log_content, provider, model, ...}
    ▼
┌─────────────────┐
│  FastAPI Server │
└─────────────────┘
    │
    │ 1. Validate request
    ▼
┌─────────────────┐
│   LogFilter     │ ◀── use_filtering=true?
└─────────────────┘
    │
    │ 2. Apply smart filtering
    │    - Extract error keywords
    │    - Get context windows
    │    - Truncate to max_context_lines
    ▼
┌─────────────────┐
│  LLMDiagnoser   │
└─────────────────┘
    │
    │ 3. Select provider
    ├─▶ OpenAI API ──────┐
    ├─▶ Anthropic API ───┤
    └─▶ Local Mock ──────┤
                         │
                         │ 4. Generate diagnosis
                         ▼
                  ┌──────────────┐
                  │  LLM Response│
                  │  (JSON)      │
                  └──────────────┘
                         │
                         │ 5. Parse response
                         ▼
┌──────────────────────────────────┐
│     GroundingVerifier            │
└──────────────────────────────────┘
    │
    │ 6. Verify citations
    │    - Check line numbers exist
    │    - Validate quoted content
    │    - Calculate grounding score
    ▼
┌─────────────────┐
│ Diagnosis Result│
│ + Metadata      │
└─────────────────┘
    │
    │ HTTP 200 Response
    │ {error_type, root_cause, ...}
    ▼
User/Script
```

---

### RAG-Enhanced Diagnosis Flow

```
Log Content
    │
    ▼
┌─────────────────────┐
│ Extract Tool Context│ (npm, maven, etc.)
└─────────────────────┘
    │
    │ Detected: "npm"
    ▼
┌─────────────────────┐
│  Vector Store Query │
│  (ChromaDB)         │
└─────────────────────┘
    │
    │ Query: "npm dependency error resolution"
    ▼
┌─────────────────────┐
│ Semantic Search     │
│ (Top 5 chunks)      │
└─────────────────────┘
    │
    │ Retrieved Documentation:
    │ - npm install docs
    │ - peer dependency guide
    │ - troubleshooting page
    ▼
┌─────────────────────┐
│ Augmented Prompt    │
└─────────────────────┘
    │
    │ Original Log + Documentation Context
    ▼
┌─────────────────────┐
│  LLM Analysis       │
└─────────────────────┘
    │
    │ Enhanced with official docs
    ▼
┌─────────────────────┐
│ Diagnosis + Citations│
│ (with doc URLs)     │
└─────────────────────┘
```

---

## 🚀 Complete Execution Guide

### Phase 1: Initial Setup (ONE TIME)

```bash
# 1. Project structure
cd ~/cicd_diagnosis_thesis
ls  # Verify: src/, data/, .venv/, etc.

# 2. Activate environment
source .venv/bin/activate

# 3. Verify installation
python -c "import fastapi, openai, anthropic; print('✓ All packages installed')"

# 4. Check API keys
cat .env | grep API_KEY
# Should show your OpenAI and GitHub tokens
```

---

### Phase 2: Data Collection (Week 1)

**Goal**: Collect 500-800 logs

**Script**: `scripts/data_collection.py` (already created)

```bash
# Run collection (repeat 10-16 times)
cd ~/cicd_diagnosis_thesis/scripts
python data_collection.py

# This creates:
# data/raw_logs/github_actions/batch1.json   (50 logs)
# data/raw_logs/github_actions/batch2.json   (50 logs)
# ... up to batch10-16.json

# Verify collection
ls -lh ../data/raw_logs/github_actions/
wc -l ../data/raw_logs/github_actions/*.json
```

**Expected Output**:
- 10-16 JSON files
- 500-800 total logs
- Mix of repositories and error types

---

### Phase 3: Auto-Diagnosis (Week 1-2)

**Goal**: Get AI diagnosis for all logs

**Terminal 1 - Start API**:
```bash
cd ~/cicd_diagnosis_thesis
source .venv/bin/activate
uvicorn src.api.main:app --reload --host 0.0.0.0 --port 8000

# Keep this running
```

**Terminal 2 - Run Diagnosis**:
```bash
cd ~/cicd_diagnosis_thesis/scripts
source ../.venv/bin/activate

# Diagnose batch 1
python diagnose_logs.py

# Edit script to process batch 2, 3, etc.
# Or create a loop script
```

**Cost**: $0.10-0.25 per 50 logs = $1-4 total for 500-800 logs

**Output**:
```
data/annotated_logs/diagnosed_batch1.json
data/annotated_logs/diagnosed_batch2.json
...
```

---

### Phase 4: Manual Annotation (Week 2-3)

**Goal**: Create ground truth labels

**Script**: Create `scripts/annotate.py`

```python
import sys, os
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(parent_dir, 'src'))

from data_collection.data_collection import LogAnnotationTool, LogAnnotation
import json
from datetime import datetime

tool = LogAnnotationTool(db_path=os.path.join(parent_dir, 'annotations.db'))

# Load diagnosed logs
with open(os.path.join(parent_dir, 'data/annotated_logs/diagnosed_batch1.json')) as f:
    logs = json.load(f)

print(f"Annotating {len(logs)} logs...")
print("For each log, verify AI diagnosis and provide corrections")
print()

for i, log in enumerate(logs, 1):
    print(f"\n{'='*70}")
    print(f"Log {i}/{len(logs)}")
    print(f"{'='*70}")
    print(f"Repository: {log['repository']}")
    print(f"AI Error Type: {log['diagnosis']['error_type']}")
    print(f"AI Root Cause: {log['diagnosis']['root_cause'][:150]}...")
    print(f"AI Suggested Fix: {log['diagnosis']['suggested_fix'][:150]}...")
    print()
    
    # Verify or correct
    correct_type = input("Correct error type (or Enter if AI correct): ").strip()
    if not correct_type:
        correct_type = log['diagnosis']['error_type']
    
    correct_cause = input("Correct root cause (or Enter if AI correct): ").strip()
    if not correct_cause:
        correct_cause = log['diagnosis']['root_cause']
    
    correct_fix = input("Correct fix (or Enter if AI correct): ").strip()
    if not correct_fix:
        correct_fix = log['diagnosis']['suggested_fix']
    
    # Save annotation
    annotation = LogAnnotation(
        log_id=log['log_id'],
        source='github_actions',
        repository=log['repository'],
        workflow_name=log['workflow'],
        failure_type=correct_type,
        failure_lines=log['diagnosis']['failure_lines'],
        root_cause=correct_cause,
        fix_description=correct_fix,
        log_content='',  # Already in raw logs
        annotator='fahid_khan',
        annotation_date=datetime.now().isoformat(),
        confidence=1.0
    )
    
    tool.save_annotation(annotation)
    print("✓ Saved")

# Export final test set
tool.export_annotations(os.path.join(parent_dir, 'data/benchmark/annotated_test_set.json'))
print(f"\n✅ All annotations exported!")
```

```bash
python scripts/annotate.py
```

**Output**: `data/benchmark/annotated_test_set.json` (your ground truth)

---

### Phase 5: Evaluation (Week 4-5)

**Goal**: Measure system performance

**Create**: `scripts/run_evaluation.py`

```python
import sys, os
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(parent_dir, 'src'))

from evaluation.evaluation import BenchmarkRunner, Visualizer
import os

# Run complete evaluation
benchmark = BenchmarkRunner(
    test_data_path=os.path.join(parent_dir, 'data/benchmark/annotated_test_set.json'),
    output_dir=os.path.join(parent_dir, 'results/evaluation')
)

print("Running baseline comparison...")
baseline_results = benchmark.run_baseline_comparison()

print("Generating visualizations...")
Visualizer.plot_comparison(
    baseline_results,
    "Baseline vs LLM Comparison",
    os.path.join(parent_dir, 'results/evaluation/baseline_comparison.png')
)

print("Generating final report...")
benchmark.generate_report(baseline_results, os.path.join(parent_dir, 'results/evaluation/final_report.json'))

print("✅ Evaluation complete!")
```

```bash
python scripts/run_evaluation.py
```

**Output**:
- `results/evaluation/baseline_comparison.png`
- `results/evaluation/confusion_matrix.png`
- `results/evaluation/final_report.json`

---

### Phase 6: RAG System (Week 5-6)

**Build Documentation Index**:

```python
import sys, os
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(parent_dir, 'src'))

from rag.rag_system import RAGSystem

rag = RAGSystem(persist_directory=os.path.join(parent_dir, 'chroma_db'))

print("Building documentation index (30-60 minutes)...")
rag.initialize(rebuild_index=True)

print("✅ RAG system ready!")
```

**Test RAG**:
```python
results = rag.search_documentation(
    query="npm dependency conflict resolution",
    tool="npm"
)

for r in results:
    print(f"Found: {r['title']}")
```

---

### Phase 7: Human Study (Week 6-7)

**Start Study Interface**:

```bash
cd ~/cicd_diagnosis_thesis
source .venv/bin/activate
python -m src.human_study.human_study start 5000
```

**Access**: http://localhost:5000

**Analyze Results**:

```bash
python -m src.human_study.human_study report results/study/
```

---

## 📊 Thesis Evaluation Roadmap

### Week-by-Week Plan

| Week | Phase | Tasks | Deliverables |
|------|-------|-------|--------------|
| 1 | Data Collection | Collect 500-800 logs | batch1-16.json |
| 2 | Auto-Diagnosis | Process all logs | diagnosed_*.json |
| 3 | Annotation | Manual verification | annotated_test_set.json |
| 4 | Baseline Eval | Regex, heuristics | baseline_report.json |
| 5 | Ablation Studies | Filtering, temperature | ablation_*.png |
| 6 | RAG System | Build + evaluate | rag_comparison.json |
| 7 | Human Study | Recruit + run | study_results.json |
| 8-12 | Writing | Draft thesis | thesis.pdf |

---

### Required Thesis Sections

#### 1. Introduction (5 pages)
- Problem statement
- Motivation
- Research questions
- Contributions

**Data Sources**:
- Statistics from data collection
- Example failure scenarios

#### 2. Background & Related Work (10 pages)
- CI/CD pipelines
- Log analysis techniques
- LLMs for software engineering
- Existing tools (Jenkins, etc.)

**Data Sources**:
- Literature review
- Tool comparisons

#### 3. Methodology (15 pages)
- System architecture (use diagrams above)
- Data collection process
- Diagnostic algorithm
- RAG implementation
- Evaluation design

**Data Sources**:
- Architecture diagrams
- Code snippets
- Algorithm pseudocode

#### 4. Dataset (5 pages)
- Collection statistics
- Error type distribution
- Log characteristics
- Annotation process

**Data Sources**:
- `data_collection.py` outputs
- Annotation statistics

#### 5. Baseline Evaluation (8 pages)
- Metrics definitions
- Baseline methods
- LLM performance
- Comparison tables

**Data Sources**:
- `results/evaluation/baseline_report.json`
- Confusion matrices
- Bar charts

#### 6. Ablation Studies (6 pages)
- Filtering strategies
- Temperature effects
- Prompt variations
- Context window analysis

**Data Sources**:
- `results/evaluation/ablation_*.json`
- Line plots
- Performance tables

#### 7. RAG Analysis (5 pages)
- Documentation retrieval
- RAG vs no-RAG
- Fix quality improvement
- Citation analysis

**Data Sources**:
- `results/evaluation/rag_comparison.json`
- User preference data

#### 8. Human Study (8 pages)
- Study design
- Participant demographics
- Time-to-insight analysis
- Statistical tests
- Qualitative feedback

**Data Sources**:
- `results/study/study_results.json`
- Box plots
- t-test results

#### 9. Discussion (5 pages)
- Key findings
- Limitations
- Threats to validity
- Practical implications

#### 10. Conclusion (3 pages)
- Summary of contributions
- Future work
- Final thoughts

**Total**: ~70 pages

---

### Key Figures & Tables

**Must-Have Figures**:
1. System architecture diagram
2. Data flow diagram
3. Dataset statistics (bar chart)
4. Baseline comparison (bar chart)
5. Confusion matrix
6. Ablation study results (line plots)
7. RAG comparison (bar chart)
8. Hallucination rate analysis
9. Time-to-insight box plots
10. Confidence distribution
11. Experience level effects

**Must-Have Tables**:
1. Dataset summary statistics
2. Baseline method comparison
3. Per-error-type performance
4. Ablation study results
5. Statistical significance tests
6. Human study demographics
7. Time analysis (with/without tool)
8. RAG retrieval metrics

---

## 📁 File Structure Reference

```
cicd_diagnosis_thesis/
├── src/                          # Source code
│   ├── api/
│   │   └── main.py              # FastAPI server
│   ├── data_collection/
│   │   └── data_collection.py   # Collection tools
│   ├── evaluation/
│   │   └── evaluation.py        # Evaluation framework
│   ├── rag/
│   │   └── rag_system.py        # RAG implementation
│   └── human_study/
│       └── human_study.py       # Study interface
│
├── scripts/                     # Execution scripts
│   ├── data_collection.py      # ✅ CREATED
│   ├── diagnose_logs.py        # Create next
│   ├── annotate.py             # Create next
│   └── run_evaluation.py       # Create next
│
├── data/                       # All data files
│   ├── raw_logs/
│   │   └── github_actions/
│   │       ├── batch1.json     # ✅ YOU HAVE THIS
│   │       ├── batch2.json     # Collect more
│   │       └── ...
│   ├── annotated_logs/
│   │   ├── diagnosed_batch1.json  # Create next
│   │   └── ...
│   └── benchmark/
│       └── annotated_test_set.json  # Final test set
│
├── results/                    # Evaluation results
│   ├── evaluation/
│   │   ├── baseline_report.json
│   │   ├── ablation_*.json
│   │   └── *.png
│   └── study/
│       ├── study_results.json
│       └── *.png
│
├── chroma_db/                  # Vector database
├── .venv/                      # Virtual environment
├── .env                        # API keys
└── README.md                   # Project docs
```

---

## 🎯 Quick Start Checklist

### Today:
- [x] Data collection working
- [x] Collected batch1.json (50 logs)
- [ ] Create diagnose_logs.py
- [ ] Start API and diagnose batch1
- [ ] Verify diagnosis output

### This Week:
- [ ] Collect 500-800 total logs
- [ ] Diagnose all logs
- [ ] Start manual annotation

### Next Week:
- [ ] Complete annotation
- [ ] Run baseline evaluation
- [ ] Generate first results

### Month 2:
- [ ] Ablation studies
- [ ] Build RAG system
- [ ] Human study

### Month 3:
- [ ] Write thesis
- [ ] Create presentation
- [ ] Defend!

---

## 💡 Tips for Success

1. **Backup Everything**: Git commit after each phase
2. **Document as You Go**: Keep a research journal
3. **Save Intermediate Results**: Never recompute expensive operations
4. **Version Your Data**: batch1_v1.json, batch1_v2.json
5. **Track Costs**: Monitor OpenAI dashboard daily
6. **Ask for Help**: Talk to supervisors regularly

---

## 🎓 You Are Here: ✅ Phase 2 (Data Collection Complete!)

**Next Step**: Create `scripts/diagnose_logs.py` and run auto-diagnosis!

Ready to continue? 🚀