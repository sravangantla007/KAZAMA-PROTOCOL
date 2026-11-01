from __future__ import annotations
import json
from typing import Type, TypeVar
from pydantic import BaseModel, ValidationError

from app.errors import LLMOutputError

T = TypeVar("T", bound=BaseModel)

DISCLAIMER = (
    "This analysis highlights potential information gaps, conflicts, and outdated details "
    "based only on the sources reviewed. AI-generated items are signals, not confirmed facts. "
    "Verify important details with the official source before making a decision."
)


class LLMClient:
    """Provider-agnostic LLM interface. All LLM access must go through this class."""

    async def generate_json(self, system: str, user: str, model_cls: Type[T]) -> T:
        raise NotImplementedError("Subclasses must implement generate_json")

    def _parse_with_retry_context(self, raw: str, model_cls: Type[T], error_text: str = "") -> T:
        """Parse raw JSON into model_cls; raises LLMOutputError on failure."""
        try:
            data = json.loads(raw)
            return model_cls.model_validate(data)
        except (json.JSONDecodeError, ValidationError) as exc:
            raise LLMOutputError(f"Failed to parse LLM output: {exc}\nError context: {error_text}") from exc
