# main.py - FastAPI CI/CD Log Diagnostic Service
#
# This file is now a thin entrypoint.  Domain logic lives in:
#   models.py       Pydantic models & enums
#   filtering.py    LogFilter
#   llm_service.py  LLMDiagnoser
#   grounding.py    GroundingVerifier

import hashlib
import logging
import os
from datetime import datetime
from typing import List

from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

from src.api.filtering import LogFilter
from src.api.grounding import GroundingVerifier
from src.api.llm_service import LLMDiagnoser
from src.api.models import (
    DiagnosisRequest,
    DiagnosisResult,
    ErrorType,
    LLMProvider,
    LogLine,
)
from src.config import settings

logger = logging.getLogger(__name__)

app = FastAPI(
    title="CI/CD Log Diagnostic API",
    description="Automated diagnosis of CI/CD pipeline failures using LLMs",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.post("/diagnose", response_model=DiagnosisResult)
async def diagnose_log(request: DiagnosisRequest):
    """Main endpoint for log diagnosis."""
    start_time = datetime.now()

    try:
        log_id = hashlib.md5(request.log_content.encode()).hexdigest()[:12]

        # Apply filtering
        if request.use_filtering:
            filtered_log = LogFilter.apply_smart_filtering(
                request.log_content,
                max_lines=request.max_context_lines,
                window_size=settings.api.filtering_window_size,
            )
        else:
            filtered_log = request.log_content

        # Resolve API key from env
        if request.provider == LLMProvider.OPENAI:
            api_key = os.getenv("OPENAI_API_KEY")
        elif request.provider == LLMProvider.ANTHROPIC:
            api_key = os.getenv("ANTHROPIC_API_KEY")
        else:
            api_key = None

        diagnoser = LLMDiagnoser(
            provider=request.provider,
            model=request.model,
            api_key=api_key,
            max_tokens=settings.api.max_tokens,
        )

        diagnosis = await diagnoser.diagnose(filtered_log, request.temperature)

        evidence = [LogLine(**ev) for ev in diagnosis.get('grounded_evidence', [])]
        hallucination_detected, grounding_score = GroundingVerifier.verify_evidence(
            filtered_log,
            evidence,
            threshold=settings.api.grounding_threshold,
        )

        execution_time = (datetime.now() - start_time).total_seconds() * 1000

        return DiagnosisResult(
            log_id=log_id,
            error_type=ErrorType(diagnosis['error_type']),
            failure_lines=diagnosis['failure_lines'],
            root_cause=diagnosis['root_cause'],
            suggested_fix=diagnosis['suggested_fix'],
            confidence_score=diagnosis['confidence_score'] * grounding_score,
            grounded_evidence=evidence,
            reasoning=diagnosis['reasoning'],
            execution_time_ms=execution_time,
            model_used=f"{request.provider.value}/{request.model}",
            hallucination_detected=hallucination_detected,
        )

    except Exception as e:
        logger.exception("Diagnosis failed")
        raise HTTPException(status_code=500, detail=f"Diagnosis failed: {str(e)}")


@app.post("/diagnose/batch")
async def diagnose_batch(logs: List[DiagnosisRequest]):
    """Batch processing endpoint."""
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
    """Upload a log file for diagnosis."""
    try:
        content = await file.read()
        log_content = content.decode('utf-8')

        request = DiagnosisRequest(
            log_content=log_content,
            provider=LLMProvider(settings.api.default_provider),
            model=settings.api.default_model,
        )
        return await diagnose_log(request)

    except Exception as e:
        raise HTTPException(status_code=400, detail=f"File upload failed: {str(e)}")


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}


@app.get("/stats")
async def get_statistics():
    """Usage statistics (stub)."""
    return {
        "total_diagnoses": 0,
        "average_execution_time_ms": 0,
        "hallucination_rate": 0,
        "supported_providers": [p.value for p in LLMProvider],
        "supported_error_types": [e.value for e in ErrorType],
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host=settings.api.host,
        port=settings.api.port,
    )