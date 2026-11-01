from __future__ import annotations
from datetime import date
from typing import Literal, Optional
from pydantic import BaseModel, ConfigDict

from app.contracts.common import (
    Score, SourceType, Provenance, Severity, Importance,
    TimeLevel, Readiness, TrustLabel,
)


class Citation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_id: str
    source_label: str
    source_type: SourceType
    quote: str
    quote_verified: bool
    source_date: Optional[date]
    source_baseline_trust: Score


class CitedClaim(Citation):
    """Citation extended with a claim statement (used in ConflictingClaimSet)."""
    claim: str


class TimeRelevance(BaseModel):
    model_config = ConfigDict(extra="forbid")
    level: TimeLevel
    message: str
    source_dates: list[Optional[date]]


class EvidenceItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    evidence_id: str
    statement: str
    provenance: Provenance
    citations: list[Citation]
    confidence: Score
    time_relevance: TimeRelevance
    relevance_to_decision: str


class ConflictingClaimSet(BaseModel):
    model_config = ConfigDict(extra="forbid")
    conflict_id: str
    topic: str
    severity: Severity
    claims: list[CitedClaim]
    why_it_matters_for_decision: str
    suggested_resolution: str
    confidence: Score
    time_relevance: TimeRelevance
    provenance: Provenance


class MissingItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    missing_id: str
    description: str
    importance: Importance
    why_it_matters_for_decision: str
    where_to_look: str
    confidence: Score
    provenance: Literal["AI_INFERRED"] = "AI_INFERRED"


class ChecklistItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    item_id: str
    priority: int
    urgency: Importance
    action: str
    reason: str
    related_ids: list[str]
    verify_with: str
    status: Literal["PENDING"] = "PENDING"


class TrustSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")
    overall_trust_score: Score
    overall_trust_label: TrustLabel
    components: dict


class DecisionPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision: str
    query: str
    decision_readiness: Readiness
    summary: str
    overall_trust_score: Score
    trust_summary: TrustSummary
    relevant_facts: list[EvidenceItem]
    conflicting_claims: list[ConflictingClaimSet]
    missing_information: list[MissingItem]
    actionable_verification_checklist: list[ChecklistItem]
    disclaimer: str
    warnings: list[str] = []
