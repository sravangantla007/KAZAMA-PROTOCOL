from __future__ import annotations
from app.llm.client import LLMClient
from app.config import settings


def get_llm_client() -> LLMClient:
    """Factory to retrieve configured LLM client instance."""
    if settings.mock_llm:
        from app.llm.mock_client import MockLLMClient
        return MockLLMClient()

    provider = settings.llm_provider.lower()
    if provider == "gemini":
        from app.llm.gemini_client import GeminiClient
        return GeminiClient()
    elif provider == "anthropic":
        from app.llm.anthropic_client import AnthropicClient
        return AnthropicClient()
    else:
        raise NotImplementedError(f"LLM Provider '{provider}' not implemented. Supported: gemini, anthropic")


__all__ = ["LLMClient", "get_llm_client"]

