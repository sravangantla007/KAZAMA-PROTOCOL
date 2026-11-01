"""Time-relevance determination and comparison utilities."""
from __future__ import annotations
from datetime import date
from typing import Optional

from app.contracts.common import TimeLevel
from app.contracts.trusted import TrustedSource

SEVERITY_ORDER: dict[TimeLevel, int] = {
    "NOT_APPLICABLE": 0,
    "CURRENT": 1,
    "AGING": 2,
    "UNDATED": 3,
    "STALE": 4,
}


def compute_deterministic_time_level(src: TrustedSource) -> TimeLevel:
    """
    Computes time relevance level based on source age_days:
    - age_days is None -> UNDATED
    - age_days <= 180  -> CURRENT
    - 181 <= age_days <= 540 -> AGING
    - age_days > 540   -> STALE
    """
    if src.age_days is None:
        return "UNDATED"
    if src.age_days <= 180:
        return "CURRENT"
    if src.age_days <= 540:
        return "AGING"
    return "STALE"


def max_severity(level_a: TimeLevel, level_b: TimeLevel) -> TimeLevel:
    """Returns the more severe time level between level_a and level_b."""
    sev_a = SEVERITY_ORDER.get(level_a, 0)
    sev_b = SEVERITY_ORDER.get(level_b, 0)
    return level_a if sev_a >= sev_b else level_b


def fallback_time_message(level: TimeLevel, source_dates: list[Optional[date]]) -> str:
    """Generates a non-empty fallback message for the time level if the LLM's message is empty."""
    valid_dates = [d.isoformat() for d in source_dates if d is not None]
    date_str = ", ".join(valid_dates) if valid_dates else "None"

    if level == "CURRENT":
        return f"Source date(s) ({date_str}) are within the last 6 months and appear current for this cycle."
    elif level == "AGING":
        return f"Source date(s) ({date_str}) are between 6 and 18 months old; verify if terms have changed."
    elif level == "STALE":
        return f"Source date(s) ({date_str}) are over 18 months old; policy or deadlines may have expired."
    elif level == "UNDATED":
        return "No publication date is visible; confirm this information is current before relying on it."
    else:
        return "Time relevance is not applicable to this item."

