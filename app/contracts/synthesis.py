from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, ConfigDict

from app.contracts.common import Score, Severity, Importance


class SourceQuote(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_id: str
    quote: str


class SynthFact(BaseModel):
    model_config = ConfigDict(extra="forbid")
    fact_id: str
    statement: str
    category: str
    confidence: Score
    llm_confidence: Score
    supporting: list[SourceQuote]
    corroboration_count: int


class ConflictClaim(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_id: str
    claim: str
    quote: str


class SynthConflict(BaseModel):
    model_config = ConfigDict(extra="forbid")
    conflict_id: str
    topic: str
    severity: Severity
    claims: list[ConflictClaim]
    note: str


class SynthMissing(BaseModel):
    model_config = ConfigDict(extra="forbid")
    missing_id: str
    description: str
    importance: Importance
    why_expected: str
    provenance: Literal["AI_INFERRED"] = "AI_INFERRED"


class SynthesisPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str
    topic_summary: str
    facts: list[SynthFact]
    conflicts: list[SynthConflict]
    missing_information: list[SynthMissing]
    coverage_notes: list[str] = []
    sources_used: list[str]
    model_info: dict
