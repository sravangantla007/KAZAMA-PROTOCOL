from __future__ import annotations
from typing import Literal
from pydantic import confloat

SourceType  = Literal["web", "user_document"]
Provenance  = Literal["SOURCED", "AI_INFERRED"]
Severity    = Literal["HIGH", "MEDIUM", "LOW"]
Importance  = Literal["CRITICAL", "IMPORTANT", "MINOR"]
TimeLevel   = Literal["CURRENT", "AGING", "STALE", "UNDATED", "NOT_APPLICABLE"]
Readiness   = Literal["READY", "VERIFY_FIRST", "INSUFFICIENT_INFORMATION"]
TrustLabel  = Literal["HIGH", "MEDIUM", "LOW"]
Score       = confloat(ge=0.0, le=1.0)
