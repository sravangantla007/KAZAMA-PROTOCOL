"""Deterministic post-processing and calibration for Module 3 Synthesizer output."""
from __future__ import annotations
from typing import Dict

from app.contracts.common import Score
from app.contracts.trusted import TrustedSource
from app.contracts.synthesis import (
    SourceQuote, SynthFact, ConflictClaim, SynthConflict,
    SynthMissing, SynthesisPayload,
)
from app.modules.synthesizer.prompts import SynthesisLLMOutput


def calibrate_synthesis(
    raw_output: SynthesisLLMOutput,
    query: str,
    sources_used: list[str],
    trusted_sources: list[TrustedSource],
    model_info: dict,
    extra_coverage_notes: list[str] | None = None,
) -> SynthesisPayload:
    """
    Deterministic calibration:
    1. Reference checks (drop invalid source_ids, drop facts with 0 quotes, drop conflicts with < 2 sources)
    2. Confidence calibration against supporting baseline_trust + staleness
    3. Recompute corroboration_count
    4. Sequential renumbering of IDs
    """
    sources_map: Dict[str, TrustedSource] = {s.source_id: s for s in trusted_sources}
    valid_source_ids = set(sources_used)

    coverage_notes = list(raw_output.coverage_notes)
    if extra_coverage_notes:
        coverage_notes.extend(extra_coverage_notes)

    # 1. Calibrate Facts
    valid_facts: list[SynthFact] = []
    dropped_facts_count = 0

    for fact in raw_output.facts:
        # Keep only supporting quotes that reference valid source_ids
        valid_supporting = [
            SourceQuote(source_id=q.source_id, quote=q.quote)
            for q in fact.supporting
            if q.source_id in valid_source_ids and q.source_id in sources_map
        ]

        if not valid_supporting:
            dropped_facts_count += 1
            continue

        distinct_source_ids = list(dict.fromkeys(q.source_id for q in valid_supporting))
        corroboration_count = len(distinct_source_ids)

        # Baseline trust of supporting sources
        supporting_trusts = [sources_map[sid].baseline_trust_score for sid in distinct_source_ids]
        max_trust = max(supporting_trusts) if supporting_trusts else 0.50

        # Confidence calibration formula: min(llm_confidence, max_trust + 0.05)
        calibrated_conf = min(float(fact.confidence), max_trust + 0.05)

        # If all supporting sources are stale (age_days > 540)
        all_stale = all(
            sources_map[sid].age_days is not None and sources_map[sid].age_days > 540
            for sid in distinct_source_ids
        )
        if all_stale:
            calibrated_conf *= 0.8

        calibrated_conf = round(max(0.0, min(1.0, calibrated_conf)), 3)

        valid_facts.append(SynthFact(
            fact_id=f"F{len(valid_facts) + 1}",
            statement=fact.statement,
            category=fact.category,
            confidence=calibrated_conf,
            llm_confidence=fact.confidence,
            supporting=valid_supporting,
            corroboration_count=corroboration_count,
        ))

    if dropped_facts_count > 0:
        coverage_notes.append(f"{dropped_facts_count} unsupported facts discarded.")

    # 2. Calibrate Conflicts
    valid_conflicts: list[SynthConflict] = []
    for conf in raw_output.conflicts:
        valid_claims = [
            ConflictClaim(source_id=c.source_id, claim=c.claim, quote=c.quote)
            for c in conf.claims
            if c.source_id in valid_source_ids and c.source_id in sources_map
        ]
        distinct_sources = set(c.source_id for c in valid_claims)
        # Conflict requires at least 2 claims from at least 2 DIFFERENT sources
        if len(valid_claims) < 2 or len(distinct_sources) < 2:
            continue

        valid_conflicts.append(SynthConflict(
            conflict_id=f"C{len(valid_conflicts) + 1}",
            topic=conf.topic,
            severity=conf.severity,
            claims=valid_claims,
            note=conf.note,
        ))

    # 3. Missing Information
    valid_missing: list[SynthMissing] = []
    for i, m in enumerate(raw_output.missing_information, 1):
        valid_missing.append(SynthMissing(
            missing_id=f"M{i}",
            description=m.description,
            importance=m.importance,
            why_expected=m.why_expected,
            provenance="AI_INFERRED",
        ))

    return SynthesisPayload(
        query=query,
        topic_summary=raw_output.topic_summary,
        facts=valid_facts,
        conflicts=valid_conflicts,
        missing_information=valid_missing,
        coverage_notes=coverage_notes,
        sources_used=sources_used,
        model_info=model_info,
    )

