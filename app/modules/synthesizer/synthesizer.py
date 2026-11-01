"""Module 3 Synthesizer implementation."""
from __future__ import annotations
from datetime import date

from app.contracts.trusted import TrustedSource
from app.contracts.synthesis import SynthesisPayload
from app.llm.client import LLMClient
from app.modules.synthesizer.prompts import (
    SYSTEM_PROMPT, SynthesisLLMOutput, build_synthesis_prompt,
)
from app.modules.synthesizer.calibrate import calibrate_synthesis
from app.config import settings


async def synthesize(
    query: str,
    sources: list[TrustedSource],
    llm: LLMClient,
    today: date,
) -> SynthesisPayload:
    """
    Synthesize facts, conflicts, and missing information from trusted sources.
    Decision-agnostic: builds an objective map of what sources say and where they disagree.
    """
    user_prompt, sources_used, extra_notes = build_synthesis_prompt(
        query=query,
        sources=sources,
        today=today,
    )

    raw_output: SynthesisLLMOutput = await llm.generate_json(
        system=SYSTEM_PROMPT,
        user=user_prompt,
        model_cls=SynthesisLLMOutput,
        purpose="synthesis",
    )

    from app.llm.mock_client import MockLLMClient
    is_mock = settings.mock_llm or isinstance(llm, MockLLMClient)

    model_info = {
        "provider": "mock" if is_mock else settings.llm_provider,
        "model": "replay" if is_mock else settings.llm_model,
        "mock": is_mock,
    }

    payload = calibrate_synthesis(
        raw_output=raw_output,
        query=query,
        sources_used=sources_used,
        trusted_sources=sources,
        model_info=model_info,
        extra_coverage_notes=extra_notes,
    )

    return payload
