from __future__ import annotations
import os
from dataclasses import dataclass
from typing import Optional
import httpx

from app.config import settings


@dataclass
class SearchHit:
    url: str
    title: str
    snippet: str


class SearchProvider:
    async def search(self, query: str, k: int) -> list[SearchHit]:
        raise NotImplementedError


class NullProvider(SearchProvider):
    async def search(self, query: str, k: int) -> list[SearchHit]:
        return []


class TavilyProvider(SearchProvider):
    API_URL = "https://api.tavily.com/search"

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = (
            api_key
            or settings.tavily_api_key
            or settings.search_api_key
            or os.environ.get("TAVILY_API_KEY", "")
            or os.environ.get("SEARCH_API_KEY", "")
        )

    async def search(self, query: str, k: int) -> list[SearchHit]:
        if not self.api_key or k <= 0:
            return []
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "query": query,
            "search_depth": "basic",
            "max_results": k,
            "include_answer": False,
            "include_raw_content": False,
        }
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(self.API_URL, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
        hits = []
        for r in data.get("results", []):
            hits.append(SearchHit(
                url=r.get("url", ""),
                title=r.get("title", ""),
                snippet=r.get("content", ""),
            ))
        return hits


def get_search_provider() -> SearchProvider:
    provider = settings.search_provider.lower()
    has_tavily_key = bool(settings.tavily_api_key or os.environ.get("TAVILY_API_KEY"))
    if provider == "tavily" or has_tavily_key:
        return TavilyProvider()
    return NullProvider()
