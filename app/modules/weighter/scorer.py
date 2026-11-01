"""Scoring, relevance, trust computation, and importance ordering for sources."""
from __future__ import annotations
from datetime import date
import re
from typing import Optional

from app.contracts.common import Score
from app.contracts.raw import RawSource
from app.contracts.trusted import TrustedSource, WeightBreakdown
from app.modules.weighter.domain_weights import compute_domain_weight
from app.modules.weighter.ai_detector import detect_ai_generated
from app.config import settings

AI_PENALTY_MAX_WEB = 0.40
AI_PENALTY_MAX_USER = 0.15
UNDATED_PENALTY_WEB = 0.05

STOPWORDS = {
    "a", "about", "above", "after", "again", "against", "all", "am", "an", "and",
    "any", "are", "aren't", "as", "at", "be", "because", "been", "before", "being",
    "below", "between", "both", "but", "by", "can", "cannot", "could", "did", "do",
    "does", "doing", "down", "during", "each", "few", "for", "from", "further",
    "had", "has", "have", "having", "he", "her", "here", "hers", "herself", "him",
    "himself", "his", "how", "i", "if", "in", "into", "is", "it", "its", "itself",
    "me", "more", "most", "my", "myself", "no", "nor", "not", "of", "off", "on",
    "once", "only", "or", "other", "ought", "our", "ours", "ourselves", "out",
    "over", "own", "same", "she", "should", "so", "some", "such", "than", "that",
    "the", "their", "theirs", "them", "themselves", "then", "there", "these",
    "they", "this", "those", "through", "to", "too", "under", "until", "up",
    "very", "was", "we", "were", "what", "when", "where", "which", "while", "who",
    "whom", "why", "with", "would", "you", "your", "yours", "yourself",
}


def compute_query_relevance(query: str, title: Optional[str], text_prefix: str) -> float:
    """Compute normalized token overlap between query terms and source text."""
    query_tokens = [w for w in re.findall(r"\b[a-z0-9]+\b", query.lower()) if w not in STOPWORDS]
    if not query_tokens:
        return 0.5  # neutral if query has only stopwords

    doc_text = f"{title or ''} {text_prefix[:3000]}".lower()
    doc_tokens = set(re.findall(r"\b[a-z0-9]+\b", doc_text))

    hits = sum(1 for q in query_tokens if q in doc_tokens)
    overlap = hits / len(query_tokens)
    return round(max(0.0, min(1.0, overlap)), 3)


def weight_source(src: RawSource, query: str, today: date) -> TrustedSource:
    """Evaluate and enrich a RawSource into a TrustedSource."""
    domain_weight, domain_rule = compute_domain_weight(src.url_or_filename, src.source_type)
    ai_prob, ai_reliable = detect_ai_generated(src.text)

    is_user_doc = src.source_type == "user_document"
    penalty_max = AI_PENALTY_MAX_USER if is_user_doc else AI_PENALTY_MAX_WEB

    if ai_reliable:
        ai_penalty = domain_weight * penalty_max * ai_prob
    else:
        ai_penalty = 0.0

    if not is_user_doc and src.published_date is None:
        undated_pen = UNDATED_PENALTY_WEB
    else:
        undated_pen = 0.0

    raw_trust = domain_weight - ai_penalty - undated_pen
    baseline_trust = max(0.05, min(1.0, raw_trust))

    breakdown = WeightBreakdown(
        base=round(domain_weight, 3),
        domain_rule_matched=domain_rule,
        ai_penalty_applied=round(ai_penalty, 3),
        undated_penalty_applied=round(undated_pen, 3),
        ai_detection_reliable=ai_reliable,
    )

    relevance = compute_query_relevance(query, src.title, src.text)
    importance = round(0.7 * baseline_trust + 0.3 * relevance, 3)

    age_days = (today - src.published_date).days if src.published_date else None

    return TrustedSource(
        source_id=src.source_id,
        source_type=src.source_type,
        url_or_filename=src.url_or_filename,
        text=src.text,
        published_date=src.published_date,
        title=src.title,
        date_origin=src.date_origin,
        fetched_at=src.fetched_at,
        content_hash=src.content_hash,
        truncated=src.truncated,
        char_count=src.char_count,
        ai_probability_score=round(ai_prob, 3),
        domain_weight=round(domain_weight, 3),
        baseline_trust_score=round(baseline_trust, 3),
        query_relevance=relevance,
        importance_score=importance,
        age_days=age_days,
        weight_breakdown=breakdown,
    )

