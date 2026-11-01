from __future__ import annotations
import time
import uuid
from datetime import datetime, timezone, date
from typing import Optional

from app.config import settings
from app.contracts.common import SourceType
from app.contracts.raw import UploadedFile, IngestionResult
from app.contracts.trusted import TrustedSource
from app.contracts.synthesis import SynthesisPayload
from app.contracts.decision import DecisionPayload
from app.contracts.api import (
    AnalyzeRequest,
    AnalyzeResponse,
    DecideRequest,
    DecideResponse,
    SourceProjection,
    PipelineMeta,
    DebugBlock,
)
from app.modules.ingestion import ingest
from app.modules.weighter import weight
from app.modules.synthesizer import synthesize
from app.modules.decision import decide
from app.llm import get_llm_client
from app.llm.mock_client import MockLLMClient


def _project_source(src: TrustedSource) -> SourceProjection:
    excerpt = (src.text[:400] + "...") if len(src.text) > 400 else src.text
    return SourceProjection(
        source_id=src.source_id,
        source_type=src.source_type,
        url_or_filename=src.url_or_filename,
        title=src.title,
        published_date=src.published_date,
        age_days=src.age_days,
        domain_weight=src.domain_weight,
        ai_probability_score=src.ai_probability_score,
        baseline_trust_score=src.baseline_trust_score,
        text_excerpt=excerpt,
    )


async def run_pipeline(
    req: AnalyzeRequest,
    request_id: Optional[str] = None,
) -> AnalyzeResponse:
    """End-to-end execution of Modules 1 through 4."""
    req_id = request_id or f"req_{uuid.uuid4().hex[:12]}"
    timings: dict[str, float] = {}

    is_mock = req.options.mock_mode or settings.mock_mode
    scenario = req.options.mock_scenario or "scholarship_scenario"
    eval_today = req.options.today or datetime.now(timezone.utc).date()
    llm_client = MockLLMClient() if (is_mock or settings.mock_llm) else get_llm_client()

    # Convert uploaded files into UploadedFile contracts
    uploaded_files: list[UploadedFile] = []
    for f in req.files:
        if isinstance(f, UploadedFile):
            uploaded_files.append(f)
        elif isinstance(f, dict):
            uploaded_files.append(UploadedFile(**f))

    # 1. Module 1: Ingestion
    t0 = time.perf_counter()
    ingestion_result: IngestionResult = await ingest(
        query=req.query,
        urls=req.urls,
        files=uploaded_files,
        mock_mode=is_mock,
        mock_scenario=scenario,
    )
    timings["m1_ingestion_ms"] = round((time.perf_counter() - t0) * 1000, 2)

    # 2. Module 2: Weighter (sync call)
    t1 = time.perf_counter()
    trusted_sources: list[TrustedSource] = weight(
        ingestion=ingestion_result,
        today=eval_today,
    )
    timings["m2_weighter_ms"] = round((time.perf_counter() - t1) * 1000, 2)

    # 3. Module 3: Synthesizer
    t2 = time.perf_counter()
    synthesis_payload: SynthesisPayload = await synthesize(
        query=req.query,
        sources=trusted_sources,
        llm=llm_client,
        today=eval_today,
    )
    timings["m3_synthesizer_ms"] = round((time.perf_counter() - t2) * 1000, 2)

    # 4. Module 4: Decision Engine (if decision specified)
    decision_payload: Optional[DecisionPayload] = None
    if req.decision:
        t3 = time.perf_counter()
        decision_payload = await decide(
            query=req.query,
            decision=req.decision,
            synthesis=synthesis_payload,
            sources=trusted_sources,
            llm=llm_client,
            today=eval_today,
        )
        timings["m4_decision_ms"] = round((time.perf_counter() - t3) * 1000, 2)

    timings["total_ms"] = round(sum(timings.values()), 2)

    # Project sources for UI
    projections = [_project_source(s) for s in trusted_sources]

    # Pipeline metadata
    meta = PipelineMeta(
        timings_ms=timings,
        sources_ingested=len(ingestion_result.sources),
        sources_used=len(trusted_sources),
        ingestion_issues=ingestion_result.issues,
        llm={
            "provider": "mock" if (is_mock or settings.mock_llm) else settings.llm_provider,
            "model": "replay" if (is_mock or settings.mock_llm) else settings.llm_model,
            "mock_llm": is_mock or settings.mock_llm,
        },
    )

    debug_block: Optional[DebugBlock] = None
    if req.options.include_debug:
        debug_block = DebugBlock(
            trusted_sources=[s.model_dump(mode="json") for s in trusted_sources],
            raw_llm_outputs={},
            prompts_hash={},
        )

    return AnalyzeResponse(
        status="ok",
        request_id=req_id,
        generated_at=datetime.now(timezone.utc),
        query=req.query,
        decision=req.decision,
        mode={
            "mock_mode": is_mock,
            "scenario": scenario if is_mock else None,
            "today": eval_today.isoformat(),
        },
        sources=projections,
        synthesis=synthesis_payload,
        decision_payload=decision_payload,
        pipeline_meta=meta,
        debug=debug_block,
    )


async def run_decision_only(
    req: DecideRequest,
    request_id: Optional[str] = None,
) -> DecideResponse:
    """Run Module 4 decision engine on existing synthesis & sources."""
    req_id = request_id or f"req_{uuid.uuid4().hex[:12]}"
    is_mock = req.options.mock_mode or settings.mock_mode
    eval_today = req.options.today or datetime.now(timezone.utc).date()
    llm_client = MockLLMClient() if (is_mock or settings.mock_llm) else get_llm_client()

    # Reconstitute TrustedSource objects
    trusted_sources: list[TrustedSource] = []
    for s_dict in req.trusted_sources:
        trusted_sources.append(TrustedSource.model_validate(s_dict))

    t0 = time.perf_counter()
    decision_payload = await decide(
        query=req.query,
        decision=req.decision,
        synthesis=req.synthesis,
        sources=trusted_sources,
        llm=llm_client,
        today=eval_today,
    )
    duration_ms = round((time.perf_counter() - t0) * 1000, 2)

    return DecideResponse(
        status="ok",
        request_id=req_id,
        generated_at=datetime.now(timezone.utc),
        decision=req.decision,
        decision_payload=decision_payload,
        timings_ms={"m4_decision_ms": duration_ms},
    )
