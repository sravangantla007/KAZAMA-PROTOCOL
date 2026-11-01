from __future__ import annotations
import asyncio
import json
import re
from typing import Type, TypeVar
from pydantic import BaseModel, ValidationError
import httpx

from app.config import settings
from app.errors import LLMOutputError
from app.llm.client import LLMClient

T = TypeVar("T", bound=BaseModel)

FALLBACK_MODELS = ["gemini-3.5-flash", "gemini-3.1-flash-lite", "gemini-3-flash-preview"]


class GeminiClient(LLMClient):
    """Google Gemini API client with schema enforcement and multi-model fallback on 503."""

    def __init__(self, api_key: str | None = None, model: str | None = None):
        self.api_key = api_key or settings.llm_api_key
        self.model = model or settings.llm_model

    async def generate_json(
        self,
        system: str,
        user: str,
        model_cls: Type[T],
        purpose: str = "general",
    ) -> T:
        schema = model_cls.model_json_schema()

        # Build candidate model list starting with configured model
        models_to_try = [self.model]
        for m in FALLBACK_MODELS:
            if m not in models_to_try:
                models_to_try.append(m)

        headers = {"Content-Type": "application/json"}
        last_error: str = ""
        last_exception: Exception | None = None

        for attempt in range(2):
            prompt_user = user
            if attempt == 1 and last_error:
                prompt_user = user + f"\n\nPREVIOUS VALIDATION ERROR (Fix your JSON output to strictly match schema):\n{last_error}"

            payload = {
                "systemInstruction": {"parts": [{"text": system}]},
                "contents": [{"role": "user", "parts": [{"text": prompt_user}]}],
                "generationConfig": {
                    "temperature": 0.0,
                    "response_mime_type": "application/json",
                },
            }

            data = None
            # Try primary and fallback models
            for model_name in models_to_try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={self.api_key}"
                
                # Up to 2 retries per model with backoff
                for retry_i in range(2):
                    async with httpx.AsyncClient(timeout=120) as client:
                        try:
                            resp = await client.post(url, headers=headers, json=payload)
                            if resp.status_code in (503, 429):
                                backoff = 2.0 * (retry_i + 1)
                                print(f"[LLM] Model '{model_name}' busy (HTTP {resp.status_code}). Backing off {backoff}s...", flush=True)
                                await asyncio.sleep(backoff)
                                continue
                            resp.raise_for_status()
                            data = resp.json()
                            break
                        except httpx.HTTPStatusError as e:
                            last_exception = e
                            if e.response.status_code in (503, 429):
                                print(f"[LLM] Model '{model_name}' returned {e.response.status_code}. Switching model...", flush=True)
                                break
                            raise LLMOutputError(f"Gemini API error (HTTP {e.response.status_code}): {e.response.text}") from e
                        except Exception as e:
                            last_exception = e
                            await asyncio.sleep(1.5)
                            continue

                if data:
                    break

            if not data:
                raise LLMOutputError(f"All Gemini models temporarily unavailable (HTTP 503): {last_exception}")

            candidates = data.get("candidates", [])
            if not candidates:
                raise LLMOutputError(f"Gemini returned no candidates: {data}")

            raw = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
            try:
                clean = raw.strip()
                if clean.startswith("```"):
                    clean = re.sub(r"^```(?:json)?\n?", "", clean)
                    clean = re.sub(r"\n?```$", "", clean)
                parsed_json = json.loads(clean)
                return model_cls.model_validate(parsed_json)
            except (json.JSONDecodeError, ValidationError) as e:
                last_error = str(e)
                if attempt == 1:
                    raise LLMOutputError(
                        f"LLM output failed validation on retry 2. Error: {e}. Raw was: {raw[:500]}"
                    ) from e

        raise LLMOutputError("Exhausted LLM generation attempts")
