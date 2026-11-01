from __future__ import annotations
import os
from app.llm.client import LLMClient
from app.config import settings


def get_llm_client() -> LLMClient:
    """Factory to retrieve configured LLM client instance."""
    if settings.mock_llm:
        from app.llm.mock_client import MockLLMClient
        return MockLLMClient()

    provider = (settings.llm_provider or "gemini").lower()
    
    # If explicitly anthropic and an Anthropic key exists, use Anthropic; otherwise default to Gemini
    if provider == "anthropic" and (settings.llm_api_key.startswith("sk-ant") or os.environ.get("ANTHROPIC_API_KEY")):
        from app.llm.anthropic_client import AnthropicClient
        return AnthropicClient()
    
    # Default is Gemini 3.5 Flash for the hackathon
    from app.llm.gemini_client import GeminiClient
    return GeminiClient()


__all__ = ["LLMClient", "get_llm_client"]

