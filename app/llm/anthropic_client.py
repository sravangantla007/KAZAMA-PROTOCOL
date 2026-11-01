from __future__ import annotations
import json
from typing import Type, TypeVar
import httpx
from pydantic import BaseModel, ValidationError

from app.llm.client import LLMClient
from app.errors import LLMOutputError
from app.config import settings

T = TypeVar("T", bound=BaseModel)


class AnthropicClient(LLMClient):
    API_URL = "https://api.anthropic.com/v1/messages"
    ANTHROPIC_VERSION = "2023-06-01"

    async def generate_json(self, system: str, user: str, model_cls: Type[T], purpose: str = "synthesis") -> T:
        model = settings.llm_model or "claude-3-5-sonnet-20241022"
        headers = {
            "x-api-key": settings.llm_api_key,
            "anthropic-version": self.ANTHROPIC_VERSION,
            "content-type": "application/json",
        }
        payload = {
            "model": model,
            "max_tokens": 8192,
            "temperature": 0,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        }
        last_error: str = ""
        for attempt in range(2):
            if attempt == 1 and last_error:
                user_retry = user + f"\n\nPREVIOUS VALIDATION ERROR (fix your JSON output):\n{last_error}"
                payload["messages"] = [{"role": "user", "content": user_retry}]
            async with httpx.AsyncClient(timeout=120) as client:
                resp = await client.post(self.API_URL, headers=headers, json=payload)
                resp.raise_for_status()
                data = resp.json()
            raw = data["content"][0]["text"]
            try:
                parsed = json.loads(raw)
                return model_cls.model_validate(parsed)
            except (json.JSONDecodeError, ValidationError) as exc:
                last_error = str(exc)
        raise LLMOutputError(f"LLM output invalid after retry: {last_error}")
