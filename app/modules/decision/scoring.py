"""Deterministic trust score calculation for Module 4 Decision Engine."""
from __future__ import annotations
from app.contracts.common import Score, TrustLabel, Readiness
from app.contracts.decision import (
    EvidenceItem, ConflictingClaimSet, MissingItem, TrustSummary,
)


def compute_trust_summary(
    relevant_facts: list[EvidenceItem],
    conflicts: list[ConflictingClaimSet],
    missing_items: list[MissingItem],
) -> tuple[TrustSummary, Score, TrustLabel, bool]:
    """
    Computes trust summary and score according to the formula:
    - evidence_strength   = mean(confidence of relevant_facts) (0.0 if none)
    - conflict_penalty    = min(0.30, 0.10*count(HIGH) + 0.05*count(MEDIUM) + 0.02*count(LOW))
    - missing_penalty     = min(0.25, 0.08*count(CRITICAL) + 0.04*count(IMPORTANT) + 0.01*count(MINOR))
    - staleness_penalty   = min(0.20, 0.05*count(evidence/conflict with level STALE) + 0.03*count(level UNDATED))
    - overall_trust_score = clamp(evidence_strength - conflict_penalty - missing_penalty - staleness_penalty, 0.0, 1.0)
    - label: >= 0.75 HIGH ; >= 0.50 MEDIUM ; else LOW

    If there are zero relevant facts: score 0.0, label LOW, zero_facts=True.
    """
    if not relevant_facts:
        summary = TrustSummary(
            overall_trust_score=0.0,
            overall_trust_label="LOW",
            components={
                "evidence_strength": 0.0,
                "conflict_penalty": 0.0,
                "missing_penalty": 0.0,
                "staleness_penalty": 0.0,
            },
        )
        return summary, 0.0, "LOW", True

    evidence_strength = sum(f.confidence for f in relevant_facts) / len(relevant_facts)

    # Conflict penalty
    high_conflicts = sum(1 for c in conflicts if c.severity == "HIGH")
    med_conflicts = sum(1 for c in conflicts if c.severity == "MEDIUM")
    low_conflicts = sum(1 for c in conflicts if c.severity == "LOW")
    raw_conflict_pen = 0.10 * high_conflicts + 0.05 * med_conflicts + 0.02 * low_conflicts
    conflict_penalty = min(0.30, raw_conflict_pen)

    # Missing penalty
    crit_missing = sum(1 for m in missing_items if m.importance == "CRITICAL")
    imp_missing = sum(1 for m in missing_items if m.importance == "IMPORTANT")
    min_missing = sum(1 for m in missing_items if m.importance == "MINOR")
    raw_missing_pen = 0.08 * crit_missing + 0.04 * imp_missing + 0.01 * min_missing
    missing_penalty = min(0.25, raw_missing_pen)

    # Staleness penalty: count over relevant_facts AND conflicts
    items_to_check = relevant_facts + conflicts
    stale_count = sum(1 for item in items_to_check if item.time_relevance.level == "STALE")
    undated_count = sum(1 for item in items_to_check if item.time_relevance.level == "UNDATED")
    raw_staleness_pen = 0.05 * stale_count + 0.03 * undated_count
    staleness_penalty = min(0.20, raw_staleness_pen)

    raw_score = evidence_strength - conflict_penalty - missing_penalty - staleness_penalty
    overall_trust_score = round(max(0.0, min(1.0, raw_score)), 3)

    if overall_trust_score >= 0.75:
        overall_trust_label: TrustLabel = "HIGH"
    elif overall_trust_score >= 0.50:
        overall_trust_label: TrustLabel = "MEDIUM"
    else:
        overall_trust_label: TrustLabel = "LOW"

    components = {
        "evidence_strength": round(evidence_strength, 3),
        "conflict_penalty": round(conflict_penalty, 3),
        "missing_penalty": round(missing_penalty, 3),
        "staleness_penalty": round(staleness_penalty, 3),
    }

    summary = TrustSummary(
        overall_trust_score=overall_trust_score,
        overall_trust_label=overall_trust_label,
        components=components,
    )

    return summary, overall_trust_score, overall_trust_label, False

