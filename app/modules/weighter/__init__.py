"""Module 2: The Weighter — static domain trust, AI penalty heuristic, and importance budgeting."""
from __future__ import annotations
from datetime import date
from app.contracts.raw import IngestionResult
from app.contracts.trusted import TrustedSource
from app.modules.weighter.scorer import weight_source
from app.config import settings


def weight(ingestion: IngestionResult, today: date) -> list[TrustedSource]:
    """
    Main entry point for Module 2.
    Converts IngestionResult sources into scored TrustedSource objects,
    sorted by importance_score descending, capped at MAX_SOURCES (protecting user docs).
    """
    trusted_list: list[TrustedSource] = []
    for src in ingestion.sources:
        ts = weight_source(src, query=ingestion.query, today=today)
        trusted_list.append(ts)

    # Sort by importance_score descending; ties broken deterministically by source_id ascending
    trusted_list.sort(key=lambda s: (-s.importance_score, s.source_id))

    # Context budgeting truncation: cap to MAX_SOURCES, never dropping a user_document
    max_src = settings.max_sources
    if len(trusted_list) > max_src:
        user_docs = [s for s in trusted_list if s.source_type == "user_document"]
        web_docs = [s for s in trusted_list if s.source_type != "user_document"]
        allowed_web = max(0, max_src - len(user_docs))
        truncated = user_docs + web_docs[:allowed_web]
        truncated.sort(key=lambda s: (-s.importance_score, s.source_id))
        return truncated

    return trusted_list

