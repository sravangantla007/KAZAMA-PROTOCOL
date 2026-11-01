"""G0 gate tests: contract round-trips, extra-field rejection, score bounds."""
from __future__ import annotations
import pytest
from datetime import date, datetime, timezone
from pydantic import ValidationError

from app.contracts import (
    RawSource, IngestionIssue, IngestionResult,
    WeightBreakdown, TrustedSource,
    SourceQuote, SynthFact, SynthesisPayload,
    Citation, TimeRelevance, EvidenceItem, DecisionPayload,
    TrustSummary, ChecklistItem, MissingItem, ConflictingClaimSet, CitedClaim,
)


def make_raw_source(**kwargs) -> RawSource:
    defaults = dict(
        source_id="S1",
        source_type="web",
        url_or_filename="https://example.com",
        text="x" * 100,
        published_date=date(2025, 1, 1),
        char_count=100,
    )
    defaults.update(kwargs)
    return RawSource(**defaults)


def make_weight_breakdown(**kwargs) -> WeightBreakdown:
    defaults = dict(
        base=0.9,
        domain_rule_matched="tld:gov.in",
        ai_penalty_applied=0.05,
        undated_penalty_applied=0.0,
        ai_detection_reliable=True,
    )
    defaults.update(kwargs)
    return WeightBreakdown(**defaults)


def make_trusted_source(**kwargs) -> TrustedSource:
    wb = make_weight_breakdown()
    defaults = dict(
        source_id="S1",
        source_type="web",
        url_or_filename="https://example.com",
        text="x" * 100,
        published_date=date(2025, 1, 1),
        char_count=100,
        ai_probability_score=0.1,
        domain_weight=0.9,
        baseline_trust_score=0.85,
        weight_breakdown=wb,
    )
    defaults.update(kwargs)
    return TrustedSource(**defaults)


def test_raw_source_round_trip():
    src = make_raw_source()
    assert RawSource.model_validate(src.model_dump()) == src


def test_raw_source_rejects_extra_field():
    with pytest.raises(ValidationError):
        RawSource(
            source_id="S1", source_type="web",
            url_or_filename="https://example.com",
            text="x" * 100, published_date=None,
            extra_unknown_field="bad",
        )


def test_trusted_source_is_subclass_of_raw_source():
    ts = make_trusted_source()
    assert isinstance(ts, RawSource)


def test_score_bounds_rejected():
    with pytest.raises(ValidationError):
        make_trusted_source(ai_probability_score=1.5)
    with pytest.raises(ValidationError):
        make_trusted_source(baseline_trust_score=-0.1)


def test_ingestion_result_round_trip():
    src = make_raw_source()
    result = IngestionResult(query="test", mode="mock", sources=[src])
    assert IngestionResult.model_validate(result.model_dump()) == result


def test_ingestion_issue_codes():
    issue = IngestionIssue(target="http://x.com", code="FETCH_FAILED", message="err")
    assert issue.fatal is False


def test_weight_breakdown_extra_rejected():
    with pytest.raises(ValidationError):
        WeightBreakdown(
            base=0.9, domain_rule_matched="x",
            ai_penalty_applied=0.0, undated_penalty_applied=0.0,
            ai_detection_reliable=True, extra_junk=True,
        )


def test_url_safety_basic():
    from app.utils.url_safety import is_safe_url
    assert is_safe_url("https://example.com")[0] is True
    assert is_safe_url("http://127.0.0.1")[0] is False
    assert is_safe_url("file:///etc/passwd")[0] is False
    assert is_safe_url("http://10.0.0.1")[0] is False
    assert is_safe_url("http://169.254.169.254")[0] is False
