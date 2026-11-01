from __future__ import annotations
import json
from pathlib import Path
from typing import Type, TypeVar
from pydantic import BaseModel

from app.llm.client import LLMClient
from app.errors import LLMOutputError

T = TypeVar("T", bound=BaseModel)

FIXTURES_DIR = Path(__file__).parent.parent.parent / "tests" / "fixtures" / "llm"


class MockLLMClient(LLMClient):
    """Replays JSON fixtures from tests/fixtures/llm/<purpose>.json."""

    def __init__(self, fixtures_dir: Path = FIXTURES_DIR):
        self.fixtures_dir = fixtures_dir

    async def generate_json(self, system: str, user: str, model_cls: Type[T], purpose: str = "synthesis") -> T:
        fixture_path = self.fixtures_dir / f"{purpose}_response.json"
        if not fixture_path.exists():
            raise LLMOutputError(f"Mock fixture not found: {fixture_path}")
        raw = fixture_path.read_text(encoding="utf-8")
        try:
            data = json.loads(raw)
            return model_cls.model_validate(data)
        except Exception as exc:
            raise LLMOutputError(f"Mock fixture parse failed: {exc}") from exc
