from __future__ import annotations


class LLMOutputError(Exception):
    """Raised when LLM output fails Pydantic validation after one retry."""


class IngestionError(Exception):
    """Raised only when the entire ingestion result is unrecoverable."""
