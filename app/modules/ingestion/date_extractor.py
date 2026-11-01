from __future__ import annotations
import re
from datetime import date
from typing import Literal, Optional

from app.utils.date_utils import safe_parse_date, is_future_date

DateOrigin = Literal["meta_tag", "json_ld", "http_header", "pdf_metadata", "text_regex"]

_PATTERNS = [
    re.compile(r"Last[- ]?updated[:\s]+(\d{1,2}\s+\w+\s+\d{4})", re.IGNORECASE),
    re.compile(r"Published\s+on[:\s]+(\d{1,2}\s+\w+\s+\d{4})", re.IGNORECASE),
    re.compile(r"Published[:\s]+(\d{4}-\d{2}-\d{2})", re.IGNORECASE),
    re.compile(r"(\d{4}-\d{2}-\d{2})"),
    re.compile(r"(\d{1,2}\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4})", re.IGNORECASE),
]


def extract_date_from_json_ld(json_ld_list: list[dict]) -> Optional[tuple[date, DateOrigin]]:
    """Extract date from JSON-LD objects. Returns (date, origin) or None."""
    candidates = []
    for obj in json_ld_list:
        for key in ("dateModified", "datePublished"):
            val = obj.get(key)
            if val:
                d = safe_parse_date(str(val))
                if d and not is_future_date(d):
                    candidates.append((d, key))
    if not candidates:
        return None
    # Prefer dateModified if later than datePublished
    modified = next((d for d, k in candidates if k == "dateModified"), None)
    published = next((d for d, k in candidates if k == "datePublished"), None)
    if modified and published:
        return (modified, "json_ld") if modified > published else (published, "json_ld")
    chosen = modified or published
    return (chosen, "json_ld") if chosen else None


def extract_date_from_meta(meta_tags: dict[str, str]) -> Optional[tuple[date, DateOrigin]]:
    """Extract from HTML meta tags dict {name/property: content}."""
    priority = [
        "article:published_time", "og:updated_time", "date", "DC.date", "last-modified"
    ]
    published = None
    modified = None
    for key in priority:
        val = meta_tags.get(key)
        if val:
            d = safe_parse_date(val)
            if d and not is_future_date(d):
                if key in ("og:updated_time", "last-modified"):
                    modified = d
                else:
                    published = d
                break
    if modified and published:
        chosen = modified if modified > published else published
    else:
        chosen = modified or published
    return (chosen, "meta_tag") if chosen else None


def extract_date_from_http_header(headers: dict[str, str]) -> Optional[tuple[date, DateOrigin]]:
    """Extract from HTTP Last-Modified header."""
    val = headers.get("last-modified") or headers.get("Last-Modified")
    if not val:
        return None
    d = safe_parse_date(val)
    if d and not is_future_date(d):
        return (d, "http_header")
    return None


def extract_date_from_text_regex(text: str, window: int = 1500) -> Optional[tuple[date, DateOrigin]]:
    """Regex scan over the first `window` chars."""
    snippet = text[:window]
    for pattern in _PATTERNS:
        m = pattern.search(snippet)
        if m:
            d = safe_parse_date(m.group(1))
            if d and not is_future_date(d):
                return (d, "text_regex")
    return None
