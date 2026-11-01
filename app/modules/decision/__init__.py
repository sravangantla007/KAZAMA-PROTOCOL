"""Module 4 Decision Engine package."""
from app.modules.decision.engine import decide, process_decision_output, FIXED_DISCLAIMER
from app.modules.decision.prompts import DecisionLLMOutput, build_decision_prompt
from app.modules.decision.verify_quotes import verify_quote
from app.modules.decision.time_relevance import compute_deterministic_time_level, max_severity
from app.modules.decision.scoring import compute_trust_summary

__all__ = [
    "decide",
    "process_decision_output",
    "FIXED_DISCLAIMER",
    "DecisionLLMOutput",
    "build_decision_prompt",
    "verify_quote",
    "compute_deterministic_time_level",
    "max_severity",
    "compute_trust_summary",
]

