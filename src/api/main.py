# main.py - FastAPI CI/CD Log Diagnostic Service
from dotenv import load_dotenv
import os

# Load environment variables

from fastapi import FastAPI, HTTPException, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from enum import Enum
import openai
import anthropic
import re
import json
from datetime import datetime
import hashlib
load_dotenv()


app = FastAPI(
    title="CI/CD Log Diagnostic API",
    description="Automated diagnosis of CI/CD pipeline failures using LLMs",
    version="1.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Enums and Models
class ErrorType(str, Enum):
    DEPENDENCY = "dependency_error"
    TEST_FAILURE = "test_failure"
    BUILD_CONFIG = "build_configuration"
    TIMEOUT = "timeout"
    PERMISSION = "permission_denied"
    SYNTAX = "syntax_error"
    NETWORK = "network_error"
    UNKNOWN = "unknown"

class LLMProvider(str, Enum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    LOCAL = "local"

class DiagnosisRequest(BaseModel):
    log_content: str = Field(..., description="Raw CI/CD log content")
    provider: LLMProvider = Field(default=LLMProvider.OPENAI)
    model: str = Field(default="gpt-4")
    temperature: float = Field(default=0.1, ge=0, le=2)
    use_filtering: bool = Field(default=True)
    max_context_lines: int = Field(default=500)

class LogLine(BaseModel):
    line_number: int
    content: str
    is_error: bool = False

class DiagnosisResult(BaseModel):
    log_id: str
    error_type: ErrorType
    failure_lines: List[int]
    root_cause: str
    suggested_fix: str
    confidence_score: float = Field(ge=0, le=1)
    grounded_evidence: List[LogLine]
    reasoning: str
    execution_time_ms: float
    model_used: str
    hallucination_detected: bool = False

# Log Filtering Strategies
class LogFilter:
    @staticmethod
    def filter_by_keywords(log_lines: List[str], keywords: List[str]) -> List[int]:
        """Filter log lines containing error keywords"""
        error_indices = []
        for i, line in enumerate(log_lines):
            if any(keyword.lower() in line.lower() for keyword in keywords):
                error_indices.append(i)
        return error_indices
    
    @staticmethod
    def get_context_window(log_lines: List[str], error_indices: List[int], 
                          window_size: int = 10) -> List[tuple]:
        """Get context around error lines"""
        contexts = []
        for idx in error_indices:
            start = max(0, idx - window_size)
            end = min(len(log_lines), idx + window_size + 1)
            contexts.append((start, end, log_lines[start:end]))
        return contexts
    
    @staticmethod
    def apply_smart_filtering(log_content: str, max_lines: int = 500) -> str:
        """Apply intelligent filtering to reduce log size"""
        lines = log_content.split('\n')
        
        # Error keywords to prioritize
        error_keywords = [
            'error', 'failed', 'failure', 'exception', 'fatal',
            'critical', 'panic', 'traceback', 'stack trace',
            'npm err!', 'gradle failed', 'maven error', 'pytest failed'
        ]
        
        # Get error line indices
        error_indices = LogFilter.filter_by_keywords(lines, error_keywords)
        
        if not error_indices:
            # No obvious errors, return last N lines
            return '\n'.join(lines[-max_lines:])
        
        # Get context around errors
        contexts = LogFilter.get_context_window(lines, error_indices, window_size=20)
        
        # Merge overlapping contexts
        filtered_lines = []
        covered_ranges = set()
        
        for start, end, context in contexts:
            for i in range(start, end):
                if i not in covered_ranges:
                    covered_ranges.add(i)
                    filtered_lines.append((i, lines[i]))
        
        # Sort by line number
        filtered_lines.sort(key=lambda x: x[0])
        
        # Format with line numbers
        result = []
        for line_num, content in filtered_lines[:max_lines]:
            result.append(f"[Line {line_num}] {content}")
        
        return '\n'.join(result)

# LLM Integration
class LLMDiagnoser:
    def __init__(self, provider: LLMProvider, model: str, api_key: Optional[str] = None):
        self.provider = provider
        self.model = model
        self.api_key = api_key
        
    def create_prompt(self, log_content: str) -> str:
        """Create diagnostic prompt for LLM"""
        return f"""You are an expert DevOps engineer analyzing CI/CD pipeline failures.

Analyze the following build log and provide a detailed diagnosis.

CRITICAL REQUIREMENTS:
1. You MUST cite exact log lines (with line numbers) as evidence
2. Every claim must reference specific lines from the log
3. Identify the root cause, not just symptoms
4. Provide actionable fix suggestions

LOG CONTENT:
{log_content}

Respond in JSON format:
{{
    "error_type": "dependency_error|test_failure|build_configuration|timeout|permission_denied|syntax_error|network_error|unknown",
    "failure_lines": [line numbers where errors occur],
    "root_cause": "Clear explanation of the underlying issue",
    "suggested_fix": "Specific, actionable steps to resolve the issue",
    "confidence_score": 0.0-1.0,
    "grounded_evidence": [
        {{"line_number": X, "content": "exact line content", "is_error": true}}
    ],
    "reasoning": "Step-by-step analysis leading to this diagnosis"
}}"""

    async def diagnose(self, log_content: str, temperature: float = 0.1) -> Dict[str, Any]:
        """Send log to LLM for diagnosis"""
        prompt = self.create_prompt(log_content)
        
        if self.provider == LLMProvider.OPENAI:
            return await self._diagnose_openai(prompt, temperature)
        elif self.provider == LLMProvider.ANTHROPIC:
            return await self._diagnose_anthropic(prompt, temperature)
        else:
            raise HTTPException(status_code=400, detail="Unsupported LLM provider")
    
    async def _diagnose_openai(self, prompt: str, temperature: float) -> Dict[str, Any]:
        """OpenAI API integration"""
        client = openai.AsyncOpenAI(api_key=self.api_key)
        
        response = await client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": "You are an expert DevOps engineer."},
                {"role": "user", "content": prompt}
            ],
            temperature=temperature,
            response_format={"type": "json_object"}
        )
        
        return json.loads(response.choices[0].message.content)
    
    async def _diagnose_anthropic(self, prompt: str, temperature: float) -> Dict[str, Any]:
        """Anthropic API integration"""
        client = anthropic.AsyncAnthropic(api_key=self.api_key)
        
        response = await client.messages.create(
            model=self.model,
            max_tokens=4096,
            temperature=temperature,
            messages=[
                {"role": "user", "content": prompt}
            ]
        )
        
        content = response.content[0].text
        # Extract JSON from response
        json_match = re.search(r'\{.*\}', content, re.DOTALL)
        if json_match:
            return json.loads(json_match.group())
        return json.loads(content)

# Grounding Verification
class GroundingVerifier:
    @staticmethod
    def verify_evidence(log_content: str, evidence: List[LogLine]) -> tuple[bool, float]:
        """Verify that cited evidence actually exists in the log"""
        log_lines = log_content.split('\n')
        verified_count = 0
        
        for ev in evidence:
            # Extract line number from formatted log
            line_match = re.search(r'\[Line (\d+)\]', log_lines[min(ev.line_number, len(log_lines)-1)])
            if line_match:
                actual_line_num = int(line_match.group(1))
                # Check if content matches
                if ev.content.strip() in log_lines[min(actual_line_num, len(log_lines)-1)]:
                    verified_count += 1
        
        hallucination_detected = verified_count < len(evidence) * 0.8  # 80% threshold
        grounding_score = verified_count / len(evidence) if evidence else 0.0
        
        return hallucination_detected, grounding_score

# API Endpoints
@app.post("/diagnose", response_model=DiagnosisResult)
async def diagnose_log(request: DiagnosisRequest):
    """Main endpoint for log diagnosis"""
    start_time = datetime.now()
    
    try:
        # Generate log ID
        log_id = hashlib.md5(request.log_content.encode()).hexdigest()[:12]
        
        # Apply filtering if requested
        if request.use_filtering:
            filtered_log = LogFilter.apply_smart_filtering(
                request.log_content, 
                request.max_context_lines
            )
        else:
            filtered_log = request.log_content
        
        # Initialize LLM diagnoser
        diagnoser = LLMDiagnoser(
            provider=request.provider,
            model=request.model
        )
        
        # Get diagnosis
        diagnosis = await diagnoser.diagnose(filtered_log, request.temperature)
        
        # Verify grounding
        hallucination_detected, grounding_score = GroundingVerifier.verify_evidence(
            filtered_log,
            [LogLine(**ev) for ev in diagnosis.get('grounded_evidence', [])]
        )
        
        # Calculate execution time
        execution_time = (datetime.now() - start_time).total_seconds() * 1000
        
        # Prepare result
        result = DiagnosisResult(
            log_id=log_id,
            error_type=ErrorType(diagnosis['error_type']),
            failure_lines=diagnosis['failure_lines'],
            root_cause=diagnosis['root_cause'],
            suggested_fix=diagnosis['suggested_fix'],
            confidence_score=diagnosis['confidence_score'] * grounding_score,
            grounded_evidence=[LogLine(**ev) for ev in diagnosis.get('grounded_evidence', [])],
            reasoning=diagnosis['reasoning'],
            execution_time_ms=execution_time,
            model_used=f"{request.provider.value}/{request.model}",
            hallucination_detected=hallucination_detected
        )
        
        return result
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Diagnosis failed: {str(e)}")

@app.post("/diagnose/batch")
async def diagnose_batch(logs: List[DiagnosisRequest]):
    """Batch processing endpoint"""
    results = []
    for log_request in logs:
        try:
            result = await diagnose_log(log_request)
            results.append(result)
        except Exception as e:
            results.append({"error": str(e)})
    return results

@app.post("/upload")
async def upload_log_file(file: UploadFile = File(...)):
    """Upload log file for diagnosis"""
    try:
        content = await file.read()
        log_content = content.decode('utf-8')
        
        request = DiagnosisRequest(
            log_content=log_content,
            provider=LLMProvider.OPENAI,
            model="gpt-4"
        )
        
        return await diagnose_log(request)
        
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"File upload failed: {str(e)}")

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}

@app.get("/stats")
async def get_statistics():
    """Get usage statistics"""
    # This would be connected to a database in production
    return {
        "total_diagnoses": 0,
        "average_execution_time_ms": 0,
        "hallucination_rate": 0,
        "supported_providers": [p.value for p in LLMProvider],
        "supported_error_types": [e.value for e in ErrorType]
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)