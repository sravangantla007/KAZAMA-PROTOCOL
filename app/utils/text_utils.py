from __future__ import annotations
import re
import unicodedata


def normalize_text(text: str) -> str:
    """Normalize whitespace and Unicode for hashing and comparison."""
    text = unicodedata.normalize("NFKC", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def normalize_for_comparison(text: str) -> str:
    """Lowercase + collapse whitespace + unify quote/dash chars. Used for quote verification."""
    text = normalize_text(text).lower()
    # Unify typographic quotes and dashes
    text = re.sub(r"[\"''\u2018\u2019\u201c\u201d]", "'", text)
    text = re.sub(r"[\u2013\u2014\u2015]", "-", text)
    return text


def non_whitespace_count(text: str) -> int:
    return len(re.sub(r"\s", "", text))


def truncate_to_chars(text: str, max_chars: int) -> tuple[str, bool]:
    """Return (text, was_truncated). Truncates at word boundary where possible."""
    if len(text) <= max_chars:
        return text, False
    truncated = text[:max_chars]
    # Try to end at last space
    last_space = truncated.rfind(" ")
    if last_space > max_chars * 0.8:
        truncated = truncated[:last_space]
    return truncated, True
