"""Verbatim and fuzzy quote verification against source texts."""
from __future__ import annotations
import re
from rapidfuzz import fuzz

QUOTE_DASH_TRANSLATION = str.maketrans({
    "“": '"', "”": '"', "„": '"', "«": '"', "»": '"',
    "‘": "'", "’": "'", "‚": "'", "`": "'",
    "—": "-", "–": "-", "−": "-", "―": "-",
})


def normalize_text_for_verification(s: str) -> str:
    """Lowercase, collapse whitespace, and unify quote/dash characters."""
    s = s.translate(QUOTE_DASH_TRANSLATION)
    s = s.lower()
    return re.sub(r"\s+", " ", s).strip()


def verify_quote(quote: str, source_text: str) -> bool:
    """
    Verifies that quote is grounded in source_text.
    Returns True if normalized quote is a substring of source_text OR
    if rapidfuzz partial_ratio >= 92.
    """
    if not quote or not source_text:
        return False

    norm_quote = normalize_text_for_verification(quote)
    norm_source = normalize_text_for_verification(source_text)

    if not norm_quote:
        return False

    if norm_quote in norm_source:
        return True

    ratio = fuzz.partial_ratio(norm_quote, norm_source)
    return ratio >= 92.0

