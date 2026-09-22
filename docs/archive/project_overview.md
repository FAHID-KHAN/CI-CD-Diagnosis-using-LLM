# Leveraging Large Language Models for Automated Diagnosis of CI/CD Pipeline Failures

**Master's Thesis - Complete Architecture & Implementation Documentation**

**Author:** Fahid Khan  
**Program:** Software, Web, and Cloud - Tampere University  
**Supervisors:** Jussi Rasko & Md Mahade Hasan  
**Date:** October 2025

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Research Context](#research-context)
3. [System Architecture](#system-architecture)
4. [Component Specifications](#component-specifications)
5. [Data Pipeline Architecture](#data-pipeline-architecture)
6. [Implementation Details](#implementation-details)
7. [Research Methodology](#research-methodology)
8. [Evaluation Framework](#evaluation-framework)
9. [Current Status & Issues](#current-status--issues)
10. [Execution Roadmap](#execution-roadmap)
11. [Expected Results](#expected-results)
12. [Technical Specifications](#technical-specifications)
13. [Appendices](#appendices)

---

## 1. Executive Summary

### 1.1 Research Problem

Continuous Integration/Continuous Deployment (CI/CD) pipelines are critical infrastructure in modern software development, but diagnosing failures remains time-consuming and error-prone. Developers must manually scan thousands of lines of build logs to identify root causes, significantly slowing development velocity.

### 1.2 Proposed Solution

This thesis develops and evaluates an automated diagnostic system using Large Language Models (LLMs) to:
- Analyze CI/CD failure logs
- Identify error types and root causes
- Provide actionable fix suggestions
- Ground outputs in actual log content to prevent hallucinations
- Optionally enhance diagnoses with official documentation retrieval (RAG)

### 1.3 Novel Contributions

1. **First open benchmark dataset** for CI/CD log diagnosis with line-level annotations
2. **Grounding mechanisms** to measure and prevent LLM hallucinations
3. **Systematic ablation studies** on log filtering, prompt design, and retrieval strategies
4. **Empirical human study** measuring developer time savings and actionability
5. **Production-ready diagnostic tool** with reproducible evaluation harness

### 1.4 Expected Impact

- Reduce diagnostic time by 50-70%
- Improve diagnostic accuracy from ~60% (baseline) to ~85% (LLM)
- Demonstrate RAG improvements of 25-35% in fix actionability
- Provide reusable benchmark for future research

---

## 2. Research Context

### 2.1 Background

**CI/CD Pipelines:** Automated systems that build, test, and deploy software upon code changes. When failures occur, developers receive log files containing thousands of lines of output.

**Common Failure Types:**
- Dependency errors (package conflicts, missing modules)
- Test failures (assertion errors, unexpected behavior)
- Build configuration issues (missing files, incorrect settings)
- Environment problems (timeouts, permissions, network)
- Syntax errors (compilation failures)

**Current Limitations:**
- Traditional tools (Jenkins Build Failure Analyzer) use regex patterns - brittle and unmaintainable
- Proprietary solutions (LogSage) lack reproducibility and open benchmarks
- No systematic measurement of hallucination rates
- Limited evidence of real developer impact

### 2.2 Research Questions

**RQ1:** Can LLMs accurately diagnose CI/CD failure types from log files?

**RQ2:** How do different log filtering strategies affect diagnostic accuracy and efficiency?

**RQ3:** Does retrieval-augmented generation improve fix quality and actionability?

**RQ4:** What is the measurable impact on developer time-to-insight and confidence?

**RQ5:** What is the hallucination rate and how can grounding mechanisms reduce it?

### 2.3 Research Scope

**In Scope:**
- GitHub Actions workflows
- BugSwarm dataset
- Common error types (dependency, test, build config, timeout, permission)
- OpenAI and Anthropic LLMs
- Line-level error detection
- English language logs

**Out of Scope:**
- Private enterprise CI/CD systems (Jenkins, CircleCI) - data unavailable
- Security vulnerabilities diagnosis
- Performance optimization recommendations
- Multi-language log analysis (non-English)
- Real-time streaming log analysis

---

## 3. System Architecture

### 3.1 High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        THESIS SYSTEM                            │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────┐
│  DATA SOURCES   │
├─────────────────┤
│ • GitHub API    │
│ • BugSwarm      │
│ • Manual Upload │
└────────┬────────┘
         │
         ▼
┌─────────────────────────────────────┐
│     DATA COLLECTION LAYER           │
├─────────────────────────────────────┤
│ • GitHubActionsCollector            │
│ • BugSwarmCollector                 │
│ • Log Sanitizer                     │
│ • Storage Manager                   │
└────────┬────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────┐
│     RAW LOG STORAGE                 │
│     (JSON Files)                    │
└────────┬────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────────┐
│                    DIAGNOSTIC ENGINE                            │
├────────────────┬──────────────────┬──────────────────┬──────────┤
│  Log Filter    │  LLM Interface   │  RAG System      │ Grounding│
├────────────────┼──────────────────┼──────────────────┼──────────┤
│ • Smart Filter │ • OpenAI Client  │ • Doc Scraper    │ • Citation│
│ • Context Win  │ • Claude Client  │ • ChromaDB       │   Check  │
│ • Truncation   │ • Local Mock     │ • Embeddings     │ • Hallu- │
│                │                  │ • Retrieval      │   cination│
└────────────────┴──────────────────┴──────────────────┴──────────┘
         │
         ▼
┌─────────────────────────────────────┐
│   DIAGNOSIS OUTPUT STORAGE          │
│   (JSON with Metadata)              │
└────────┬────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────────┐
│              ANNOTATION & EVALUATION LAYER                      │
├────────────────┬──────────────────┬──────────────────┬──────────┤
│  Manual Tool   │  Ground Truth    │  Baseline        │ Metrics  │
├────────────────┼──────────────────┼──────────────────┼──────────┤
│ • SQLite DB    │ • Human Labels   │ • Regex Method   │ • P/R/F1 │
│ • Annotation   │ • Error Types    │ • Heuristics     │ • Accuracy│
│   Interface    │ • Failure Lines  │ • Comparison     │ • Hallu  │
│                │ • Fix Descriptions│                 │   Rate   │
└────────────────┴──────────────────┴──────────────────┴──────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────────┐
│                   HUMAN STUDY INTERFACE                         │
├─────────────────────────────────────────────────────────────────┤
│ • Flask Web Application                                         │
│ • Consent & Demographics Collection                            │
│ • Timed Diagnostic Tasks                                       │
│ • With/Without Tool Conditions                                 │
│ • Statistical Analysis Engine                                  │
└────────┬────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────────┐
│                    RESEARCH OUTPUTS                             │
├─────────────────────────────────────────────────────────────────┤
│ • Benchmark Dataset (500-800 annotated logs)                   │
│ • Evaluation Metrics & Visualizations                          │
│ • Statistical Analysis Reports                                 │
│ • Thesis Document (~70 pages)                                  │
│ • Open Source Codebase                                         │
└─────────────────────────────────────────────────────────────────┘
```

### 3.2 Component Interaction Diagram

```
[User/Researcher]
       │
       ├──────────────────────────────────────┐
       │                                      │
       ▼                                      ▼
[Data Collection Script]          [FastAPI Server]
       │                                      │
       │ 1. collect_logs()                   │ 2. POST /diagnose
       ▼                                      │
[GitHub API]                                 │
       │                                      │
       │ 3. Returns ZIP logs                 │
       ▼                                      │
[Decompressor]                               │
       │                                      │
       │ 4. Extract text                     │
       ▼                                      │
[data/raw_logs/*.json]                      │
       │                                      │
       │ 5. Load logs                        │
       ├──────────────────────────────────>  │
                                              │
                                              ▼
                                    [LogFilter]
                                              │
                                              │ 6. Filter & extract context
                                              ▼
                                    [LLMDiagnoser]
                                              │
                                              ├─────> [OpenAI API]
                                              │           │
                                              │           │ 7. Analyze
                                              │           ▼
                                              │      [GPT-4o-mini]
                                              │           │
                                              │           │ 8. Return JSON
                                              │<──────────┘
                                              │
                                              ▼
                                    [GroundingVerifier]
                                              │
                                              │ 9. Check citations
                                              ▼
                                    [Diagnosis Result]
                                              │
                                              │ 10. Save
                                              ▼
                           [data/annotated_logs/*.json]
                                              │
                                              │ 11. Load for evaluation
                                              ▼
                                    [Evaluation Framework]
                                              │
                                              ├─────> [BaselineEvaluator]
                                              ├─────> [MetricsCalculator]
                                              ├─────> [Visualizer]
                                              │
                                              │ 12. Generate
                                              ▼
                                    [results/evaluation/*]
                                              │
                                              │ 13. Use in thesis
                                              ▼
                                         [Thesis.pdf]
```

### 3.3 Data Flow Architecture

**Phase 1: Data Collection**
```
GitHub Repos → API Request → ZIP Response → Decompress → Raw Text → JSON File → Storage
```

**Phase 2: Diagnosis**
```
Raw Log → Load → Filter (optional) → LLM Prompt → API Call → Parse Response → 
Verify Grounding → Add Metadata → Save Diagnosis → Storage
```

**Phase 3: Annotation**
```
Diagnosis Results → Display to Researcher → Manual Review → 
Corrections/Confirmations → Save to SQLite → Export Ground Truth → Benchmark Dataset
```

**Phase 4: Evaluation**
```
Ground Truth + AI Predictions → Compare → Calculate Metrics → 
Statistical Tests → Generate Visualizations → Results Report
```

**Phase 5: RAG Enhancement**
```
Error Detected → Extract Context (npm, maven, etc.) → Query Vector DB → 
Retrieve Docs → Augment Prompt → Enhanced LLM Call → Better Diagnosis
```

---

## 4. Component Specifications

### 4.1 Data Collection Component

**Location:** `src/data_collection/data_collection.py`

**Purpose:** Gather CI/CD failure logs from public sources

#### 4.1.1 GitHubActionsCollector

**Responsibilities:**
- Search GitHub for repositories with failed workflows
- Download failure logs via GitHub API
- Decompress ZIP responses
- Sanitize sensitive information
- Store logs with metadata

**Key Methods:**

```python
class GitHubActionsCollector:
    def __init__(self, github_token: str)
    def search_failed_workflows(query: str, max_results: int) -> List[Dict]
    def get_workflow_runs(owner: str, repo: str, status: str) -> List[Dict]
    def download_log(owner: str, repo: str, run_id: int) -> Optional[str]
    def collect_logs(num_logs: int) -> List[Dict]
```

**Input:**
- GitHub Personal Access Token
- Number of logs to collect
- Optional query parameters

**Output:**
```json
{
  "log_id": "gh_{owner}_{repo}_{run_id}",
  "source": "github_actions",
  "repository": "owner/repo",
  "workflow_name": "CI",
  "run_id": 12345,
  "log_content": "full log text...",
  "created_at": "2025-01-01T00:00:00Z",
  "url": "https://github.com/..."
}
```

**Current Issue:** ZIP decompression not implemented - logs saved as binary

**Fix Required:**
```python
import zipfile
import io

def download_log(self, owner: str, repo: str, run_id: int) -> Optional[str]:
    url = f"{self.base_url}/repos/{owner}/{repo}/actions/runs/{run_id}/logs"
    response = requests.get(url, headers=self.headers)
    
    if response.status_code == 200:
        # GitHub returns logs as ZIP
        try:
            with zipfile.ZipFile(io.BytesIO(response.content)) as z:
                file_list = z.namelist()
                if file_list:
                    with z.open(file_list[0]) as f:
                        return f.read().decode('utf-8', errors='ignore')
        except zipfile.BadZipFile:
            # Not a ZIP, return as text
            return response.text
    return None
```

#### 4.1.2 BugSwarmCollector

**Responsibilities:**
- Load logs from BugSwarm dataset
- Parse fail-pass pairs
- Extract relevant metadata

**Key Methods:**
```python
class BugSwarmCollector:
    def __init__(self, bugswarm_path: str)
    def load_bugswarm_artifacts() -> List[Dict]
    def load_log_file(log_path: str) -> Optional[str]
    def collect_logs(num_logs: int) -> List[Dict]
```

#### 4.1.3 LogAnnotationTool

**Responsibilities:**
- Store manual annotations in SQLite
- Track annotator, confidence, timestamps
- Export to JSON for evaluation

**Database Schema:**
```sql
CREATE TABLE annotations (
    log_id TEXT PRIMARY KEY,
    source TEXT,
    repository TEXT,
    workflow_name TEXT,
    failure_type TEXT,
    failure_lines TEXT,  -- JSON array
    root_cause TEXT,
    fix_description TEXT,
    log_content TEXT,
    annotator TEXT,
    annotation_date TEXT,
    confidence REAL
);
```

**Key Methods:**
```python
class LogAnnotationTool:
    def __init__(self, db_path: str)
    def save_annotation(annotation: LogAnnotation)
    def get_annotation(log_id: str) -> Optional[LogAnnotation]
    def export_annotations(output_path: str)
    def get_statistics() -> Dict
```

### 4.2 Diagnostic API Component

**Location:** `src/api/main.py`

**Purpose:** REST API for log diagnosis using LLMs

#### 4.2.1 FastAPI Server

**Technology Stack:**
- FastAPI 0.104.1
- Uvicorn (ASGI server)
- Pydantic for validation
- CORS enabled

**Endpoints:**

| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | /diagnose | Single log diagnosis |
| POST | /diagnose/batch | Batch processing |
| POST | /upload | File upload |
| GET | /health | Health check |
| GET | /stats | Usage statistics |

**Request Model:**
```python
class DiagnosisRequest(BaseModel):
    log_content: str
    provider: LLMProvider = "openai"  # openai, anthropic, local
    model: str = "gpt-4o-mini"
    temperature: float = 0.1
    use_filtering: bool = True
    max_context_lines: int = 500
```

**Response Model:**
```python
class DiagnosisResult(BaseModel):
    log_id: str
    error_type: ErrorType  # Enum
    failure_lines: List[int]
    root_cause: str
    suggested_fix: str
    confidence_score: float  # 0.0-1.0
    grounded_evidence: List[LogLine]
    reasoning: str
    execution_time_ms: float
    model_used: str
    hallucination_detected: bool
```

#### 4.2.2 LogFilter

**Purpose:** Reduce log size while preserving diagnostic information

**Filtering Strategies:**

1. **Keyword-based filtering:**
   - Identify lines containing error keywords
   - Extract context windows (10 lines before/after)
   - Remove build verbosity

2. **Smart filtering:**
   - Prioritize lines with "error", "failed", "exception"
   - Keep stack traces intact
   - Preserve dependency information
   - Remove timestamps, decorative output

3. **Context window extraction:**
   - Configurable window size (default: 10 lines)
   - Merge overlapping windows
   - Add line numbers

**Error Keywords:**
```python
ERROR_KEYWORDS = [
    'error', 'failed', 'failure', 'exception', 'fatal',
    'critical', 'panic', 'traceback', 'stack trace',
    'npm err!', 'gradle failed', 'maven error', 'pytest failed'
]
```

**Algorithm:**
```
1. Split log into lines
2. Identify error lines (keyword matching)
3. For each error line:
   a. Extract context (±window_size lines)
4. Merge overlapping contexts
5. If total > max_context_lines:
   a. Keep highest-priority contexts
6. Format with line numbers
7. Return filtered log
```

#### 4.2.3 LLMDiagnoser

**Purpose:** Interface with LLM providers for diagnosis

**Supported Providers:**
- **OpenAI:** GPT-4o-mini (primary), GPT-4 (if available)
- **Anthropic:** Claude Sonnet 4.5
- **Local:** Mock mode for testing

**Prompt Engineering:**

**System Prompt:**
```
You are an expert DevOps engineer analyzing CI/CD pipeline failures.

Analyze the following build log and provide a detailed diagnosis.

CRITICAL REQUIREMENTS:
1. You MUST cite exact log lines (with line numbers) as evidence
2. Every claim must reference specific lines from the log
3. Identify the root cause, not just symptoms
4. Provide actionable fix suggestions
```

**Output Format:**
```json
{
  "error_type": "dependency_error|test_failure|build_configuration|...",
  "failure_lines": [line numbers],
  "root_cause": "Clear explanation",
  "suggested_fix": "Specific steps",
  "confidence_score": 0.0-1.0,
  "grounded_evidence": [
    {"line_number": X, "content": "exact line", "is_error": true}
  ],
  "reasoning": "Step-by-step analysis"
}
```

**Key Methods:**
```python
class LLMDiagnoser:
    def __init__(self, provider: LLMProvider, model: str, api_key: str)
    def create_prompt(log_content: str) -> str
    async def diagnose(log_content: str, temperature: float) -> Dict
    async def _diagnose_openai(prompt: str, temperature: float) -> Dict
    async def _diagnose_anthropic(prompt: str, temperature: float) -> Dict
    async def _diagnose_local(prompt: str, temperature: float) -> Dict
```

#### 4.2.4 GroundingVerifier

**Purpose:** Prevent hallucinations by verifying citations

**Verification Process:**
```
1. Extract cited line numbers from LLM response
2. For each citation:
   a. Check line number exists in log
   b. Verify quoted content matches actual line
   c. Allow fuzzy matching (partial quotes OK)
3. Calculate grounding score:
   verified_citations / total_citations
4. Flag hallucination if score < 80%
5. Adjust confidence score accordingly
```

**Key Methods:**
```python
class GroundingVerifier:
    @staticmethod
    def verify_evidence(log_content: str, evidence: List[LogLine]) -> Tuple[bool, float]
```

**Output:**
- `hallucination_detected`: bool
- `grounding_score`: float (0.0-1.0)
- `adjusted_confidence`: original_confidence * grounding_score

### 4.3 RAG System Component

**Location:** `src/rag/rag_system.py`

**Purpose:** Enhance diagnoses with official documentation

#### 4.3.1 DocumentationScraper

**Target Sources:**
- npm (https://docs.npmjs.com)
- Maven (https://maven.apache.org/guides/)
- pip (https://pip.pypa.io/en/stable/)
- Docker (https://docs.docker.com)
- GitHub Actions (https://docs.github.com/en/actions)
- Gradle (https://docs.gradle.org)
- pytest (https://docs.pytest.org)
- Jest (https://jestjs.io/docs)

**Scraping Strategy:**
```
1. Start with base URL
2. Extract main content (remove nav, footer)
3. Follow documentation links
4. Limit to max_pages per source
5. Clean HTML to plain text
6. Store with metadata (source, title, URL)
```

**Key Methods:**
```python
class DocumentationScraper:
    def __init__(self, cache_dir: str)
    def scrape_documentation(source: str, max_pages: int) -> List[Dict]
    def _extract_content(soup: BeautifulSoup, source: str) -> str
    def _extract_doc_links(soup: BeautifulSoup, base_url: str) -> List[str]
```

#### 4.3.2 DocumentChunker

**Purpose:** Split documents into semantic sections for retrieval

**Chunking Strategy:**
```
1. Split by headers (# in Markdown, <h1-h6> in HTML)
2. Max chunk size: 500 chars
3. If section > 500 chars:
   a. Split by paragraphs
   b. Create overlapping chunks
4. Preserve section titles
5. Add source metadata
```

**Key Methods:**
```python
class DocumentChunker:
    @staticmethod
    def chunk_by_section(document: Dict, max_chunk_size: int) -> List[DocumentChunk]
```

**Output:**
```python
@dataclass
class DocumentChunk:
    chunk_id: str
    source: str  # "npm", "maven", etc.
    title: str
    content: str
    url: str
    section: str
    embedding: Optional[np.ndarray]
```

#### 4.3.3 VectorStore (ChromaDB)

**Purpose:** Semantic search over documentation

**Technology:**
- ChromaDB (vector database)
- SentenceTransformer (all-MiniLM-L6-v2)
- Cosine similarity search

**Indexing Process:**
```
1. Load document chunks
2. Generate embeddings:
   text → SentenceTransformer → 384-dim vector
3. Store in ChromaDB:
   - ids: chunk_id
   - embeddings: vectors
   - documents: text content
   - metadata: {source, title, url, section}
```

**Search Process:**
```
1. User query → Generate embedding
2. Similarity search in ChromaDB
3. Retrieve top-k chunks (default k=5)
4. Return chunks + relevance scores
```

**Key Methods:**
```python
class VectorStore:
    def __init__(self, collection_name: str, persist_directory: str)
    def add_documents(chunks: List[DocumentChunk])
    def search(query: str, n_results: int, source_filter: Optional[str]) -> RetrievalResult
```

#### 4.3.4 RAGEnhancedDiagnoser

**Purpose:** Combine LLM with retrieved documentation

**Workflow:**
```
1. Receive log content
2. Detect tool context (npm, maven, pip, etc.)
3. Query vector DB for relevant docs
4. Augment prompt with documentation
5. Call LLM with enhanced context
6. Extract citations from docs
7. Return diagnosis + doc references
```

**Augmented Prompt Structure:**
```
SYSTEM: You are an expert DevOps engineer...

RETRIEVED DOCUMENTATION:
[Doc 1 from npm]
Content: ...
Source: https://docs.npmjs.com/...

[Doc 2 from npm]
Content: ...
Source: https://docs.npmjs.com/...

BUILD LOG:
[Line 1] ...
[Line 2] npm ERR! ...

INSTRUCTIONS:
1. Analyze log
2. Use documentation to provide accurate fixes
3. Cite documentation sources
4. Include documentation URLs
```

**Key Methods:**
```python
class RAGEnhancedDiagnoser:
    def __init__(self, vector_store: VectorStore, llm_diagnoser: LLMDiagnoser)
    def extract_tool_context(log_content: str) -> List[str]
    def create_rag_prompt(log_content: str, error_type: str, retrieved_docs: RetrievalResult) -> str
    async def diagnose_with_rag(log_content: str, temperature: float) -> Dict
```

### 4.4 Evaluation Framework Component

**Location:** `src/evaluation/evaluation.py`

**Purpose:** Systematic performance measurement

#### 4.4.1 BaselineEvaluator

**Baseline Methods:**

**1. Regex Baseline:**
```python
def regex_baseline(log_content: str) -> Tuple[str, List[int]]:
    """
    Pattern-based error detection
    - Match: ModuleNotFoundError → dependency_error
    - Match: FAILED.*test → test_failure
    - Match: build.*failed → build_configuration
    """
```

**Patterns:**
```python
PATTERNS = {
    'dependency_error': [
        r'ModuleNotFoundError',
        r'ImportError',
        r'package.*not found',
        r'npm ERR! code ERESOLVE'
    ],
    'test_failure': [
        r'FAILED.*test',
        r'AssertionError',
        r'Test.*failed'
    ],
    'build_configuration': [
        r'build.*failed',
        r'gradle.*error',
        r'maven.*error'
    ],
    'timeout': [
        r'timeout',
        r'timed out'
    ],
    'permission_denied': [
        r'permission denied',
        r'access denied'
    ]
}
```

**2. Heuristic Baseline:**
```python
def heuristic_baseline(log_content: str) -> Tuple[str, List[int]]:
    """
    Keyword scoring system
    1. Count keyword occurrences per error type
    2. Assign scores to lines
    3. Select highest-scoring lines
    4. Classify by highest keyword count
    """
```

**Key Methods:**
```python
class BaselineEvaluator:
    @staticmethod
    def regex_baseline(log_content: str) -> Tuple[str, List[int]]
    @staticmethod
    def heuristic_baseline(log_content: str) -> Tuple[str, List[int]]
```

#### 4.4.2 MetricsCalculator

**Metrics Computed:**

**1. Line Overlap Metrics:**
```
Precision = True Positives / (True Positives + False Positives)
Recall = True Positives / (True Positives + False Negatives)
F1 = 2 * (Precision * Recall) / (Precision + Recall)

Where:
- True Positive: Predicted line is in actual failure lines
- False Positive: Predicted line not in actual failure lines
- False Negative: Actual failure line not predicted
```

**2. Classification Metrics:**
```
Accuracy = Correct Classifications / Total Classifications
Per-class Precision/Recall/F1
Confusion Matrix
```

**3. Hallucination Metrics:**
```
Hallucination Rate = Logs with Hallucinations / Total Logs
Mean Grounding Score = Average grounding scores
```

**4. Efficiency Metrics:**
```
Mean Execution Time
Mean Confidence Score
API Cost Estimate
```

**Key Methods:**
```python
class MetricsCalculator:
    @staticmethod
    def calculate_line_overlap(predicted: List[int], actual: List[int]) -> Tuple[float, float, float]
    @staticmethod
    def calculate_metrics(predictions: List[PredictionResult]) -> EvaluationMetrics
    @staticmethod
    def calculate_per_error_type_metrics(predictions: List[PredictionResult]) -> Dict
```

#### 4.4.3 AblationStudy

**Purpose:** Systematic evaluation of design choices

**Study 1: Filtering Strategies**
```python
strategies = {
    'no_filtering': {'use_filtering': False},
    'smart_500': {'use_filtering': True, 'max_context_lines': 500},
    'smart_1000': {'use_filtering': True, 'max_context_lines': 1000},
    'smart_2000': {'use_filtering': True, 'max_context_lines': 2000}
}

For each strategy:
    Run on test set
    Calculate metrics
    Compare performance vs cost
```

**Study 2: Temperature Settings**
```python
temperatures = [0.0, 0.1, 0.3, 0.5, 0.7, 1.0]

For each temperature:
    Run on test set
    Measure:
        - Accuracy
        - Confidence
        - Consistency (same log multiple times)
        - Hallucination rate
```

**Study 3: Prompt Variations**
```python
prompts = {
    'zero_shot': basic_prompt,
    'few_shot': prompt_with_examples,
    'chain_of_thought': prompt_requesting_reasoning
}

For each prompt:
    Run on test set
    Compare diagnostic quality
```

**Study 4: RAG vs No-RAG**
```python
conditions = ['no_rag', 'rag_enabled']

For each condition:
    Run on test set
    Measure:
        - Fix actionability
        - Documentation citation rate
        - User preference
```

**Key Methods:**
```python
class AblationStudy:
    @staticmethod
    def evaluate_filtering_strategies(test_logs: List[Dict]) -> Dict[str, EvaluationMetrics]
    @staticmethod
    def evaluate_temperature_settings(test_logs: List[Dict]) -> Dict[float, EvaluationMetrics]
    @staticmethod
    def evaluate_prompt_variations(test_logs: List[Dict], prompts: Dict[str, str]) -> Dict[str, EvaluationMetrics]
```

#### 4.4.4 Visualizer

**Purpose:** Generate publication-quality figures

**Visualization Types:**

1. **Comparison Bar Charts:**
   - Baseline vs LLM performance
   - Multiple metrics (P/R/F1/Accuracy)
   - Error bars for confidence intervals

2. **Confusion Matrices:**
   - Error type classification
   - Heatmap visualization
   - Annotated with counts

3. **Ablation Line Plots:**
   - Performance vs parameter
   - Multiple metrics on same plot
   - Shaded regions for variance

4. **Box Plots:**
   - Time-to-insight distribution
   - Confidence score distribution
   - Grouped by condition

5. **Hallucination Analysis:**
   - Rate by error type
   - Confidence vs hallucination scatter
   - Distribution plots

**Key Methods:**
```python
class Visualizer:
    @staticmethod
    def plot_comparison(results: Dict[str, EvaluationMetrics], title: str, output_path: str)
    @staticmethod
    def plot_confusion_matrix(predictions: List[PredictionResult], output_path: str)
    @staticmethod
    def plot_hallucination_analysis(predictions: List[PredictionResult], output_path: str)
```

#### 4.4.5 BenchmarkRunner

**Purpose:** Orchestrate complete evaluation

**Workflow:**
```
1. Load annotated test set
2. Run baseline methods
3. Run LLM diagnosis
4. Calculate all metrics
5. Generate visualizations
6. Create comprehensive report
7. Export to JSON/LaTeX tables
```

**Key Methods:**
```python
class BenchmarkRunner:
    def __init__(self, test_data_path: str, output_dir: str)
    def run_baseline_comparison() -> Dict[str, EvaluationMetrics]
    def generate_report(results: Dict[str, Any], output_file: str)
```

### 4.5 Human Study Component

**Location:** `src/human_study/human_study.py`

**Purpose:** Measure real developer impact

#### 4.5.1 Study Design

**Study Type:** Within-subjects repeated measures

**Independent Variables:**
- Tool condition (with/without diagnostic tool)
- Task difficulty (simple/moderate/complex)

**Dependent Variables:**
- Time-to-insight (seconds)
- Diagnostic accuracy (%)
- Confidence rating (1-5 Likert scale)
- Difficulty rating (1-5 Likert scale)
- Tool helpfulness (1-5 Likert scale, tool condition only)

**Counterbalancing:**
- Randomize task order
- Alternate tool condition

**Sample Size:** 10-15 participants

**Power Analysis:**
```
Effect size: d = 0.8 (large effect expected)
Alpha: 0.05
Power: 0.80
Required N: 12 participants
```

#### 4.5.2 Flask Web Application

**Routes:**

| Route | Method | Purpose |
|-------|--------|---------|
| / | GET | Consent form |
| /consent | POST | Process consent, collect demographics |
| /task | GET | Display diagnostic task |
| /submit_task | POST | Save task response |
| /complete | GET | Thank you page |

**Session Management:**
```python
session['participant_id'] = generate_id()
session['current_task'] = 0
session['tasks'] = generate_task_sequence()
session['start_time'] = timestamp
```

**Task Sequence Generation:**
```python
def generate_task_sequence(num_tasks=8):
    tasks = load_representative_logs()
    # Alternate tool condition
    for i, task in enumerate(tasks):
        task['with_assistance'] = (i % 2 == 0)
    return tasks
```

#### 4.5.3 Database Schema

**SQLite Tables:**

```sql
-- Participants
CREATE TABLE participants (
    participant_id TEXT PRIMARY KEY,
    years_experience INTEGER,
    ci_cd_experience TEXT,  -- 'none', 'beginner', 'intermediate', 'expert'
    primary_languages TEXT,  -- JSON array
    primary_tools TEXT,      -- JSON array
    consent_given BOOLEAN,
    timestamp TEXT
);

-- Tasks
CREATE TABLE tasks (
    task_id TEXT PRIMARY KEY,
    log_id TEXT,
    log_content TEXT,
    error_type TEXT,
    actual_fix TEXT
);

-- Responses
CREATE TABLE responses (
    response_id INTEGER PRIMARY KEY AUTOINCREMENT,
    participant_id TEXT,
    task_id TEXT,
    start_time REAL,
    end_time REAL,
    time_taken_seconds REAL,
    identified_error_type TEXT,
    identified_root_cause TEXT,
    suggested_fix TEXT,
    confidence_rating INTEGER,      -- 1-5
    difficulty_rating INTEGER,      -- 1-5
    with_assistance BOOLEAN,
    tool_helpfulness_rating INTEGER, -- 1-5, NULL if no assistance
    FOREIGN KEY (participant_id) REFERENCES participants(participant_id),
    FOREIGN KEY (task_id) REFERENCES tasks(task_id)
);
```

#### 4.5.4 Statistical Analysis

**Analyses to Perform:**

**1. Time-to-Insight Analysis:**
```
Paired t-test:
H0: mean(time_without) = mean(time_with)
H1: mean(time_without) > mean(time_with)

Calculate:
- Mean reduction
- Median reduction
- Effect size (Cohen's d)
- 95% confidence interval
```

**2. Accuracy Analysis:**
```
McNemar's test (paired binary outcomes)
H0: P(correct_without) = P(correct_with)

Calculate:
- Accuracy improvement
- Statistical significance
```

**3. Confidence Analysis:**
```
Wilcoxon signed-rank test (paired ordinal data)
H0: median(confidence_without) = median(confidence_with)

Calculate:
- Median difference
- Effect size (r)
```

**4. Experience Level Analysis:**
```
Mixed ANOVA:
- Between-subjects: experience level
- Within-subjects: tool condition

Interaction: Does experience moderate tool effect?
```

**Key Methods:**
```python
class StudyAnalyzer:
    def __init__(self, db: StudyDatabase)
    def analyze_time_to_insight() -> Dict
    def analyze_accuracy() -> Dict
    def analyze_confidence() -> Dict
    def analyze_by_experience() -> Dict
    def generate_report(output_path: str)
    def plot_results(output_dir: str)
```

---

## 5. Data Pipeline Architecture

### 5.1 End-to-End Data Flow

```
┌─────────────────────────────────────────────────────────────────┐
│ PHASE 1: DATA COLLECTION                                        │
└─────────────────────────────────────────────────────────────────┘

GitHub API
    ↓
GitHubActionsCollector.collect_logs(num_logs=50)
    ↓
For each repository:
    ↓
    search_failed_workflows() → List of repos
    ↓
    get_workflow_runs(status="failure") → List of runs
    ↓
    download_log(run_id) → ZIP file
    ↓
    decompress_zip() → Text content
    ↓
    sanitize() → Remove sensitive data
    ↓
    add_metadata(repo, workflow, url, timestamp)
    ↓
Save to: data/raw_logs/github_actions/batch{N}.json

Output Format:
[
  {
    "log_id": "gh_owner_repo_runid",
    "source": "github_actions",
    "repository": "owner/repo",
    "workflow_name": "CI",
    "run_id": 12345,
    "log_content": "...",
    "created_at": "2025-01-01T00:00:00Z",
    "url": "https://..."
  },
  ...
]

┌─────────────────────────────────────────────────────────────────┐
│ PHASE 2: AUTOMATED DIAGNOSIS                                    │
└─────────────────────────────────────────────────────────────────┘

Load: data/raw_logs/github_actions/batch{N}.json
    ↓
For each log:
    ↓
    log_content → LogFilter (if enabled)
        ↓
        Extract error keywords
        ↓
        Get context windows (±10 lines)
        ↓
        Merge overlapping contexts
        ↓
        Truncate to max_context_lines
        ↓
        Format with line numbers
    ↓
    filtered_log → LLMDiagnoser.diagnose()
        ↓
        create_prompt(filtered_log)
        ↓
        OpenAI API call (gpt-4o-mini)
            Request: {
                "model": "gpt-4o-mini",
                "messages": [...],
                "temperature": 0.1,
                "response_format": {"type": "json_object"}
            }
            ↓
            Response: {
                "error_type": "dependency_error",
                "failure_lines": [5, 6],
                "root_cause": "...",
                "suggested_fix": "...",
                "confidence_score": 0.85,
                "grounded_evidence": [...],
                "reasoning": "..."
            }
        ↓
        Parse JSON response
    ↓
    diagnosis → GroundingVerifier.verify_evidence()
        ↓
        For each cited line:
            Check line exists in log
            Verify content matches
        ↓
        Calculate grounding_score
        ↓
        Detect hallucination (score < 0.8)
        ↓
        Adjust confidence_score
    ↓
    Add metadata:
        - log_id
        - execution_time_ms
        - model_used
        - hallucination_detected
    ↓
Save to: data/annotated_logs/diagnosed_batch{N}.json

Output Format:
[
  {
    "log_id": "gh_owner_repo_runid",
    "repository": "owner/repo",
    "workflow": "CI",
    "url": "https://...",
    "diagnosis": {
      "log_id": "abc123",
      "error_type": "dependency_error",
      "failure_lines": [5, 6, 7],
      "root_cause": "npm peer dependency conflict...",
      "suggested_fix": "Update package.json...",
      "confidence_score": 0.85,
      "grounded_evidence": [...],
      "reasoning": "...",
      "execution_time_ms": 2341.5,
      "model_used": "openai/gpt-4o-mini",
      "hallucination_detected": false
    }
  },
  ...
]

┌─────────────────────────────────────────────────────────────────┐
│ PHASE 3: MANUAL ANNOTATION                                      │
└─────────────────────────────────────────────────────────────────┘

Load: data/annotated_logs/diagnosed_batch{N}.json
    ↓
For each log:
    ↓
    Display to researcher:
        - Repository
        - AI diagnosis
        - Original log (first 50 lines)
    ↓
    Researcher reviews and provides:
        - Correct error type (or confirms AI)
        - Correct root cause (or confirms AI)
        - Correct fix description
        - Failure line numbers
        - Confidence (1.0 = certain)
    ↓
    LogAnnotationTool.save_annotation()
        ↓
        Insert into SQLite database
    ↓
    Continue until all logs annotated
    ↓
LogAnnotationTool.export_annotations()
    ↓
Save to: data/benchmark/annotated_test_set.json

Output Format:
[
  {
    "log_id": "gh_owner_repo_runid",
    "source": "github_actions",
    "repository": "owner/repo",
    "workflow_name": "CI",
    "failure_type": "dependency_error",
    "failure_lines": [5, 6, 7],
    "root_cause": "npm peer dependency...",
    "fix_description": "Update React to v18...",
    "annotator": "researcher_name",
    "annotation_date": "2025-01-15T10:30:00Z",
    "confidence": 1.0
  },
  ...
]

┌─────────────────────────────────────────────────────────────────┐
│ PHASE 4: EVALUATION                                             │
└─────────────────────────────────────────────────────────────────┘

Load: 
- data/benchmark/annotated_test_set.json (ground truth)
- data/annotated_logs/diagnosed_batch*.json (AI predictions)
    ↓
BenchmarkRunner initialization
    ↓
┌─ Baseline Comparison ─────────────────────────────────────────┐
│                                                                │
│ For each log in test set:                                     │
│     ↓                                                          │
│     BaselineEvaluator.regex_baseline()                        │
│         → error_type, failure_lines                           │
│     ↓                                                          │
│     BaselineEvaluator.heuristic_baseline()                    │
│         → error_type, failure_lines                           │
│     ↓                                                          │
│     Load LLM prediction                                       │
│         → error_type, failure_lines                           │
│                                                                │
│ MetricsCalculator.calculate_metrics()                         │
│     ↓                                                          │
│     For each method (regex, heuristic, LLM):                  │
│         Accuracy = correct / total                            │
│         Precision = TP / (TP + FP)                            │
│         Recall = TP / (TP + FN)                               │
│         F1 = 2 * P * R / (P + R)                              │
│         Hallucination rate = flagged / total                  │
│                                                                │
│ Visualizer.plot_comparison()                                  │
│     → results/evaluation/baseline_comparison.png              │
│                                                                │
│ Visualizer.plot_confusion_matrix()                            │
│     → results/evaluation/confusion_matrix.png                 │
│                                                                │
└────────────────────────────────────────────────────────────────┘
    ↓
┌─ Ablation Studies ─────────────────────────────────────────────┐
│                                                                │
│ Study 1: Filtering strategies                                 │
│     For strategy in [no_filter, 500, 1000, 2000]:            │
│         Re-run diagnosis with strategy                        │
│         Calculate metrics                                     │
│         Compare: accuracy vs cost                             │
│     → results/evaluation/ablation_filtering.png               │
│                                                                │
│ Study 2: Temperature settings                                 │
│     For temp in [0.0, 0.1, 0.3, 0.5, 0.7, 1.0]:              │
│         Re-run diagnosis with temperature                     │
│         Calculate metrics                                     │
│         Compare: accuracy vs consistency                      │
│     → results/evaluation/ablation_temperature.png             │
│                                                                │
│ Study 3: RAG comparison                                       │
│     Re-run diagnosis with RAG enabled                         │
│     Compare: fix quality, citations                           │
│     → results/evaluation/rag_comparison.png                   │
│                                                                │
└────────────────────────────────────────────────────────────────┘
    ↓
BenchmarkRunner.generate_report()
    ↓
    Compile all metrics
    ↓
    Generate LaTeX tables
    ↓
    Create summary JSON
    ↓
Save to: results/evaluation/comprehensive_report.json

Output: Complete evaluation results for thesis

┌─────────────────────────────────────────────────────────────────┐
│ PHASE 5: HUMAN STUDY                                            │
└─────────────────────────────────────────────────────────────────┘

Start Flask app on port 5000
    ↓
Participant visits: http://localhost:5000
    ↓
Consent form → Demographics → Task sequence
    ↓
For each task (8 total):
    ↓
    Display log content
    ↓
    If with_assistance:
        Display tool diagnosis
    ↓
    Participant diagnoses (timed)
    ↓
    Participant rates confidence, difficulty
    ↓
    Save response to database
    ↓
Next task (alternate assistance condition)
    ↓
After 8 tasks: Thank you page
    ↓
Repeat for all participants (N=10-15)
    ↓
StudyAnalyzer.analyze_time_to_insight()
    - Paired t-test
    - Effect size calculation
    - Confidence intervals
    ↓
StudyAnalyzer.analyze_accuracy()
    - McNemar's test
    - Improvement percentage
    ↓
StudyAnalyzer.analyze_confidence()
    - Wilcoxon test
    - Median comparison
    ↓
StudyAnalyzer.generate_report()
    ↓
Save to: results/study/statistical_analysis.json
    ↓
StudyAnalyzer.plot_results()
    → results/study/time_boxplots.png
    → results/study/accuracy_bars.png
    → results/study/confidence_distribution.png

Output: Human study results for thesis
```

### 5.2 Data Format Specifications

**Raw Log Format:**
```json
{
  "log_id": "string (unique identifier)",
  "source": "github_actions | bugswarm",
  "repository": "owner/repo",
  "workflow_name": "string",
  "run_id": "integer (GitHub run ID)",
  "log_content": "string (full log text, newline-separated)",
  "created_at": "ISO 8601 timestamp",
  "url": "string (GitHub Actions run URL)"
}
```

**Diagnosis Format:**
```json
{
  "log_id": "string (unique identifier)",
  "error_type": "dependency_error | test_failure | build_configuration | timeout | permission_denied | syntax_error | network_error | unknown",
  "failure_lines": [1, 2, 3],
  "root_cause": "string (explanation)",
  "suggested_fix": "string (actionable steps)",
  "confidence_score": 0.85,
  "grounded_evidence": [
    {
      "line_number": 5,
      "content": "npm ERR! code ERESOLVE",
      "is_error": true
    }
  ],
  "reasoning": "string (step-by-step analysis)",
  "execution_time_ms": 2341.5,
  "model_used": "openai/gpt-4o-mini",
  "hallucination_detected": false
}
```

**Annotation Format:**
```json
{
  "log_id": "string",
  "source": "github_actions | bugswarm",
  "repository": "owner/repo",
  "workflow_name": "string",
  "failure_type": "dependency_error | ...",
  "failure_lines": [1, 2, 3],
  "root_cause": "string (ground truth)",
  "fix_description": "string (ground truth)",
  "annotator": "string (researcher name)",
  "annotation_date": "ISO 8601 timestamp",
  "confidence": 0.0-1.0
}
```

**Evaluation Results Format:**
```json
{
  "timestamp": "ISO 8601",
  "test_set_size": 500,
  "methods": {
    "regex_baseline": {
      "accuracy": 0.60,
      "precision": 0.58,
      "recall": 0.55,
      "f1_score": 0.56,
      "hallucination_rate": 0.0,
      "mean_execution_time_ms": 5.0
    },
    "heuristic_baseline": {
      "accuracy": 0.65,
      "precision": 0.63,
      "recall": 0.60,
      "f1_score": 0.61,
      "hallucination_rate": 0.0,
      "mean_execution_time_ms": 8.0
    },
    "llm_gpt4o_mini": {
      "accuracy": 0.85,
      "precision": 0.88,
      "recall": 0.82,
      "f1_score": 0.85,
      "hallucination_rate": 0.08,
      "mean_execution_time_ms": 2341.5
    }
  },
  "per_error_type": {
    "dependency_error": {
      "accuracy": 0.90,
      "count": 200
    },
    "test_failure": {
      "accuracy": 0.85,
      "count": 150
    }
  }
}
```

---

## 6. Implementation Details

### 6.1 Technology Stack

**Backend:**
- Python 3.11+
- FastAPI 0.104.1 (API framework)
- Uvicorn (ASGI server)
- Pydantic (data validation)

**LLM Integration:**
- OpenAI Python SDK 1.3.0
- Anthropic Python SDK 0.7.0

**Data Processing:**
- Pandas 2.1.3 (analysis)
- NumPy 1.26.2 (numerical)
- Requests 2.31.0 (HTTP)
- BeautifulSoup4 4.12.2 (HTML parsing)

**Vector Database:**
- ChromaDB 0.4.18
- Sentence-Transformers 2.2.2

**Evaluation:**
- Scikit-learn 1.3.2 (metrics)
- SciPy 1.11.4 (statistics)
- Matplotlib 3.8.2 (plotting)
- Seaborn 0.13.0 (visualization)

**Human Study:**
- Flask 3.0.0 (web interface)
- SQLite3 (database)

**Testing:**
- Pytest 7.4.3
- Pytest-asyncio 0.21.1

**Utilities:**
- Python-dotenv 1.0.0 (environment)
- TQDM 4.66.1 (progress bars)

### 6.2 Directory Structure

```
cicd_diagnosis_thesis/
│
├── .github/
│   └── workflows/
│       └── ci.yml                  # GitHub Actions CI/CD
│
├── src/                            # Source code
│   ├── __init__.py
│   │
│   ├── api/                        # FastAPI server
│   │   ├── __init__.py
│   │   └── main.py                 # 500+ lines
│   │
│   ├── data_collection/            # Data collection
│   │   ├── __init__.py
│   │   └── data_collection.py      # 600+ lines
│   │
│   ├── evaluation/                 # Evaluation framework
│   │   ├── __init__.py
│   │   └── evaluation.py           # 800+ lines
│   │
│   ├── rag/                        # RAG system
│   │   ├── __init__.py
│   │   └── rag_system.py           # 700+ lines
│   │
│   └── human_study/                # Human study
│       ├── __init__.py
│       └── human_study.py          # 900+ lines
│
├── scripts/                        # Execution scripts
│   ├── data_collection.py          # Run data collection
│   ├── diagnose_logs.py            # Run diagnosis
│   ├── annotate.py                 # Manual annotation
│   └── run_evaluation.py           # Run evaluation
│
├── data/                           # Data files
│   ├── raw_logs/
│   │   ├── github_actions/
│   │   │   ├── batch1.json         # 50 logs
│   │   │   ├── batch2.json
│   │   │   └── ...
│   │   └── bugswarm/
│   │       └── bugswarm_logs.json
│   │
│   ├── annotated_logs/
│   │   ├── diagnosed_batch1.json   # AI diagnoses
│   │   ├── diagnosed_batch2.json
│   │   └── ...
│   │
│   └── benchmark/
│       └── annotated_test_set.json # Ground truth
│
├── results/                        # Evaluation results
│   ├── evaluation/
│   │   ├── baseline/
│   │   │   ├── baseline_comparison.png
│   │   │   ├── confusion_matrix.png
│   │   │   └── report.json
│   │   │
│   │   ├── ablation_filtering/
│   │   │   ├── filtering_comparison.png
│   │   │   └── results.json
│   │   │
│   │   ├── ablation_temperature/
│   │   │   ├── temperature_analysis.png
│   │   │   └── results.json
│   │   │
│   │   └── final_report/
│   │       ├── comprehensive_report.json
│   │       └── latex_tables.tex
│   │
│   └── study/
│       ├── human_study.db          # Study database
│       ├── study_results.png       # Visualizations
│       ├── statistical_analysis.json
│       └── raw_responses.csv
│
├── chroma_db/                      # Vector database
│   └── (ChromaDB files)
│
├── configs/                        # Configuration files
│   ├── api_config.yaml
│   ├── evaluation_config.yaml
│   └── rag_config.yaml
│
├── tests/                          # Unit tests
│   ├── __init__.py
│   ├── test_api.py
│   ├── test_data_collection.py
│   ├── test_evaluation.py
│   ├── test_rag.py
│   └── test_human_study.py
│
├── notebooks/                      # Jupyter notebooks
│   ├── 01_data_exploration.ipynb
│   ├── 02_baseline_analysis.ipynb
│   ├── 03_ablation_studies.ipynb
│   ├── 04_rag_evaluation.ipynb
│   └── 05_human_study_analysis.ipynb
│
├── docs/                           # Documentation
│   ├── api_documentation.md
│   ├── dataset_description.md
│   ├── evaluation_guide.md
│   └── user_study_protocol.md
│
├── .venv/                          # Virtual environment
├── .env                            # Environment variables (gitignored)
├── .env.template                   # Environment template
├── .gitignore                      # Git ignore rules
├── setup.py                        # Setup script
├── requirements.txt                # Dependencies
├── Dockerfile                      # Docker configuration
├── docker-compose.yml              # Docker Compose
├── Makefile                        # Build automation
├── README.md                       # Project README
├── LICENSE                         # MIT License
└── pyproject.toml                  # Python project config
```

**Total Lines of Code:** ~3,500+ lines (excluding comments)

### 6.3 Configuration Management

**Environment Variables (`.env`):**
```bash
# LLM APIs
OPENAI_API_KEY=sk-proj-...
ANTHROPIC_API_KEY=sk-ant-...

# Data Collection
GITHUB_TOKEN=ghp_...

# Database
DATABASE_URL=sqlite:///cicd_diagnosis.db

# RAG System
VECTOR_DB_PATH=./chroma_db
EMBEDDING_MODEL=all-MiniLM-L6-v2

# API Server
API_HOST=0.0.0.0
API_PORT=8000

# Human Study
STUDY_PORT=5000
```

**Configuration Files:**

`configs/api_config.yaml`:
```yaml
api:
  host: "0.0.0.0"
  port: 8000
  debug: false
  
llm:
  default_provider: "openai"
  default_model: "gpt-4o-mini"
  temperature: 0.1
  max_tokens: 4096
  
filtering:
  enabled: true
  max_context_lines: 500
  window_size: 10
  
grounding:
  enabled: true
  threshold: 0.8
```

`configs/evaluation_config.yaml`:
```yaml
evaluation:
  test_data_path: "data/benchmark/annotated_test_set.json"
  output_dir: "results/evaluation"
  
baseline:
  methods: ["regex", "heuristic"]
  
ablation:
  filtering:
    strategies: [false, 500, 1000, 2000]
  temperature:
    values: [0.0, 0.1, 0.3, 0.5, 0.7, 1.0]
  
metrics:
  - precision
  - recall
  - f1_score
  - accuracy
  - hallucination_rate
```

### 6.4 Error Handling Strategy

**API Error Handling:**
```python
try:
    diagnosis = await llm_diagnoser.diagnose(log_content)
except openai.APIError as e:
    # OpenAI API error
    return JSONResponse(
        status_code=500,
        content={"detail": f"OpenAI API error: {str(e)}"}
    )
except openai.RateLimitError:
    # Rate limit exceeded
    return JSONResponse(
        status_code=429,
        content={"detail": "Rate limit exceeded. Please retry later."}
    )
except Exception as e:
    # Unexpected error
    logger.error(f"Unexpected error: {str(e)}")
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"}
    )
```

**Data Collection Error Handling:**
```python
try:
    logs = collector.collect_logs(num_logs)
except requests.exceptions.HTTPError as e:
    if e.response.status_code == 403:
        logger.error("GitHub API rate limit exceeded")
    elif e.response.status_code == 401:
        logger.error("Invalid GitHub token")
    else:
        logger.error(f"HTTP error: {e}")
except zipfile.BadZipFile:
    logger.error("Invalid ZIP file from GitHub API")
except Exception as e:
    logger.error(f"Unexpected error during collection: {e}")
```

### 6.5 Logging Strategy

**Logging Configuration:**
```python
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/app.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)
```

**What to Log:**
- API requests and responses
- LLM API calls (timing, costs)
- Data collection progress
- Errors and exceptions
- Evaluation runs
- Human study events

---

## 7. Research Methodology

### 7.1 Data Collection Methodology

**Sampling Strategy:**
- **Source:** GitHub Actions public workflows
- **Selection Criteria:**
  - Failed workflow runs
  - Popular repositories (>100 stars)
  - Recent failures (within 6 months)
  - Diverse languages and toolchains
- **Sample Size:** 500-800 logs
- **Stratification:** Aim for balanced error types

**Data Quality Measures:**
- Remove duplicate logs (same repo, same error)
- Filter out corrupted/truncated logs
- Sanitize sensitive information (API keys, tokens)
- Verify log completeness

### 7.2 Annotation Methodology

**Annotation Protocol:**

**Step 1: Initial Review**
- Read log (focus on last 100 lines)
- Identify obvious error patterns

**Step 2: Error Type Classification**
- Select from predefined categories
- If uncertain, mark as "unknown"

**Step 3: Failure Line Identification**
- Mark specific lines causing failure
- Include relevant context lines

**Step 4: Root Cause Description**
- Write 1-2 sentence explanation
- Focus on underlying issue, not symptoms

**Step 5: Fix Description**
- Provide actionable steps
- Be specific (exact commands, file changes)

**Step 6: Confidence Rating**
- 1.0 = Certain
- 0.8 = Confident
- 0.6 = Somewhat confident
- 0.4 = Uncertain

**Inter-Annotator Agreement:**
- Subset of 50 logs annotated by second researcher
- Calculate Cohen's Kappa
- Resolve disagreements through discussion

### 7.3 Experimental Design

**Research Design:** Mixed-methods

**Quantitative Components:**
1. Baseline comparison (controlled experiment)
2. Ablation studies (factorial design)
3. Human study (within-subjects)

**Qualitative Components:**
1. Error pattern analysis
2. Failure case analysis
3. User feedback (open-ended questions)

**Threats to Validity:**

**Internal Validity:**
- **Confound:** Log difficulty affects performance
  - **Mitigation:** Stratified sampling by complexity
- **Confound:** Experience level affects study results
  - **Mitigation:** Balanced participant recruitment, control analysis

**External Validity:**
- **Limitation:** GitHub Actions only (not Jenkins, CircleCI)
  - **Justification:** GitHub Actions is widely used, logs are public
- **Limitation:** English logs only
  - **Justification:** English dominant in OSS, simplifies annotation

**Construct Validity:**
- **Threat:** Accuracy metric may not capture full diagnostic quality
  - **Mitigation:** Multiple metrics (P/R/F1, confidence, actionability)

**Conclusion Validity:**
- **Threat:** Small sample size in human study
  - **Mitigation:** Power analysis, effect size reporting

### 7.4 Ethical Considerations

**Human Study Ethics:**
- Informed consent obtained
- Voluntary participation
- Right to withdraw anytime
- Data anonymization
- No deception

**Data Privacy:**
- Only public GitHub repositories
- Sanitize logs for sensitive data
- No personally identifiable information

**Reproducibility:**
- All code open-sourced
- Data (where permitted) publicly released
- Detailed methodology documentation

---

## 8. Evaluation Framework

### 8.1 Evaluation Metrics

**Primary Metrics:**

| Metric | Definition | Interpretation |
|--------|-----------|----------------|
| Accuracy | Correct classifications / Total | Overall correctness |
| Precision | TP / (TP + FP) | False alarm rate |
| Recall | TP / (TP + FN) | Coverage |
| F1 Score | 2 * P * R / (P + R) | Balanced measure |

**Secondary Metrics:**

| Metric | Definition | Interpretation |
|--------|-----------|----------------|
| Hallucination Rate | Ungrounded claims / Total | Trustworthiness |
| Mean Confidence | Avg confidence scores | Self-calibration |
| Execution Time | Avg time per diagnosis | Efficiency |
| API Cost | Estimated dollars | Economic viability |

**Human Study Metrics:**

| Metric | Definition | Measurement |
|--------|-----------|-------------|
| Time-to-Insight | Time to identify root cause | Seconds (continuous) |
| Diagnostic Accuracy | Correct diagnosis | Binary (0/1) |
| Confidence Rating | Self-reported confidence | Likert 1-5 |
| Difficulty Rating | Perceived task difficulty | Likert 1-5 |
| Tool Helpfulness | Tool assistance rating | Likert 1-5 |

### 8.2 Baseline Methods

**Regex Baseline:**
```
Accuracy: ~60%
Precision: ~58%
Recall: ~55%
F1: ~56%
Speed: <10ms per log
Cost: $0
```

**Heuristic Baseline:**
```
Accuracy: ~65%
Precision: ~63%
Recall: ~60%
F1: ~61%
Speed: <20ms per log
Cost: $0
```

**Expected LLM Performance:**
```
Accuracy: ~85%
Precision: ~88%
Recall: ~82%
F1: ~85%
Speed: ~2000ms per log
Cost: ~$0.003 per log
```

### 8.3 Statistical Tests

**Baseline Comparison:**
```
Test: McNemar's test (paired binary outcomes)
H0: P(correct_baseline) = P(correct_LLM)
H1: P(correct_LLM) > P(correct_baseline)
Alpha: 0.05
Expected p-value: < 0.001 (highly significant)
```

**Ablation Studies:**
```
Test: Repeated measures ANOVA
Factors: Filtering strategy, Temperature
DV: Accuracy, F1 score
Post-hoc: Tukey HSD
```

**Human Study:**
```
Test: Paired t-test (time-to-insight)
H0: mean(time_without) = mean(time_with)
H1: mean(time_without) > mean(time_with)
Expected Cohen's d: ~0.8 (large effect)

Test: McNemar's test (accuracy)
Test: Wilcoxon signed-rank (confidence)
```

---

## 9. Current Status & Issues

### 9.1 Completed Components

- [x] Project structure created
- [x] All source code written (~3500+ lines)
- [x] Virtual environment configured
- [x] Dependencies installed
- [x] API keys configured (OpenAI, Anthropic, GitHub)
- [x] FastAPI server implemented and tested
- [x] Data collection script created
- [x] First data collection run (50 logs)
- [x] Diagnosis script created
- [x] First diagnosis run (25 logs processed)

### 9.2 Critical Issue Identified

**Problem:** GitHub Actions API returns logs as compressed ZIP files

**Symptoms:**
- All 25 diagnosed logs returned error_type="unknown"
- Confidence scores = 0%
- Root cause: "Log appears corrupted"
- Log content starts with "PK" (ZIP signature)

**Evidence:**
```json
{
  "log_id": "gh_...",
  "diagnosis": {
    "error_type": "unknown",
    "confidence_score": 0.0,
    "root_cause": "The build log appears to be corrupted or improperly formatted...",
    "grounded_evidence": [
      {"line_number": 0, "content": "PK\\u0003\\u0004", "is_error": true}
    ]
  }
}
```

**Root Cause:** `GitHubActionsCollector.download_log()` saves ZIP bytes directly without decompression

**Impact:**
- Current batch1.json contains binary data, not text
- diagnosed_batch1.json contains invalid diagnoses
- Wasted ~$0.25 on API calls for corrupted data

### 9.3 Required Fix

**Location:** `src/data_collection/data_collection.py`

**Method:** `GitHubActionsCollector.download_log()`

**Required Changes:**
```python
import zipfile
import io

def download_log(self, owner: str, repo: str, run_id: int) -> Optional[str]:
    """Download workflow log"""
    url = f"{self.base_url}/repos/{owner}/{repo}/actions/runs/{run_id}/logs"
    
    response = requests.get(url, headers=self.headers)
    if response.status_code == 200:
        # GitHub returns logs as ZIP - MUST decompress
        try:
            with zipfile.ZipFile(io.BytesIO(response.content)) as z:
                # ZIP usually contains one file named like "0_build.txt"
                file_list = z.namelist()
                if file_list:
                    with z.open(file_list[0]) as f:
                        return f.read().decode('utf-8', errors='ignore')
        except zipfile.BadZipFile:
            # If not a ZIP (rare), return as-is
            return response.text
    return None
```

**Testing Strategy:**
1. Apply fix to code
2. Delete corrupted data:
   ```bash
   rm data/raw_logs/github_actions/batch1.json
   rm data/annotated_logs/diagnosed_batch1.json
   ```
3. Re-run collection: `python scripts/data_collection.py`
4. Verify logs are readable text (not binary)
5. Diagnose one log manually to confirm fix

**Expected After Fix:**
- Log content: Human-readable text with "npm ERR!", "test failed", etc.
- Diagnoses: error_type != "unknown", confidence > 0%
- Evidence: Actual error messages, not ZIP headers

### 9.4 Recovery Plan

**Immediate Actions:**
1. Fix `download_log()` method (5 minutes)
2. Delete corrupted data (1 minute)
3. Re-collect batch1 (10 minutes)
4. Verify fix with test diagnosis (5 minutes)

**Next 7 Days:**
1. Collect 500-800 logs (run script 10-16 times)
2. Diagnose all logs (~$2-4 cost)
3. Begin manual annotation

**Lessons Learned:**
- Always verify data before expensive processing
- Add data validation checks
- Document GitHub API quirks

**Documentation for Thesis:**
> "During initial data collection, we encountered a practical challenge common in CI/CD tooling: GitHub Actions API returns logs in compressed (ZIP) format. This required implementing automatic decompression before analysis. This finding highlights an important consideration for real-world deployment - log formats may vary across platforms and require preprocessing."

---

## 10. Execution Roadmap

### 10.1 Week-by-Week Timeline

| Week | Phase | Tasks | Deliverables | Hours |
|------|-------|-------|--------------|-------|
| 1 | Data Collection | • Fix ZIP decompression<br>• Collect 500-800 logs<br>• Verify data quality | • batch1-16.json<br>• Quality report | 15h |
| 2 | Auto-Diagnosis | • Start API server<br>• Diagnose all logs<br>• Monitor costs | • diagnosed_batch*.json<br>• Diagnosis report | 10h |
| 3 | Annotation | • Review 500-800 diagnoses<br>• Correct errors<br>• Label ground truth | • annotations.db<br>• annotated_test_set.json | 25h |
| 4 | Baseline Eval | • Run regex baseline<br>• Run heuristic baseline<br>• Compare vs LLM | • baseline_report.json<br>• comparison plots | 12h |
| 5 | Ablation Studies | • Filtering ablation<br>• Temperature ablation<br>• Analyze results | • ablation_*.json<br>• ablation plots | 15h |
| 6 | RAG System | • Build doc index<br>• Test RAG vs no-RAG<br>• Evaluate improvement | • rag_comparison.json<br>• RAG plots | 20h |
| 7 | Human Study | • Recruit participants<br>• Run study sessions<br>• Collect responses | • human_study.db<br>• Study results | 20h |
| 8-9 | Analysis | • Statistical tests<br>• Generate all figures<br>• Compile results | • All results files<br>• LaTeX tables | 20h |
| 10-14 | Writing | • Write all chapters<br>• Create figures<br>• Proofread | • thesis_draft.pdf | 60h |
| 15-16 | Finalization | • Supervisor feedback<br>• Revisions<br>• Final submission | • thesis_final.pdf<br>• presentation.pdf | 20h |

**Total Estimated Hours:** ~217 hours (~6 weeks full-time)

### 10.2 Critical Path

```
Fix ZIP Bug (Day 1)
    ↓
Data Collection (Week 1)
    ↓
Auto-Diagnosis (Week 2)
    ↓
Manual Annotation (Week 3) ← BOTTLENECK (time-intensive)
    ↓
Evaluation & Studies (Weeks 4-7)
    ↓
Analysis & Writing (Weeks 8-14)
    ↓
Defense (Week 16)
```

**Bottleneck:** Manual annotation of 500-800 logs

**Mitigation Strategies:**
1. Batch annotation (50 logs per session)
2. Focus on obvious cases first
3. Use AI suggestions as starting point
4. Recruit second annotator for subset (inter-rater reliability)

### 10.3 Risk Management

| Risk | Probability | Impact | Mitigation |
|------|------------|--------|------------|
| OpenAI quota exceeded | Medium | High | • Monitor usage daily<br>• Add credits preemptively<br>• Have Anthropic as backup |
| Annotation takes too long | High | Medium | • Simplify protocol<br>• Use AI pre-labels<br>• Reduce to 400 logs if needed |
| Human study recruitment fails | Medium | Medium | • Start recruiting early<br>• Offer small incentive<br>• Use social networks |
| RAG system too slow | Low | Low | • Start simple<br>• Can be optional contribution<br>• Focus on main results first |
| API changes/breaks | Low | High | • Version lock dependencies<br>• Test frequently<br>• Document API versions |

### 10.4 Contingency Plans

**If annotation takes too long:**
- Reduce dataset to 400 logs (still sufficient)
- Focus on most common error types only
- Use semi-automated approach (AI + human verification)

**If human study recruitment fails:**
- Reduce target to 8-10 participants (minimum viable)
- Extend recruitment period
- Offer small compensation ($10 gift card)
- Ask supervisors for contacts

**If compute budget exhausted:**
- Switch to cheaper models (gpt-3.5-turbo)
- Reduce ablation study scope
- Use cached results where possible
- Request additional budget from university

**If technical issues arise:**
- Have backup data collection sources (BugSwarm)
- Document issues as research findings
- Focus on achievable scope
- Adjust research questions if needed

---

## 11. Expected Results

### 11.1 Quantitative Results

**Baseline Comparison:**
```
Method          | Acc   | P     | R     | F1    | Time (ms) | Cost
----------------|-------|-------|-------|-------|-----------|------
Regex           | 0.60  | 0.58  | 0.55  | 0.56  | 5         | $0
Heuristic       | 0.65  | 0.63  | 0.60  | 0.61  | 8         | $0
LLM (ours)      | 0.85  | 0.88  | 0.82  | 0.85  | 2000      | $0.003
```

**Improvement:** +20-25 percentage points over best baseline

**Per-Error-Type Performance:**
```
Error Type       | Count | Acc   | P     | R     | F1
-----------------|-------|-------|-------|-------|------
Dependency       | 200   | 0.90  | 0.92  | 0.88  | 0.90
Test Failure     | 150   | 0.85  | 0.87  | 0.83  | 0.85
Build Config     | 100   | 0.82  | 0.85  | 0.79  | 0.82
Timeout          | 30    | 0.75  | 0.73  | 0.77  | 0.75
Permission       | 20    | 0.70  | 0.68  | 0.72  | 0.70
```

**Observation:** Better performance on common error types

**Ablation Study - Filtering:**
```
Strategy        | Acc   | F1    | Time (ms) | Cost   | Recommended
----------------|-------|-------|-----------|--------|------------
No filtering    | 0.86  | 0.86  | 3500      | $0.005 | No
Filter 500      | 0.85  | 0.85  | 2000      | $0.003 | Yes ✓
Filter 1000     | 0.85  | 0.85  | 2500      | $0.004 | No
Filter 2000     | 0.84  | 0.84  | 3000      | $0.004 | No
```

**Finding:** 500-line filtering optimal (minimal accuracy loss, major cost/time savings)

**Ablation Study - Temperature:**
```
Temperature | Acc   | F1    | Confidence | Consistency
------------|-------|-------|------------|------------
0.0         | 0.85  | 0.85  | 0.88       | 0.95
0.1         | 0.85  | 0.85  | 0.87       | 0.93
0.3         | 0.84  | 0.84  | 0.85       | 0.88
0.5         | 0.82  | 0.82  | 0.80       | 0.75
0.7         | 0.78  | 0.78  | 0.75       | 0.60
1.0         | 0.72  | 0.72  | 0.65       | 0.40
```

**Finding:** Temperature 0.0-0.1 best for diagnostic accuracy

**RAG Comparison:**
```
Metric                  | No RAG | With RAG | Improvement
------------------------|--------|----------|------------
Fix Actionability       | 0.70   | 0.90     | +29%
Documentation Citations | 0%     | 75%      | +75 pp
User Preference         | -      | 85%      | N/A
```

**Finding:** RAG significantly improves fix quality

**Hallucination Analysis:**
```
Condition           | Hallucination Rate | Mean Grounding Score
--------------------|-------------------|--------------------
No grounding check  | 22%               | 0.65
With grounding      | 8%                | 0.92
```

**Finding:** Grounding mechanisms reduce hallucinations by ~14 percentage points

**Human Study Results:**
```
Metric              | Without Tool | With Tool | Improvement | p-value
--------------------|--------------|-----------|-------------|--------
Time-to-Insight (s) | 480          | 180       | -62.5%      | <0.001
Accuracy (%)        | 60           | 85        | +25 pp      | <0.001
Confidence (1-5)    | 3.2          | 4.3       | +34%        | <0.001
```

**Finding:** Developers are 2.7x faster with 25% better accuracy

### 11.2 Qualitative Findings

**Error Pattern Analysis:**
- Dependency errors most common (40% of logs)
- Test failures often lack context in logs
- Build config errors have highest fix accuracy
- Timeout errors most difficult to diagnose

**Failure Case Analysis:**
- LLM struggles with novel/rare errors
- Multi-step failures confuse diagnosis
- Very long logs (>10k lines) degrade performance
- Obfuscated stack traces reduce accuracy

**User Feedback Themes:**
- Tool most helpful for unfamiliar error types
- Documentation citations increase trust
- Confidence scores generally well-calibrated
- Desire for interactive refinement

### 11.3 Thesis Contributions Summary

**Contribution 1: Open Benchmark Dataset**
- 500-800 annotated CI/CD logs
- Line-level failure annotations
- Multiple error types
- Publicly released

**Contribution 2: Grounding Mechanisms**
- Novel citation verification approach
- Measurable hallucination reduction
- Confidence score calibration

**Contribution 3: Systematic Evaluation**
- Comprehensive ablation studies
- Multiple baseline comparisons
- RAG enhancement analysis
- Reproducible harness

**Contribution 4: Human Impact Study**
- Empirical time savings measurement
- Accuracy improvement quantification
- Experience level analysis

**Contribution 5: Production-Ready Tool**
- Open-source implementation
- Documented API
- Deployment guide

---

## 12. Technical Specifications

### 12.1 System Requirements

**Development Environment:**
- Python 3.11 or higher
- 8GB RAM minimum (16GB recommended)
- 20GB disk space
- Internet connection (for API calls)

**Production Environment:**
- Ubuntu 20.04+ or macOS 12+
- Python 3.11+
- 16GB RAM
- 50GB disk space
- Stable internet connection

**API Requirements:**
- OpenAI API access (GPT-4o-mini)
- GitHub Personal Access Token
- Optional: Anthropic API access

### 12.2 Performance Specifications

**API Performance:**
- Throughput: ~30 diagnoses/minute (with rate limiting)
- Latency: 1-3 seconds per diagnosis (filtered logs)
- Concurrent requests: Supports 10 simultaneous users

**Data Collection:**
- Collection rate: ~5 logs/minute (GitHub API limits)
- Batch size: 50 logs recommended
- Expected time: 10 minutes per batch

**Evaluation:**
- Baseline evaluation: ~5 minutes for 500 logs
- Ablation studies: ~2 hours for complete suite
- Statistical analysis: ~10 minutes

**RAG System:**
- Index build time: 30-60 minutes (8 sources)
- Search latency: <100ms per query
- Storage: ~500MB for full index

### 12.3 Cost Specifications

**Development Costs:**
```
Component           | Cost Estimate | Notes
--------------------|---------------|------------------------
Data Collection     | $0            | GitHub API free
Auto-Diagnosis      | $2-4          | 500-800 logs × $0.003
Evaluation          | $1-2          | Multiple runs
RAG Testing         | $1-2          | Enhanced diagnoses
Human Study         | $2-3          | Tool assistance runs
Total               | $6-11         | Very affordable
```

**Cost per Log:**
- Collection: $0
- Diagnosis (filtered): ~$0.003
- Diagnosis (full): ~$0.005
- RAG-enhanced: ~$0.004

**Budget Recommendations:**
- Minimum: $10 for core research
- Recommended: $20 for full evaluation suite
- With buffer: $30 for iterations/mistakes

### 12.4 Scalability Considerations

**Current Scale:**
- 500-800 logs (thesis scope)
- 10-15 study participants
- 8 error types

**Future Scale Potential:**
- Database: SQLite → PostgreSQL for 10k+ logs
- API: Single server → Load balanced for production
- Storage: Local files → Cloud storage (S3)
- Caching: Add Redis for repeated diagnoses

### 12.5 Security Considerations

**API Security:**
- API keys stored in .env (gitignored)
- HTTPS for all external API calls
- Rate limiting to prevent abuse
- Input validation on all endpoints

**Data Privacy:**
- Only public repositories used
- Sanitize logs for sensitive data
- Anonymize human study participants
- No PII collected or stored

**Code Security:**
- Dependency scanning (GitHub Dependabot)
- No eval() or exec() in code
- Input validation prevents injection
- Secure default configurations

---

## 13. Appendices

### Appendix A: Command Reference

**Quick Start Commands:**
```bash
# Setup
cd cicd_diagnosis_thesis
source .venv/bin/activate
python setup.py

# Data Collection
python scripts/data_collection.py

# Start API
uvicorn src.api.main:app --reload

# Diagnose Logs
python scripts/diagnose_logs.py

# Annotate
python scripts/annotate.py

# Evaluate
python scripts/run_evaluation.py

# Human Study
python -m src.human_study.human_study start 5000
```

**Maintenance Commands:**
```bash
# Update dependencies
pip install --upgrade -r requirements.txt

# Run tests
pytest tests/ -v --cov=src

# Lint code
black src/
flake8 src/ --max-line-length=120

# Check types
mypy src/ --ignore-missing-imports

# Build Docker
docker-compose up --build

# Backup data
tar -czf backup_$(date +%Y%m%d).tar.gz data/ results/
```

### Appendix B: API Endpoint Reference

**POST /diagnose**
```bash
curl -X POST http://localhost:8000/diagnose \
  -H "Content-Type: application/json" \
  -d '{
    "log_content": "npm ERR! code ERESOLVE...",
    "provider": "openai",
    "model": "gpt-4o-mini",
    "temperature": 0.1,
    "use_filtering": true
  }'
```

**POST /diagnose/batch**
```bash
curl -X POST http://localhost:8000/diagnose/batch \
  -H "Content-Type: application/json" \
  -d '[
    {"log_content": "log1...", "provider": "openai", "model": "gpt-4o-mini"},
    {"log_content": "log2...", "provider": "openai", "model": "gpt-4o-mini"}
  ]'
```

**POST /upload**
```bash
curl -X POST http://localhost:8000/upload \
  -F "file=@build_log.txt"
```

**GET /health**
```bash
curl http://localhost:8000/health
```

**GET /stats**
```bash
curl http://localhost:8000/stats
```

### Appendix C: Error Type Taxonomy

| Error Type | Definition | Examples | Typical Causes |
|------------|-----------|----------|----------------|
| dependency_error | Package/module conflicts or missing dependencies | npm ERR! ERESOLVE, ModuleNotFoundError | Version conflicts, missing packages |
| test_failure | Test assertion failures or unexpected behavior | AssertionError, Test failed | Code bugs, incorrect test expectations |
| build_configuration | Build system or configuration issues | Missing build.gradle, Invalid pom.xml | Misconfiguration, missing files |
| timeout | Process exceeded time limit | Timeout after 30 minutes | Slow tests, infinite loops |
| permission_denied | Insufficient permissions to access resources | Permission denied, Access denied | File permissions, API permissions |
| syntax_error | Code syntax or parsing errors | SyntaxError, Parse error | Typos, language version issues |
| network_error | Network connectivity problems | Connection refused, DNS error | Network outages, firewall |
| unknown | Cannot determine specific type | - | Rare errors, corrupted logs |

### Appendix D: Troubleshooting Guide

**Problem: API not starting**
```bash
# Check if port 8000 is in use
lsof -i :8000

# Kill process using port
kill -9 <PID>

# Try different port
uvicorn src.api.main:app --port 8001
```

**Problem: Module not found errors**
```bash
# Ensure you're in project root
pwd

# Ensure venv is activated
which python  # Should point to .venv/bin/python

# Add src to PYTHONPATH
export PYTHONPATH="${PYTHONPATH}:${PWD}/src"
```

**Problem: API key not found**
```bash
# Verify .env file exists
ls -la .env

# Check keys are loaded
python -c "from dotenv import load_dotenv; import os; load_dotenv(); print(os.getenv('OPENAI_API_KEY')[:20])"
```

**Problem: ZIP decompression fails**
```bash
# Check if zipfile module is available
python -c "import zipfile; print('OK')"

# Try manual decompression
python -c "
import zipfile, io, requests
response = requests.get('URL_HERE')
with zipfile.ZipFile(io.BytesIO(response.content)) as z:
    print(z.namelist())
"
```

**Problem: Slow diagnosis**
```bash
# Enable filtering
# Set use_filtering=true in request

# Reduce context
# Set max_context_lines=300

# Use faster model
# Use gpt-3.5-turbo instead of gpt-4o-mini
```

### Appendix E: Research Ethics Checklist

- [ ] Informed consent obtained from all participants
- [ ] Voluntary participation explained
- [ ] Right to withdraw communicated
- [ ] Data anonymization implemented
- [ ] No deception used in study
- [ ] Only public data collected
- [ ] Sensitive information sanitized
- [ ] Institutional review board (IRB) approval obtained (if required)
- [ ] Data storage complies with GDPR/privacy laws
- [ ] Code and data sharing permissions secured

### Appendix F: Publication Checklist

**For Thesis Submission:**
- [ ] Title page with committee signatures
- [ ] Abstract (max 300 words)
- [ ] Acknowledgments
- [ ] Table of contents
- [ ] List of figures
- [ ] List of tables
- [ ] All chapters complete
- [ ] References formatted (IEEE or ACM style)
- [ ] Appendices included
- [ ] Proofread for typos/grammar
- [ ] PDF generated and verified
- [ ] Submitted via university portal

**For Potential Conference Paper:**
- [ ] Abstract (150-300 words)
- [ ] Introduction with motivation
- [ ] Related work section
- [ ] Methodology description
- [ ] Evaluation results
- [ ] Discussion and limitations
- [ ] Conclusion and future work
- [ ] References (20-40 papers)
- [ ] Figures and tables formatted
- [ ] Anonymous version (if double-blind)
- [ ] Page limit adhered to
- [ ] Submitted before deadline

**Potential Venues:**
- ICSE (International Conference on Software Engineering)
- FSE (Foundations of Software Engineering)
- ASE (Automated Software Engineering)
- MSR (Mining Software Repositories)
- ICSME (Software Maintenance and Evolution)

### Appendix G: Future Work Ideas

**Short-term Improvements:**
1. Add support for more CI/CD platforms (Jenkins, CircleCI, GitLab CI)
2. Implement real-time streaming log analysis
3. Add interactive refinement (user feedback loop)
4. Support multiple programming languages
5. Develop VS Code extension

**Research Extensions:**
1. Multi-modal analysis (logs + code + tests)
2. Proactive failure prediction
3. Transfer learning across CI/CD platforms
4. Automated fix generation and application
5. Root cause clustering and pattern mining

**Long-term Vision:**
1. Integrated development environment (IDE) plugin
2. Continuous learning from developer feedback
3. Enterprise-grade deployment
4. Multi-language support (non-English logs)
5. Community-driven error knowledge base

### Appendix H: Dataset Statistics Template

**Raw Data Collection:**
```
Total logs collected: ___
Date range: ___ to ___
Unique repositories: ___
Unique workflows: ___
Average log size: ___ lines
Median log size: ___ lines
Min/Max log size: ___ / ___ lines
```

**Error Type Distribution:**
```
Error Type          | Count | Percentage
--------------------|-------|------------
dependency_error    | ___   | ___%
test_failure        | ___   | ___%
build_configuration | ___   | ___%
timeout             | ___   | ___%
permission_denied   | ___   | ___%
syntax_error        | ___   | ___%
network_error       | ___   | ___%
unknown             | ___   | ___%
--------------------|-------|------------
TOTAL               | ___   | 100%
```

**Repository Language Distribution:**
```
Language    | Count | Percentage
------------|-------|------------
Python      | ___   | ___%
JavaScript  | ___   | ___%
Java        | ___   | ___%
C++         | ___   | ___%
Go          | ___   | ___%
Other       | ___   | ___%
```

**Annotation Statistics:**
```
Total logs annotated: ___
Annotation time: ___ hours
Average time per log: ___ minutes
Annotator agreement (Cohen's κ): ___
Annotation confidence (mean): ___
```

### Appendix I: LaTeX Table Templates

**Baseline Comparison Table:**
```latex
\begin{table}[h]
\centering
\caption{Performance Comparison: Baselines vs. LLM}
\label{tab:baseline_comparison}
\begin{tabular}{lcccc}
\toprule
Method & Accuracy & Precision & Recall & F1 Score \\
\midrule
Regex Baseline      & 0.60 & 0.58 & 0.55 & 0.56 \\
Heuristic Baseline  & 0.65 & 0.63 & 0.60 & 0.61 \\
GPT-4o-mini (Ours)  & \textbf{0.85} & \textbf{0.88} & \textbf{0.82} & \textbf{0.85} \\
\bottomrule
\end{tabular}
\end{table}
```

**Ablation Study Table:**
```latex
\begin{table}[h]
\centering
\caption{Ablation Study: Filtering Strategies}
\label{tab:ablation_filtering}
\begin{tabular}{lccccc}
\toprule
Strategy & Accuracy & F1 & Time (ms) & Cost (\$) & Recommended \\
\midrule
No Filtering   & 0.86 & 0.86 & 3500 & 0.005 & \\
Filter 500     & 0.85 & 0.85 & 2000 & 0.003 & \checkmark \\
Filter 1000    & 0.85 & 0.85 & 2500 & 0.004 & \\
Filter 2000    & 0.84 & 0.84 & 3000 & 0.004 & \\
\bottomrule
\end{tabular}
\end{table}
```

**Human Study Results Table:**
```latex
\begin{table}[h]
\centering
\caption{Human Study Results: Time-to-Insight and Accuracy}
\label{tab:human_study}
\begin{tabular}{lccccc}
\toprule
Metric & Without Tool & With Tool & Improvement & Cohen's d & p-value \\
\midrule
Time (s)        & 480  & 180 & -62.5\% & 0.82 & <0.001 \\
Accuracy (\%)   & 60   & 85  & +25 pp  & 0.75 & <0.001 \\
Confidence (1-5)& 3.2  & 4.3 & +34\%   & 0.68 & <0.001 \\
\bottomrule
\end{tabular}
\end{table}
```

### Appendix J: Key References

**CI/CD and Log Analysis:**
1. Tomassi et al. (2019). "BugSwarm: Mining and Continuously Growing a Dataset of Reproducible Failures and Fixes." ICSE.
2. Chen et al. (2016). "A Survey on the Use of Topic Models When Mining Software Repositories." ESE.
3. Dagenais & Robillard (2010). "Creating and Evolving Developer Documentation." FSE.

**LLMs for Software Engineering:**
4. LogSage (2025). "Large Language Model Framework for CI/CD Log Diagnosis."
5. Skeppner & Thorsteinsson (2025). "From Logs to Insights: Optimizing LLM Parameters for Root Cause Detection."
6. LogInsight (2025). "Interpretable Log Diagnosis with LLMs."

**Retrieval-Augmented Generation:**
7. Lewis et al. (2021). "Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks." NeurIPS.
8. Gao et al. (2023). "Retrieval-Augmented Generation for Large Language Models: A Survey."

**Evaluation Methodologies:**
9. Chiang et al. (2024). "Chatbot Arena: An Open Platform for Evaluating LLMs by Human Preference."
10. Rajpurkar et al. (2016). "SQuAD: 100,000+ Questions for Machine Comprehension of Text." EMNLP.

### Appendix K: Glossary

**CI/CD:** Continuous Integration/Continuous Deployment - automated software development practices

**LLM:** Large Language Model - AI models trained on vast text data (e.g., GPT-4, Claude)

**RAG:** Retrieval-Augmented Generation - enhancing LLMs with external knowledge retrieval

**Grounding:** Ensuring LLM outputs are supported by actual input data (preventing hallucinations)

**Hallucination:** When LLM generates plausible but incorrect or unsupported information

**Ablation Study:** Systematic removal/modification of system components to measure their impact

**Baseline:** Simple reference method for comparison (e.g., regex, heuristics)

**Precision:** True Positives / (True Positives + False Positives)

**Recall:** True Positives / (True Positives + False Negatives)

**F1 Score:** Harmonic mean of precision and recall

**Cohen's Kappa:** Inter-rater reliability measure for categorical judgments

**Effect Size:** Standardized measure of difference magnitude (e.g., Cohen's d)

**Artifact:** In thesis context, a delivered tool/dataset/model

**Workflow:** In GitHub Actions, a configured CI/CD automation

**Run:** Single execution of a workflow

**Log:** Text output from a CI/CD run

**Failure Line:** Specific log line indicating an error

**Root Cause:** Underlying reason for a failure (not just symptom)

**Fix Description:** Actionable steps to resolve a failure

**Annotation:** Human-labeled ground truth data

**Test Set:** Held-out data for final evaluation

**API Token:** Authentication credential for API access

**Embedding:** Vector representation of text for semantic search

**Vector Database:** Database optimized for similarity search over embeddings

**Chunk:** Section of a document (for retrieval)

**Temperature:** LLM sampling randomness parameter (0=deterministic, 1=creative)

**Prompt Engineering:** Crafting effective instructions for LLMs

**Zero-shot:** LLM performs task without examples

**Few-shot:** LLM given examples before performing task

**Chain-of-Thought:** Prompting LLM to explain its reasoning step-by-step

---

## Conclusion

This document provides complete architectural and implementation documentation for the Master's thesis project "Leveraging Large Language Models for Automated Diagnosis of CI/CD Pipeline Failures."

**Current Status:**
- System fully designed and implemented (~3,500 lines of code)
- Initial data collection completed (50 logs)
- Critical bug identified (ZIP decompression needed)
- Fix documented and ready to apply

**Next Immediate Actions:**
1. Fix ZIP decompression in `data_collection.py`
2. Re-collect clean data
3. Verify data quality
4. Begin diagnosis and annotation phases

**Timeline to Completion:** 12-16 weeks

**Expected Outcomes:**
- 85% diagnostic accuracy (vs 60% baseline)
- 60-70% time savings for developers
- First open benchmark for CI/CD log diagnosis
- Production-ready open-source tool

**Key Innovation:** Combining LLMs with grounding mechanisms and RAG to create trustworthy, actionable diagnostic tool with empirical validation of real-world impact.

---

**Document Version:** 1.0  
**Last Updated:** October 2025  
**Author:** Fahid Khan  
**Contact:** [Your Email]  
**Repository:** [GitHub URL when available]

---

**END OF DOCUMENTATION**