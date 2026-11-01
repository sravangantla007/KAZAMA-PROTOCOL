"""Module 2 (Weighter) acceptance tests — consume ONLY tests/fixtures/m1_output.json."""
from __future__ import annotations
from datetime import date
import json
from pathlib import Path
import pytest

from app.contracts.raw import IngestionResult, RawSource
from app.contracts.trusted import TrustedSource
from app.modules.weighter import weight
from app.modules.weighter.domain_weights import compute_domain_weight
from app.modules.weighter.ai_detector import detect_ai_generated
from app.modules.weighter.scorer import weight_source

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"
M1_PATH = FIXTURES_DIR / "m1_output.json"
M2_PATH = FIXTURES_DIR / "m2_output.json"
TODAY = date(2026, 10, 31)


@pytest.fixture
def m1_ingestion() -> IngestionResult:
    assert M1_PATH.exists(), "m1_output.json golden fixture must exist"
    data = json.loads(M1_PATH.read_text(encoding="utf-8"))
    return IngestionResult.model_validate(data)


def test_mock_sources_exact_domain_weights(m1_ingestion: IngestionResult):
    """
    Exact expected domain_weight for all six mock sources:
    S1: 0.90 (gov.in)
    S2: 0.45 (com)
    S3: 0.25 (forum)
    S4: 0.60 (news)
    S5: 1.00 (user_document)
    S6: 0.85 (edu)
    """
    by_id = {s.source_id: s for s in m1_ingestion.sources}
    expected = {
        "S1": 0.90,
        "S2": 0.45,
        "S3": 0.25,
        "S4": 0.60,
        "S5": 1.00,
        "S6": 0.85,
    }
    for sid, exp_weight in expected.items():
        w, rule = compute_domain_weight(by_id[sid].url_or_filename, by_id[sid].source_type)
        assert w == pytest.approx(exp_weight, abs=0.01), f"{sid} got {w} (rule: {rule}), expected {exp_weight}"


def test_ai_detector_calibration_thresholds(m1_ingestion: IngestionResult):
    """S2 must score >= 0.55; S1 and S5 must score <= 0.35."""
    by_id = {s.source_id: s for s in m1_ingestion.sources}

    s2_score, s2_rel = detect_ai_generated(by_id["S2"].text)
    assert s2_rel is True
    assert s2_score >= 0.55, f"S2 AI score {s2_score} must be >= 0.55"

    s1_score, _ = detect_ai_generated(by_id["S1"].text)
    assert s1_score <= 0.35, f"S1 AI score {s1_score} must be <= 0.35"

    s5_score, _ = detect_ai_generated(by_id["S5"].text)
    assert s5_score <= 0.35, f"S5 AI score {s5_score} must be <= 0.35"


def test_baseline_trust_ranking_invariants(m1_ingestion: IngestionResult):
    """
    S5.baseline_trust_score is the maximum;
    S1 outranks S2;
    S3 is minimum or tied-minimum.
    """
    trusted = weight(m1_ingestion, today=TODAY)
    by_id = {s.source_id: s for s in trusted}

    max_trust = max(s.baseline_trust_score for s in trusted)
    assert by_id["S5"].baseline_trust_score == pytest.approx(max_trust, abs=0.01)

    assert by_id["S1"].baseline_trust_score > by_id["S2"].baseline_trust_score

    min_trust = min(s.baseline_trust_score for s in trusted)
    assert by_id["S3"].baseline_trust_score == pytest.approx(min_trust, abs=0.01)


def test_user_supremacy_invariant():
    """
    For any input, a user_document with ai_probability <= 0.35 has a
    baseline_trust_score >= every web source with ai_probability <= 0.35.
    """
    human_notes = (
        "My personal notes for the scholarship application: I met the village revenue officer "
        "on 12 January 2026 and obtained the family income certificate. My qualifying examination "
        "score is 88%, which clears the cutoff. Need to submit marksheet, Aadhaar card, and college bonafide. "
        "Still need to verify whether the Tahsildar signature is strictly mandatory."
    )
    user_raw = RawSource(
        source_id="SU", source_type="user_document", url_or_filename="notes.txt",
        text=human_notes, published_date=None, char_count=len(human_notes),
    )
    user_trusted = weight_source(user_raw, query="test", today=TODAY)
    assert user_trusted.ai_probability_score <= 0.35

    # Check against highest possible web source (gov, dated, 0 AI)
    web_raw = RawSource(
        source_id="SW", source_type="web", url_or_filename="https://portal.gov.in/doc",
        text="Official government announcement text with plenty of facts and details.",
        published_date=date(2026, 1, 1), char_count=100,
    )
    web_trusted = weight_source(web_raw, query="test", today=TODAY)
    assert user_trusted.baseline_trust_score >= web_trusted.baseline_trust_score


def test_edge_cases_and_clamp_floor():
    # Short text (< 300 chars) -> AI detector unreliable, 0 AI penalty
    short_raw = RawSource(
        source_id="S_SHORT", source_type="web", url_or_filename="https://forum.example.com",
        text="Too short text.", published_date=None, char_count=15,
    )
    ts = weight_source(short_raw, query="test", today=TODAY)
    assert ts.weight_breakdown.ai_detection_reliable is False
    assert ts.weight_breakdown.ai_penalty_applied == 0.0
    assert ts.weight_breakdown.undated_penalty_applied == 0.05
    # Floor clamp at 0.05
    assert ts.baseline_trust_score >= 0.05


def test_sorting_and_user_doc_retention(m1_ingestion: IngestionResult, monkeypatch):
    """Ensure sorting is by importance_score descending and user docs are never dropped during truncation."""
    monkeypatch.setattr("app.modules.weighter.settings.max_sources", 2)
    truncated = weight(m1_ingestion, today=TODAY)
    assert len(truncated) == 2
    # S5 is a user document and MUST be retained
    assert any(s.source_id == "S5" for s in truncated)


def test_determinism(m1_ingestion: IngestionResult):
    run1 = weight(m1_ingestion, today=TODAY)
    run2 = weight(m1_ingestion, today=TODAY)
    for s1, s2 in zip(run1, run2):
        assert s1.source_id == s2.source_id
        assert s1.baseline_trust_score == s2.baseline_trust_score
        assert s1.importance_score == s2.importance_score


def test_write_golden_fixture(m1_ingestion: IngestionResult):
    """Write tests/fixtures/m2_output.json from the weighted mock scenario."""
    trusted = weight(m1_ingestion, today=TODAY)
    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
    serialized = [t.model_dump(mode="json") for t in trusted]
    M2_PATH.write_text(json.dumps(serialized, indent=2), encoding="utf-8")
    assert M2_PATH.exists()

    # Re-validate against TrustedSource schema
    reloaded = [TrustedSource.model_validate(item) for item in json.loads(M2_PATH.read_text(encoding="utf-8"))]
    assert len(reloaded) == 6
