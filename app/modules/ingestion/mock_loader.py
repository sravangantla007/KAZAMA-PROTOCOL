from __future__ import annotations
import json
from pathlib import Path

from app.contracts.raw import IngestionResult, RawSource
from app.utils.hash_utils import sha256_of_text

MOCK_DATA_DIR = Path(__file__).parent.parent.parent.parent / "data" / "mock"


def load_mock_scenario(scenario: str = "scholarship_scenario") -> IngestionResult:
    path = MOCK_DATA_DIR / f"{scenario}.json"
    if not path.exists():
        raise FileNotFoundError(f"Mock scenario not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    result = IngestionResult.model_validate(data)
    # Compute content_hash for each source (needed by downstream modules)
    enriched = []
    for src in result.sources:
        h = sha256_of_text(src.text)
        enriched.append(src.model_copy(update={"content_hash": h, "char_count": len(src.text)}))
    return IngestionResult(query=result.query, mode=result.mode, sources=enriched, issues=result.issues)
