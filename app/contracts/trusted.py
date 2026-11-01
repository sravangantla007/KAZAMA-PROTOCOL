from __future__ import annotations
from typing import Optional
from pydantic import BaseModel, ConfigDict

from app.contracts.common import Score
from app.contracts.raw import RawSource


class WeightBreakdown(BaseModel):
    model_config = ConfigDict(extra="forbid")
    base: float
    domain_rule_matched: str
    ai_penalty_applied: float
    undated_penalty_applied: float
    ai_detection_reliable: bool


class TrustedSource(RawSource):
    model_config = ConfigDict(extra="forbid")
    ai_probability_score: Score
    domain_weight: Score
    baseline_trust_score: Score
    query_relevance: Score = 0.0
    importance_score: Score = 0.0
    age_days: Optional[int] = None
    weight_breakdown: WeightBreakdown
