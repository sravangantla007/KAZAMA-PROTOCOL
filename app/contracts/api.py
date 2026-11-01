from __future__ import annotations
from datetime import date, datetime
from typing import Any, Optional
from pydantic import BaseModel, ConfigDict, field_validator

from app.contracts.common import SourceType, Score
from app.contracts.decision import DecisionPayload
from app.contracts.synthesis import SynthesisPayload
from app.contracts.raw import IngestionIssue


class AnalyzeOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mock_mode: bool = False
    mock_scenario: Optional[str] = None
    use_search: bool = True
    include_debug: bool = False
    today: Optional[date] = None


class AnalyzeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str
    decision: Optional[str] = None
    files: list[dict] = []
    urls: list[str] = []
    options: AnalyzeOptions = AnalyzeOptions()

    @field_validator("query")
    @classmethod
    def validate_query(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 3 or len(v) > 500:
            raise ValueError("query must be 3–500 characters")
        return v

    @field_validator("decision")
    @classmethod
    def validate_decision(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            v = v.strip()
            if v and (len(v) < 3 or len(v) > 300):
                raise ValueError("decision must be 3–300 characters")
            if not v:
                return None
        return v

    @field_validator("urls")
    @classmethod
    def validate_urls(cls, v: list[str]) -> list[str]:
        if len(v) > 12:
            raise ValueError("maximum 12 URLs allowed")
        return v


class SourceProjection(BaseModel):
    """UI-safe projection of TrustedSource."""
    model_config = ConfigDict(extra="forbid")
    source_id: str
    source_type: SourceType
    url_or_filename: str
    title: Optional[str] = None
    published_date: Optional[date] = None
    age_days: Optional[int] = None
    domain_weight: Score
    ai_probability_score: Score
    baseline_trust_score: Score
    text_excerpt: str  # first 400 chars of cleaned text


class PipelineMeta(BaseModel):
    model_config = ConfigDict(extra="forbid")
    timings_ms: dict
    sources_ingested: int
    sources_used: int
    ingestion_issues: list[IngestionIssue]
    llm: dict


class DebugBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")
    trusted_sources: list[Any]
    raw_llm_outputs: dict
    prompts_hash: dict


class AnalyzeResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: str
    request_id: str
    generated_at: datetime
    query: str
    decision: Optional[str] = None
    mode: dict
    sources: list[SourceProjection]
    synthesis: SynthesisPayload
    decision_payload: Optional[DecisionPayload] = None
    pipeline_meta: PipelineMeta
    debug: Optional[DebugBlock] = None


class DecideRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision: str
    query: str
    synthesis: SynthesisPayload
    trusted_sources: list[dict]
    options: AnalyzeOptions = AnalyzeOptions()

    @field_validator("decision")
    @classmethod
    def validate_decision(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 3 or len(v) > 300:
            raise ValueError("decision must be 3–300 characters")
        return v


class DecideResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: str
    request_id: str
    generated_at: datetime
    decision: str
    decision_payload: DecisionPayload
    timings_ms: dict


class ErrorDetail(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str
    message: str
    target: Optional[str] = None


class ErrorResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: str = "error"
    request_id: str
    error: ErrorDetail
