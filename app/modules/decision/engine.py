"""Module 4 Decision Engine implementation and post-processing."""
from __future__ import annotations
from datetime import date
from urllib.parse import urlparse

from app.contracts.common import (
    Provenance, Score, TimeLevel, Readiness, TrustLabel,
)
from app.contracts.trusted import TrustedSource
from app.contracts.synthesis import SynthesisPayload
from app.contracts.decision import (
    Citation, CitedClaim, TimeRelevance, EvidenceItem, ConflictingClaimSet,
    MissingItem, ChecklistItem, TrustSummary, DecisionPayload,
)
from app.llm.client import LLMClient
from app.modules.decision.prompts import (
    SYSTEM_PROMPT, DecisionLLMOutput, build_decision_prompt,
)
from app.modules.decision.time_relevance import (
    compute_deterministic_time_level, max_severity, fallback_time_message,
)
from app.modules.decision.verify_quotes import verify_quote
from app.modules.decision.scoring import compute_trust_summary

FIXED_DISCLAIMER = (
    "This analysis highlights potential information gaps, conflicts, and outdated details based only on the "
    "sources reviewed. AI-generated items are signals, not confirmed facts. Verify important details with the "
    "official source before making a decision."
)


async def decide(
    query: str,
    decision: str,
    synthesis: SynthesisPayload,
    sources: list[TrustedSource],
    llm: LLMClient,
    today: date,
) -> DecisionPayload:
    """
    Decide entry point for Module 4.
    Runs decision-specific LLM filtering followed by the 9 deterministic post-processing steps.
    """
    user_prompt, cited_ids = build_decision_prompt(
        query=query,
        decision=decision,
        synthesis=synthesis,
        sources=sources,
        today=today,
    )

    raw_output: DecisionLLMOutput = await llm.generate_json(
        system=SYSTEM_PROMPT,
        user=user_prompt,
        model_cls=DecisionLLMOutput,
        purpose="decision",
    )

    return process_decision_output(
        raw_output=raw_output,
        query=query,
        decision=decision,
        sources=sources,
        today=today,
    )


def process_decision_output(
    raw_output: DecisionLLMOutput,
    query: str,
    decision: str,
    sources: list[TrustedSource],
    today: date,
) -> DecisionPayload:
    """
    Executes the 9 deterministic post-processing steps in exact order.
    """
    warnings: list[str] = []
    sources_by_id = {s.source_id: s for s in sources}

    # -------------------------------------------------------------
    # Step 1 & 2 & 3 & 4 & 5: Process relevant_facts
    # -------------------------------------------------------------
    processed_facts: list[EvidenceItem] = []
    for item in raw_output.relevant_facts:
        if not item.statement or not item.statement.strip():
            continue  # Delete items that have no statement text

        resolved_citations: list[Citation] = []
        verified_trust_scores: list[float] = []
        source_dates: list[date | None] = []
        det_levels: list[TimeLevel] = []

        for cit in item.citations:
            src = sources_by_id.get(cit.source_id)
            if not src:
                warnings.append(f"{item.evidence_id} dropped citation with unknown source_id '{cit.source_id}'")
                continue

            # Quote verification
            is_verified = verify_quote(cit.quote, src.text)

            origin = urlparse(src.url_or_filename).hostname or src.url_or_filename
            source_label = src.title or origin or src.source_id

            resolved_cit = Citation(
                source_id=src.source_id,
                source_label=source_label,
                source_type=src.source_type,
                quote=cit.quote,
                quote_verified=is_verified,
                source_date=src.published_date,
                source_baseline_trust=src.baseline_trust_score,
            )
            resolved_citations.append(resolved_cit)

            if is_verified:
                verified_trust_scores.append(src.baseline_trust_score)

            source_dates.append(src.published_date)
            det_levels.append(compute_deterministic_time_level(src))

        # Provenance enforcement (Step 3)
        provenance: Provenance = item.provenance
        confidence = float(item.confidence)

        if provenance == "SOURCED":
            has_verified = any(c.quote_verified for c in resolved_citations)
            if not has_verified:
                provenance = "AI_INFERRED"
                confidence = round(confidence * 0.5, 3)
                warnings.append(f"{item.evidence_id} downgraded: citation could not be verified")
            else:
                # Confidence cap (Step 4)
                if verified_trust_scores:
                    max_verified_trust = max(verified_trust_scores)
                    confidence = round(min(confidence, max_verified_trust + 0.05), 3)

        # Time relevance merge (Step 5)
        # Determine base deterministic level from cited sources
        if det_levels:
            # Most severe among cited sources
            cur_det_level = det_levels[0]
            for dl in det_levels[1:]:
                cur_det_level = max_severity(cur_det_level, dl)
        else:
            cur_det_level = "UNDATED" if provenance == "AI_INFERRED" else "UNDATED"

        final_time_level = max_severity(cur_det_level, item.time_relevance_level)

        time_message = item.time_relevance_message.strip() if item.time_relevance_message else ""
        if not time_message:
            time_message = fallback_time_message(final_time_level, source_dates)

        time_relevance = TimeRelevance(
            level=final_time_level,
            message=time_message,
            source_dates=source_dates,
        )

        processed_facts.append(
            EvidenceItem(
                evidence_id=item.evidence_id,
                statement=item.statement,
                provenance=provenance,
                citations=resolved_citations,
                confidence=round(max(0.0, min(1.0, confidence)), 3),
                time_relevance=time_relevance,
                relevance_to_decision=item.relevance_to_decision,
            )
        )

    # -------------------------------------------------------------
    # Step 1 & 2 & 3 & 4 & 5: Process conflicting_claims
    # -------------------------------------------------------------
    processed_conflicts: list[ConflictingClaimSet] = []
    for conf in raw_output.conflicting_claims:
        resolved_claims: list[CitedClaim] = []
        verified_trust_scores: list[float] = []
        source_dates: list[date | None] = []
        det_levels: list[TimeLevel] = []

        for cl in conf.claims:
            src = sources_by_id.get(cl.source_id)
            if not src:
                warnings.append(f"{conf.conflict_id} dropped claim citation with unknown source_id '{cl.source_id}'")
                continue

            is_verified = verify_quote(cl.quote, src.text)
            origin = urlparse(src.url_or_filename).hostname or src.url_or_filename
            source_label = src.title or origin or src.source_id

            resolved_claim = CitedClaim(
                source_id=src.source_id,
                source_label=source_label,
                source_type=src.source_type,
                quote=cl.quote,
                quote_verified=is_verified,
                source_date=src.published_date,
                source_baseline_trust=src.baseline_trust_score,
                claim=cl.claim,
            )
            resolved_claims.append(resolved_claim)

            if is_verified:
                verified_trust_scores.append(src.baseline_trust_score)

            source_dates.append(src.published_date)
            det_levels.append(compute_deterministic_time_level(src))

        provenance = conf.provenance
        confidence = float(conf.confidence)

        if provenance == "SOURCED":
            has_verified = any(c.quote_verified for c in resolved_claims)
            if not has_verified:
                provenance = "AI_INFERRED"
                confidence = round(confidence * 0.5, 3)
                warnings.append(f"{conf.conflict_id} downgraded: claim citation could not be verified")
            else:
                if verified_trust_scores:
                    max_verified_trust = max(verified_trust_scores)
                    confidence = round(min(confidence, max_verified_trust + 0.05), 3)

        if det_levels:
            cur_det_level = det_levels[0]
            for dl in det_levels[1:]:
                cur_det_level = max_severity(cur_det_level, dl)
        else:
            cur_det_level = "UNDATED"

        final_time_level = max_severity(cur_det_level, conf.time_relevance_level)
        time_message = conf.time_relevance_message.strip() if conf.time_relevance_message else ""
        if not time_message:
            time_message = fallback_time_message(final_time_level, source_dates)

        time_relevance = TimeRelevance(
            level=final_time_level,
            message=time_message,
            source_dates=source_dates,
        )

        processed_conflicts.append(
            ConflictingClaimSet(
                conflict_id=conf.conflict_id,
                topic=conf.topic,
                severity=conf.severity,
                claims=resolved_claims,
                why_it_matters_for_decision=conf.why_it_matters_for_decision,
                suggested_resolution=conf.suggested_resolution,
                confidence=round(max(0.0, min(1.0, confidence)), 3),
                time_relevance=time_relevance,
                provenance=provenance,
            )
        )

    # -------------------------------------------------------------
    # Missing information processing
    # -------------------------------------------------------------
    processed_missing: list[MissingItem] = []
    for m in raw_output.missing_information:
        processed_missing.append(
            MissingItem(
                missing_id=m.missing_id,
                description=m.description,
                importance=m.importance,
                why_it_matters_for_decision=m.why_it_matters_for_decision,
                where_to_look=m.where_to_look,
                confidence=round(max(0.0, min(1.0, float(m.confidence))), 3),
                provenance="AI_INFERRED",
            )
        )

    # -------------------------------------------------------------
    # Step 6: Checklist integrity
    # -------------------------------------------------------------
    existing_evidence_ids = {f.evidence_id for f in processed_facts}
    existing_conflict_ids = {c.conflict_id for c in processed_conflicts}
    existing_missing_ids = {m.missing_id for m in processed_missing}
    all_valid_ids = existing_evidence_ids | existing_conflict_ids | existing_missing_ids

    # Track which high conflicts and critical missing items are covered
    high_conflict_ids = {c.conflict_id for c in processed_conflicts if c.severity == "HIGH"}
    critical_missing_ids = {m.missing_id for m in processed_missing if m.importance == "CRITICAL"}
    covered_ids: set[str] = set()

    processed_checklist: list[ChecklistItem] = []
    for item in raw_output.actionable_verification_checklist:
        # Filter dangling related_ids
        valid_rel_ids = [rid for rid in item.related_ids if rid in all_valid_ids]
        covered_ids.update(valid_rel_ids)

        processed_checklist.append(
            ChecklistItem(
                item_id=item.item_id,
                priority=item.priority,
                urgency=item.urgency,
                action=item.action,
                reason=item.reason,
                related_ids=valid_rel_ids,
                verify_with=item.verify_with,
                status="PENDING",
            )
        )

    # Auto-append if any HIGH conflict is missing coverage
    for hc_id in sorted(high_conflict_ids):
        if hc_id not in covered_ids:
            conf_obj = next(c for c in processed_conflicts if c.conflict_id == hc_id)
            auto_item = ChecklistItem(
                item_id=f"V{len(processed_checklist) + 1}",
                priority=len(processed_checklist) + 1,
                urgency="CRITICAL",
                action=f"Verify conflict: {conf_obj.topic}",
                reason=conf_obj.why_it_matters_for_decision,
                related_ids=[hc_id],
                verify_with=conf_obj.suggested_resolution or "the official source",
                status="PENDING",
            )
            processed_checklist.append(auto_item)
            covered_ids.add(hc_id)
            warnings.append(f"Auto-appended checklist item for uncovered HIGH conflict '{hc_id}'")

    # Auto-append if any CRITICAL missing item is missing coverage
    for cm_id in sorted(critical_missing_ids):
        if cm_id not in covered_ids:
            miss_obj = next(m for m in processed_missing if m.missing_id == cm_id)
            auto_item = ChecklistItem(
                item_id=f"V{len(processed_checklist) + 1}",
                priority=len(processed_checklist) + 1,
                urgency="CRITICAL",
                action=f"Verify: {miss_obj.description}",
                reason=miss_obj.why_it_matters_for_decision,
                related_ids=[cm_id],
                verify_with=miss_obj.where_to_look or "the official source",
                status="PENDING",
            )
            processed_checklist.append(auto_item)
            covered_ids.add(cm_id)
            warnings.append(f"Auto-appended checklist item for uncovered CRITICAL missing item '{cm_id}'")

    # Re-normalize checklist priorities ascending from 1
    processed_checklist.sort(key=lambda x: (x.priority, x.item_id))
    for idx, item in enumerate(processed_checklist, start=1):
        item.priority = idx

    # -------------------------------------------------------------
    # Step 7: Compute trust summary
    # -------------------------------------------------------------
    trust_summary, overall_trust_score, overall_trust_label, zero_facts = compute_trust_summary(
        relevant_facts=processed_facts,
        conflicts=processed_conflicts,
        missing_items=processed_missing,
    )

    # -------------------------------------------------------------
    # Step 8: Readiness guardrail
    # -------------------------------------------------------------
    decision_readiness: Readiness = raw_output.decision_readiness

    if zero_facts:
        decision_readiness = "INSUFFICIENT_INFORMATION"
    else:
        has_high_conflict = len(high_conflict_ids) > 0
        has_crit_missing = len(critical_missing_ids) > 0
        if (has_high_conflict or has_crit_missing or overall_trust_score < 0.30) and decision_readiness == "READY":
            decision_readiness = "VERIFY_FIRST"

    # -------------------------------------------------------------
    # Step 9: Inject fixed disclaimer and collected warnings
    # -------------------------------------------------------------
    return DecisionPayload(
        decision=decision,
        query=query,
        decision_readiness=decision_readiness,
        summary=raw_output.summary,
        overall_trust_score=overall_trust_score,
        trust_summary=trust_summary,
        relevant_facts=processed_facts,
        conflicting_claims=processed_conflicts,
        missing_information=processed_missing,
        actionable_verification_checklist=processed_checklist,
        disclaimer=FIXED_DISCLAIMER,
        warnings=warnings,
    )

