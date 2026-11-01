from __future__ import annotations
import uuid
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.exceptions import RequestValidationError

from app.config import settings
from app.contracts.api import (
    AnalyzeRequest,
    AnalyzeResponse,
    DecideRequest,
    DecideResponse,
    ErrorResponse,
    ErrorDetail,
)
from app.pipeline import run_pipeline, run_decision_only

app = FastAPI(
    title="Kazama Protocol - Digital Dark Spot Detection",
    version="1.0.0",
    description="Deterministic 4-stage information gap detection backend with 3D neural visualization.",
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    req_id = getattr(request.state, "request_id", f"req_{uuid.uuid4().hex[:12]}")
    errors = exc.errors()
    first_msg = errors[0]["msg"] if errors else "Invalid request data"
    loc = ".".join(str(l) for l in errors[0].get("loc", [])) if errors else None
    print(f"\n[ERROR 422] Validation failed: {first_msg} (at {loc})", file=sys.stderr, flush=True)
    return JSONResponse(
        status_code=422,
        content=ErrorResponse(
            status="error",
            request_id=req_id,
            error=ErrorDetail(
                code="VALIDATION_ERROR",
                message=f"{first_msg} (at {loc})" if loc else first_msg,
                target=loc,
            ),
        ).model_dump(mode="json"),
    )


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    req_id = getattr(request.state, "request_id", f"req_{uuid.uuid4().hex[:12]}")
    print(f"\n[ERROR 500] Unhandled Exception: {exc}", file=sys.stderr, flush=True)
    traceback.print_exc()
    return JSONResponse(
        status_code=500,
        content=ErrorResponse(
            status="error",
            request_id=req_id,
            error=ErrorDetail(
                code="INTERNAL_SERVER_ERROR",
                message=f"{type(exc).__name__}: {str(exc)}",
            ),
        ).model_dump(mode="json"),
    )


@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "name": "Kazama Protocol",
        "version": "1.0.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "mock_mode": settings.mock_mode,
        "mock_llm": settings.mock_llm,
        "search_provider": settings.search_provider,
        "llm_model": settings.llm_model or "gemini-3.5-flash",
        "llm_provider": settings.llm_provider or "gemini",
    }


@app.get("/api/mock-scenarios")
async def mock_scenarios():
    return {
        "scenarios": [
            {
                "id": "scholarship_scenario",
                "title": "National Merit Engineering Scholarship (NMES) 2025",
                "default_query": "What are the eligibility criteria and deadlines for NMES?",
                "default_decision": "Apply for scholarship as final year student",
            }
        ]
    }


@app.post("/api/analyze")
async def analyze_endpoint(request: Request, payload: AnalyzeRequest):
    req_id = getattr(request.state, "request_id", f"req_{uuid.uuid4().hex[:12]}")
    print(f"\n" + "=" * 60, flush=True)
    print(f"[API] >>> POST /api/analyze [{req_id}]", flush=True)
    print(f"      Query    : {payload.query}", flush=True)
    print(f"      Decision : {payload.decision}", flush=True)
    print(f"      Mock Mode: {payload.options.mock_mode}", flush=True)
    print(f"      Urls     : {payload.urls}", flush=True)
    print(f"      Files    : {len(payload.files)} attached", flush=True)
    print("=" * 60, flush=True)

    try:
        response = await run_pipeline(payload, request_id=req_id)
        print(f"[API] <<< /api/analyze SUCCESS [{req_id}] - {len(response.sources)} sources, {len(response.synthesis.facts)} facts", flush=True)
        return response.model_dump(mode="json")
    except Exception as e:
        print(f"\n[ERROR] Pipeline execution failed: {type(e).__name__}: {e}", file=sys.stderr, flush=True)
        traceback.print_exc()
        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "request_id": req_id,
                "error": {
                    "code": f"PIPELINE_{type(e).__name__.upper()}",
                    "message": f"{type(e).__name__}: {str(e)}",
                    "traceback": traceback.format_exc(),
                }
            }
        )


@app.post("/api/decide")
async def decide_endpoint(request: Request, payload: DecideRequest):
    req_id = getattr(request.state, "request_id", f"req_{uuid.uuid4().hex[:12]}")
    print(f"\n[API] >>> POST /api/decide [{req_id}] for decision: '{payload.decision}'", flush=True)
    try:
        response = await run_decision_only(payload, request_id=req_id)
        readiness = response.decision_payload.decision_readiness
        print(f"[API] <<< /api/decide SUCCESS [{req_id}] - Readiness: {readiness}", flush=True)
        return response.model_dump(mode="json")
    except Exception as e:
        print(f"\n[ERROR] Decision execution failed: {type(e).__name__}: {e}", file=sys.stderr, flush=True)
        traceback.print_exc()
        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "request_id": req_id,
                "error": {
                    "code": f"DECISION_{type(e).__name__.upper()}",
                    "message": f"{type(e).__name__}: {str(e)}",
                    "traceback": traceback.format_exc(),
                }
            }
        )


# Static frontend mounting
static_dir = Path(__file__).parent / "static"
static_dir.mkdir(parents=True, exist_ok=True)


@app.get("/")
async def root():
    index_file = static_dir / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return {"message": "Kazama Protocol API is active. Static files not yet deployed."}


app.mount("/", StaticFiles(directory=str(static_dir)), name="static")
