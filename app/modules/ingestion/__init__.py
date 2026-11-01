from __future__ import annotations
import asyncio
import hashlib
from datetime import datetime, timezone
from typing import Optional

from app.config import settings
from app.contracts.raw import (
    RawSource, IngestionResult, IngestionIssue, UploadedFile,
)
from app.utils.hash_utils import sha256_of_text
from app.utils.text_utils import normalize_text, truncate_to_chars, non_whitespace_count
from app.utils.date_utils import is_future_date

MIN_TEXT_CHARS = 50  # non-whitespace minimum


async def ingest(
    query: str,
    urls: list[str],
    files: list[UploadedFile],
    mock_mode: bool = False,
    mock_scenario: Optional[str] = None,
) -> IngestionResult:
    """Main entry point for Module 1."""

    # --- MOCK MODE ---
    if mock_mode or settings.mock_mode:
        from app.modules.ingestion.mock_loader import load_mock_scenario
        return load_mock_scenario(mock_scenario or "scholarship_scenario")

    # --- LIVE MODE ---
    sources: list[RawSource] = []
    issues: list[IngestionIssue] = []
    seen_hashes: set[str] = set()
    counter = [0]

    def next_id() -> str:
        counter[0] += 1
        return f"S{counter[0]}"

    # Enforce file limits
    if len(files) > settings.max_files:
        issues.append(IngestionIssue(
            target="request",
            code="UNSUPPORTED_TYPE",
            message=f"Too many files: max {settings.max_files}",
        ))
        files = files[:settings.max_files]

    # 1. Parse uploaded files (user_documents first)
    from app.modules.ingestion.file_parser import parse_file
    from app.modules.ingestion.date_extractor import extract_date_from_text_regex

    for uf in files:
        text, file_issues = parse_file(uf.filename, uf.content_base64, uf.mime_type)
        issues.extend(file_issues)
        if text is None:
            continue
        text = normalize_text(text)
        text, truncated = truncate_to_chars(text, settings.max_chars_per_source)
        if non_whitespace_count(text) < MIN_TEXT_CHARS:
            issues.append(IngestionIssue(
                target=uf.filename, code="EMPTY_TEXT",
                message="Extracted text has fewer than 50 non-whitespace characters",
            ))
            continue
        h = sha256_of_text(text)
        if h in seen_hashes:
            issues.append(IngestionIssue(target=uf.filename, code="DUPLICATE", message="Duplicate content"))
            continue
        seen_hashes.add(h)
        if truncated:
            issues.append(IngestionIssue(target=uf.filename, code="TRUNCATED", message="Text truncated to MAX_CHARS_PER_SOURCE", fatal=False))
        date_result = extract_date_from_text_regex(text)
        published_date = date_result[0] if date_result else None
        date_origin = date_result[1] if date_result else None
        src = RawSource(
            source_id=next_id(),
            source_type="user_document",
            url_or_filename=uf.filename,
            text=text,
            published_date=published_date,
            date_origin=date_origin,
            fetched_at=datetime.now(timezone.utc),
            content_hash=h,
            truncated=truncated,
            char_count=len(text),
        )
        sources.append(src)

    # 2. Fetch user-provided URLs concurrently
    from app.modules.ingestion.fetcher import fetch_url

    url_tasks = [fetch_url(url, f"__TEMP_{i}") for i, url in enumerate(urls)]
    url_results = await asyncio.gather(*url_tasks, return_exceptions=True)
    for url, result in zip(urls, url_results):
        if isinstance(result, Exception):
            issues.append(IngestionIssue(target=url, code="FETCH_FAILED", message=str(result)))
            continue
        src, fetch_issues = result
        issues.extend(fetch_issues)
        if src is None:
            continue
        src = _postprocess_source(src, next_id(), seen_hashes, issues, settings.max_chars_per_source)
        if src:
            sources.append(src)

    # 3. Search results (if provider configured)
    remaining = max(0, settings.max_sources - len(sources))
    if remaining > 0:
        from app.modules.ingestion.search import get_search_provider
        provider = get_search_provider()
        hits = await provider.search(query, remaining)
        search_tasks = [fetch_url(hit.url, f"__TEMP_SEARCH_{i}") for i, hit in enumerate(hits)]
        search_results = await asyncio.gather(*search_tasks, return_exceptions=True)
        for hit, result in zip(hits, search_results):
            if isinstance(result, Exception):
                issues.append(IngestionIssue(target=hit.url, code="FETCH_FAILED", message=str(result)))
                continue
            src, fetch_issues = result
            issues.extend(fetch_issues)
            if src is None:
                continue
            if not src.title:
                object.__setattr__(src, "title", hit.title)
            src = _postprocess_source(src, next_id(), seen_hashes, issues, settings.max_chars_per_source)
            if src:
                sources.append(src)

    # Truncate to MAX_SOURCES
    sources = sources[:settings.max_sources]

    return IngestionResult(query=query, mode="live", sources=sources, issues=issues)


def _postprocess_source(
    src: RawSource,
    new_id: str,
    seen_hashes: set[str],
    issues: list[IngestionIssue],
    max_chars: int,
) -> Optional[RawSource]:
    text = normalize_text(src.text)
    text, truncated = truncate_to_chars(text, max_chars)
    if non_whitespace_count(text) < MIN_TEXT_CHARS:
        issues.append(IngestionIssue(
            target=src.url_or_filename, code="EMPTY_TEXT",
            message="Extracted text too short",
        ))
        return None
    h = sha256_of_text(text)
    if h in seen_hashes:
        issues.append(IngestionIssue(target=src.url_or_filename, code="DUPLICATE", message="Duplicate content"))
        return None
    seen_hashes.add(h)
    if truncated:
        issues.append(IngestionIssue(target=src.url_or_filename, code="TRUNCATED",
                                      message="Text truncated to MAX_CHARS_PER_SOURCE", fatal=False))
    return RawSource(
        source_id=new_id,
        source_type=src.source_type,
        url_or_filename=src.url_or_filename,
        text=text,
        published_date=src.published_date,
        title=src.title,
        date_origin=src.date_origin,
        fetched_at=src.fetched_at,
        content_hash=h,
        truncated=truncated,
        char_count=len(text),
    )
