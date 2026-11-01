from __future__ import annotations
from datetime import date
from typing import Optional
import re


_ISO_RE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
_HUMAN_RE = re.compile(
    r"\b(\d{1,2})\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4})\b",
    re.IGNORECASE,
)
_MONTH_MAP = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
}


def safe_parse_date(value: str) -> Optional[date]:
    """Parse ISO or human-readable date string. Returns None on failure."""
    if not value:
        return None
    value = value.strip()
    # ISO
    m = _ISO_RE.match(value[:10])
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            pass
    # Human readable
    m2 = _HUMAN_RE.search(value)
    if m2:
        try:
            return date(int(m2.group(3)), _MONTH_MAP[m2.group(2).lower()], int(m2.group(1)))
        except ValueError:
            pass
    return None


def is_future_date(d: date) -> bool:
    return d > date.today()
