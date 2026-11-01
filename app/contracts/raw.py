from __future__ import annotations
from datetime import date, datetime
from typing import Literal, Optional
from pydantic import BaseModel, ConfigDict

from app.contracts.common import SourceType


class UploadedFile(BaseModel):
    model_config = ConfigDict(extra="forbid")
    filename: str
    mime_type: Optional[str] = None
    content_base64: str


class RawSource(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_id: str
    source_type: SourceType
    url_or_filename: str
    text: str
    published_date: Optional[date]
    title: Optional[str] = None
    date_origin: Optional[Literal[
        "meta_tag", "json_ld", "http_header", "pdf_metadata", "text_regex", "mock"
    ]] = None
    fetched_at: Optional[datetime] = None
    content_hash: Optional[str] = None
    truncated: bool = False
    char_count: int = 0


class IngestionIssue(BaseModel):
    model_config = ConfigDict(extra="forbid")
    target: str
    code: Literal[
        "FETCH_FAILED", "TIMEOUT", "BLOCKED_URL", "UNSUPPORTED_TYPE", "EMPTY_TEXT",
        "SCANNED_PDF_NO_TEXT", "FILE_TOO_LARGE", "PARSE_FAILED", "DUPLICATE",
        "FUTURE_DATE", "TRUNCATED"
    ]
    message: str
    fatal: bool = False


class IngestionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str
    mode: Literal["live", "mock"]
    sources: list[RawSource]
    issues: list[IngestionIssue] = []
