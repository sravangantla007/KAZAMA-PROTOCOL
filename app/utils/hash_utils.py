from __future__ import annotations
import hashlib
from app.utils.text_utils import normalize_text


def sha256_of_text(text: str) -> str:
    normalized = normalize_text(text)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()
