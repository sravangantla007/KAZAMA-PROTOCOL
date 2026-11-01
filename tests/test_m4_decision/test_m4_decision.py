"""Module 4 (Decision Engine) acceptance tests — consume ONLY tests/fixtures/m3_output.json and m2_output.json."""
from __future__ import annotations
from datetime import date
import json
from pathlib import Path
import pytest

from app.contracts.common import TimeLevel
from app.contracts.trusted import TrustedSource
from app.contracts.synthesis import SynthesisPayload
from app.contracts.decision import DecisionPayload
from app.llm.mock_client import MockLLMClient
from app.modules.decision import decide, FIXED_DISCLAIMER
from app.modules.decision.prompts import (
    DecisionLLMOutput, EvidenceItemLLM, CitationLLM, ConflictingClaimSetLLM,
    CitedClaimLLM, MissingItemLLM, ChecklistItemLLM,
)
from app.modules.decision.engine import process_decision_output
from app.modules.decision.scoring import compute_trust_summary
from app.modules.decision.time_relevance import max_severity

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"
M2_PATH = FIXTURES_DIR / "m2_output.json"
M3_PATH = FIXTURES_DIR / "m3_output.json"
M4_PATH = FIXTURES_DIR / "m4_output.json"
TODAY = date(2026, 10, 31)
QUERY = "What should I verify before applying for the NMES scholarship?"
DECISION = "Apply to the NMES scholarship this cycle"


@pytest.fixture
def m2_sources() -> list[TrustedSource]:
    assert M2_PATH.exists(), "m2_output.json golden fixture must exist"
    data = json.loads(M2_PATH.read_text(encoding="utf-8"))
    return [TrustedSource.model_validate(s) for s in data]


@pytest.fixture
def m3_synthesis() -> SynthesisPayload:
    assert M3_PATH.exists(), "m3_output.json golden fixture must exist"
    data = json.loads(M3_PATH.read_text(encoding="utf-8"))
    return SynthesisPayload.model_validate(data)


@pytest.mark.asyncio
async def test_mock_decision_validates_as_decision_payload(
    m3_synthesis: SynthesisPayload,
    m2_sources: list[TrustedSource],
):
    """
    For 'Apply to the NMES scholarship this cycle':
    - Output validates as DecisionPayload.
    - Includes income-limit conflict (S1 vs S2) with both citations quote_verified=True.
    - Includes missing renewal conditions.
    - Includes a checklist with >= 4 items whose first items address the HIGH conflict(s).
    """
    mock_llm = MockLLMClient()
    result = await decide(
        query=QUERY,
        decision=DECISION,
        synthesis=m3_synthesis,
        sources=m2_sources,
        llm=mock_llm,
        today=TODAY,
    )

    assert isinstance(result, DecisionPayload)
    assert result.decision == DECISION
    assert result.query == QUERY
    assert result.decision_readiness in ("VERIFY_FIRST", "READY", "INSUFFICIENT_INFORMATION")
    assert result.disclaimer == FIXED_DISCLAIMER

    # Income-limit conflict check
    income_conflicts = [c for c in result.conflicting_claims if "income" in c.topic.lower()]
    assert len(income_conflicts) >= 1
    c1 = income_conflicts[0]
    assert c1.severity == "HIGH"
    assert len(c1.claims) == 2
    assert all(cl.quote_verified for cl in c1.claims), "Both claims in income conflict must have verified quotes"
    claim_source_ids = {cl.source_id for cl in c1.claims}
    assert "S1" in claim_source_ids and "S2" in claim_source_ids

    # Missing renewal conditions
    renewal_missing = [m for m in result.missing_information if "renewal" in m.description.lower()]
    assert len(renewal_missing) >= 1
    assert renewal_missing[0].provenance == "AI_INFERRED"

    # Verification checklist
    assert len(result.actionable_verification_checklist) >= 4
    # First item(s) must address the HIGH conflict
    first_item = result.actionable_verification_checklist[0]
    assert first_item.urgency == "CRITICAL"
    assert any(rid in ("C1", "C2", "C3") for rid in first_item.related_ids)


def test_all_evidence_and_conflicts_have_nonempty_time_message(
    m3_synthesis: SynthesisPayload,
    m2_sources: list[TrustedSource],
):
    """Every relevant_fact and conflicting_claim has a non-empty time_relevance.message."""
    mock_fixture = json.loads((FIXTURES_DIR / "llm" / "decision_response.json").read_text(encoding="utf-8"))
    raw_llm = DecisionLLMOutput.model_validate(mock_fixture)

    result = process_decision_output(
        raw_output=raw_llm,
        query=QUERY,
        decision=DECISION,
        sources=m2_sources,
        today=TODAY,
    )

    for f in result.relevant_facts:
        assert f.time_relevance.message.strip(), f"Fact {f.evidence_id} has empty time_relevance.message"
    for c in result.conflicting_claims:
        assert c.time_relevance.message.strip(), f"Conflict {c.conflict_id} has empty time_relevance.message"


def test_time_level_never_lowered(m2_sources: list[TrustedSource]):
    """If LLM attempts to lower a deterministic STALE or AGING source to CURRENT, level remains at least as severe."""
    # S4 is STALE (age_days = 609 > 540)
    s4 = next(s for s in m2_sources if s.source_id == "S4")
    assert s4.age_days is not None and s4.age_days > 540

    # Craft an LLM output claiming S4 is CURRENT
    raw_output = DecisionLLMOutput(
        decision_readiness="READY",
        summary="Testing time level lowering prevention.",
        relevant_facts=[
            EvidenceItemLLM(
                evidence_id="E_TEST",
                statement="According to S4, scholarship requires college verification.",
                provenance="SOURCED",
                citations=[CitationLLM(source_id="S4", quote="scholarship requires college verification.")],
                confidence=0.8,
                time_relevance_level="CURRENT",  # Attempted downgrade to CURRENT
                time_relevance_message="LLM claims it is current.",
                relevance_to_decision="Test",
            )
        ],
        conflicting_claims=[],
        missing_information=[],
        actionable_verification_checklist=[],
    )

    result = process_decision_output(
        raw_output=raw_output,
        query=QUERY,
        decision=DECISION,
        sources=m2_sources,
        today=TODAY,
    )

    fact = result.relevant_facts[0]
    assert fact.time_relevance.level == "STALE", "Deterministic STALE level must not be lowered to CURRENT by LLM"


def test_hallucinated_quote_downgrades_to_ai_inferred(m2_sources: list[TrustedSource]):
    """Crafted response with a made-up quote -> quote_verified=False, item downgraded to AI_INFERRED, warning present."""
    raw_output = DecisionLLMOutput(
        decision_readiness="READY",
        summary="Testing hallucinated quote handling.",
        relevant_facts=[
            EvidenceItemLLM(
                evidence_id="E_HALLUCINATED",
                statement="The scholarship provides free laptops to all recipients.",
                provenance="SOURCED",
                citations=[
                    CitationLLM(
                        source_id="S1",
                        quote="All recipients shall receive a brand new high performance laptop free of cost.",
                    )
                ],
                confidence=0.90,
                time_relevance_level="CURRENT",
                time_relevance_message="Test message",
                relevance_to_decision="Test",
            )
        ],
        conflicting_claims=[],
        missing_information=[],
        actionable_verification_checklist=[],
    )

    result = process_decision_output(
        raw_output=raw_output,
        query=QUERY,
        decision=DECISION,
        sources=m2_sources,
        today=TODAY,
    )

    fact = result.relevant_facts[0]
    assert fact.provenance == "AI_INFERRED"
    assert fact.citations[0].quote_verified is False
    assert fact.confidence == 0.45, "Confidence must be halved on unverified quote downgrade (0.90 * 0.5 = 0.45)"
    assert any("E_HALLUCINATED downgraded" in w for w in result.warnings)


def test_trust_formula_unit_and_zero_facts():
    """Trust formula hand-computed unit tests and zero-facts guardrail."""
    summary, score, label, zero_facts = compute_trust_summary(
        relevant_facts=[],
        conflicts=[],
        missing_items=[],
    )
    assert score == 0.0
    assert label == "LOW"
    assert zero_facts is True
    assert summary.components["evidence_strength"] == 0.0


def test_readiness_guardrail(m2_sources: list[TrustedSource]):
    """HIGH conflict forces readiness from READY to VERIFY_FIRST."""
    raw_output = DecisionLLMOutput(
        decision_readiness="READY",  # LLM erroneously outputs READY
        summary="Testing readiness guardrail.",
        relevant_facts=[
            EvidenceItemLLM(
                evidence_id="E1",
                statement="85% marks required.",
                provenance="AI_INFERRED",
                citations=[],
                confidence=0.8,
                time_relevance_level="CURRENT",
                time_relevance_message="Test message",
                relevance_to_decision="Test",
            )
        ],
        conflicting_claims=[
            ConflictingClaimSetLLM(
                conflict_id="C1",
                topic="Income cap",
                severity="HIGH",
                claims=[
                    CitedClaimLLM(source_id="S1", claim="₹6 Lakh", quote="₹6,00,000"),
                    CitedClaimLLM(source_id="S2", claim="₹8 Lakh", quote="₹8,00,000"),
                ],
                why_it_matters_for_decision="Critical threshold difference",
                suggested_resolution="Check portal",
                confidence=0.85,
                time_relevance_level="CURRENT",
                time_relevance_message="Test",
                provenance="AI_INFERRED",
            )
        ],
        missing_information=[],
        actionable_verification_checklist=[],
    )

    result = process_decision_output(
        raw_output=raw_output,
        query=QUERY,
        decision=DECISION,
        sources=m2_sources,
        today=TODAY,
    )

    assert result.decision_readiness == "VERIFY_FIRST", "HIGH conflict must prevent READY status"


def test_checklist_auto_append_and_dangling_ids(m2_sources: list[TrustedSource]):
    """Uncovered HIGH conflict gets an auto-appended checklist item, and dangling related_ids are removed."""
    raw_output = DecisionLLMOutput(
        decision_readiness="VERIFY_FIRST",
        summary="Testing auto-append.",
        relevant_facts=[],
        conflicting_claims=[
            ConflictingClaimSetLLM(
                conflict_id="C1",
                topic="Income cap conflict",
                severity="HIGH",
                claims=[
                    CitedClaimLLM(source_id="S1", claim="₹6 Lakh", quote="₹6,00,000"),
                    CitedClaimLLM(source_id="S2", claim="₹8 Lakh", quote="₹8,00,000"),
                ],
                why_it_matters_for_decision="Matters",
                suggested_resolution="Official portal",
                confidence=0.85,
                time_relevance_level="CURRENT",
                time_relevance_message="Test",
                provenance="AI_INFERRED",
            )
        ],
        missing_information=[],
        actionable_verification_checklist=[
            ChecklistItemLLM(
                item_id="V1",
                priority=1,
                urgency="IMPORTANT",
                action="Review guidelines",
                reason="Review",
                related_ids=["C999_DANGLING"],  # Non-existent ID
                verify_with="Helpdesk",
            )
        ],
    )

    result = process_decision_output(
        raw_output=raw_output,
        query=QUERY,
        decision=DECISION,
        sources=m2_sources,
        today=TODAY,
    )

    # Dangling ID dropped
    assert "C999_DANGLING" not in result.actionable_verification_checklist[0].related_ids

    # Uncovered C1 auto-appended
    assert len(result.actionable_verification_checklist) == 2
    auto_item = result.actionable_verification_checklist[1]
    assert auto_item.urgency == "CRITICAL"
    assert "C1" in auto_item.related_ids
    assert any("Auto-appended" in w for w in result.warnings)


@pytest.mark.asyncio
async def test_write_golden_fixture(
    m3_synthesis: SynthesisPayload,
    m2_sources: list[TrustedSource],
):
    """Generate tests/fixtures/m4_output.json from the mock decision run."""
    mock_llm = MockLLMClient()
    result = await decide(
        query=QUERY,
        decision=DECISION,
        synthesis=m3_synthesis,
        sources=m2_sources,
        llm=mock_llm,
        today=TODAY,
    )

    M4_PATH.write_text(result.model_dump_json(indent=2), encoding="utf-8")
    assert M4_PATH.exists()
    assert M4_PATH.stat().st_size > 100

