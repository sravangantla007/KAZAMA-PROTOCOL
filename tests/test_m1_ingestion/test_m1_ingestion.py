"""Module 1 acceptance tests — all offline, no live network."""
from __future__ import annotations
import asyncio
import base64
import io
import json
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock

import pytest
import respx
import httpx

from app.contracts.raw import RawSource, IngestionResult
from app.modules.ingestion import ingest
from app.modules.ingestion.mock_loader import load_mock_scenario
from app.modules.ingestion.file_parser import parse_file
from app.modules.ingestion.date_extractor import (
    extract_date_from_json_ld,
    extract_date_from_meta,
    extract_date_from_http_header,
    extract_date_from_text_regex,
)
from app.utils.url_safety import is_safe_url

FIXTURES = Path(__file__).parent.parent / "fixtures"


# ── Mock mode ────────────────────────────────────────────────────────────────

def test_mock_mode_returns_six_valid_sources():
    result = load_mock_scenario("scholarship_scenario")
    assert result.mode == "mock"
    assert len(result.sources) == 6
    ids = [s.source_id for s in result.sources]
    assert ids == ["S1", "S2", "S3", "S4", "S5", "S6"]
    for src in result.sources:
        RawSource.model_validate(src.model_dump())


@pytest.mark.asyncio
async def test_mock_mode_via_ingest():
    result = await ingest(query="test", urls=[], files=[], mock_mode=True)
    assert result.mode == "mock"
    assert len(result.sources) == 6


# ── File parsing ─────────────────────────────────────────────────────────────

def test_txt_parsing_utf8():
    text = "Hello, this is a test file with enough content to pass validation easily."
    b64 = base64.b64encode(text.encode("utf-8")).decode()
    result, issues = parse_file("test.txt", b64)
    assert result is not None
    assert "Hello" in result
    assert not any(i.fatal for i in issues)


def test_txt_parsing_latin1():
    text = "Caf\xe9 and na\xefve content with enough text to pass minimum length check here."
    b64 = base64.b64encode(text.encode("latin-1")).decode()
    result, issues = parse_file("test.txt", b64)
    assert result is not None
    assert len(result) > 0


def test_pdf_parsing_text_pdf():
    """Generate a minimal text PDF in-memory using reportlab."""
    try:
        from reportlab.pdfgen import canvas
        from reportlab.lib.pagesizes import letter
    except ImportError:
        pytest.skip("reportlab not installed")

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    c.drawString(100, 750, "This is a test PDF document for the Digital Dark Spot project.")
    c.drawString(100, 730, "It contains enough text to pass the minimum character threshold.")
    c.save()
    buf.seek(0)
    pdf_bytes = buf.read()
    b64 = base64.b64encode(pdf_bytes).decode()
    result, issues = parse_file("test.pdf", b64)
    assert result is not None
    assert len(result.strip()) >= 50
    assert not any(i.code == "SCANNED_PDF_NO_TEXT" for i in issues)


def test_pdf_scanned_returns_issue():
    """A PDF with no extractable text should return SCANNED_PDF_NO_TEXT."""
    try:
        from reportlab.pdfgen import canvas
        from reportlab.lib.pagesizes import letter
    except ImportError:
        pytest.skip("reportlab not installed")

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    # Don't write any text — simulates a scanned PDF
    c.save()
    buf.seek(0)
    b64 = base64.b64encode(buf.read()).decode()
    result, issues = parse_file("scanned.pdf", b64)
    assert result is None
    assert any(i.code == "SCANNED_PDF_NO_TEXT" for i in issues)


def test_unsupported_extension_rejected():
    b64 = base64.b64encode(b"some content").decode()
    result, issues = parse_file("document.docx", b64)
    assert result is None
    assert any(i.code == "UNSUPPORTED_TYPE" for i in issues)


def test_file_too_large_rejected(monkeypatch):
    monkeypatch.setattr("app.modules.ingestion.file_parser.settings.max_file_bytes", 10)
    b64 = base64.b64encode(b"x" * 100).decode()
    result, issues = parse_file("big.txt", b64)
    assert result is None
    assert any(i.code == "FILE_TOO_LARGE" for i in issues)


# ── Web fetch ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_web_fetch_happy_path():
    sample_html = """<html><head><title>Test Page</title></head>
    <body><p>This is a well-formed test article with plenty of content.
    It discusses important topics related to scholarships and eligibility criteria.
    The content is long enough to pass the minimum text length validation check.</p></body></html>"""

    with respx.mock:
        respx.get("https://example-test.com/page").mock(
            return_value=httpx.Response(200, text=sample_html,
                                        headers={"content-type": "text/html"})
        )
        from app.modules.ingestion.fetcher import fetch_url
        src, issues = await fetch_url("https://example-test.com/page", "S1")
    assert src is not None
    assert src.source_type == "web"
    assert len(src.text) >= 50


@pytest.mark.asyncio
async def test_timeout_produces_issue_not_exception():
    with respx.mock:
        respx.get("https://slow-site.example.com/").mock(side_effect=httpx.TimeoutException("timeout"))
        from app.modules.ingestion.fetcher import fetch_url
        src, issues = await fetch_url("https://slow-site.example.com/", "S1")
    assert src is None
    assert any(i.code == "TIMEOUT" for i in issues)


@pytest.mark.asyncio
async def test_http_error_produces_fetch_failed_issue():
    with respx.mock:
        respx.get("https://example-test.com/forbidden").mock(
            return_value=httpx.Response(403, text="Forbidden access", headers={"content-type": "text/html"})
        )
        from app.modules.ingestion.fetcher import fetch_url
        src, issues = await fetch_url("https://example-test.com/forbidden", "S1")
    assert src is None
    assert any(i.code == "FETCH_FAILED" and "403" in i.message for i in issues)


@pytest.mark.asyncio
async def test_bot_challenge_detected_as_fetch_failed():
    challenge_html = "<html><head><title>Just a moment...</title></head><body>Enable JavaScript and cookies to continue with Cloudflare protection.</body></html>"
    with respx.mock:
        respx.get("https://example-test.com/challenge").mock(
            return_value=httpx.Response(200, text=challenge_html, headers={"content-type": "text/html"})
        )
        from app.modules.ingestion.fetcher import fetch_url
        src, issues = await fetch_url("https://example-test.com/challenge", "S1")
    assert src is None
    assert any(i.code == "FETCH_FAILED" and "anti-bot" in i.message.lower() for i in issues)


# ── SSRF blocklist ────────────────────────────────────────────────────────────

def test_ssrf_blocklist():
    assert is_safe_url("http://localhost/evil")[0] is False
    assert is_safe_url("http://127.0.0.1/admin")[0] is False
    assert is_safe_url("http://10.0.0.1/internal")[0] is False
    assert is_safe_url("http://169.254.169.254/latest/meta-data/")[0] is False
    assert is_safe_url("file:///etc/passwd")[0] is False
    assert is_safe_url("https://example.com/safe")[0] is True


# ── Date extraction ───────────────────────────────────────────────────────────

def test_date_extraction_json_ld():
    json_ld = [{"@type": "Article", "datePublished": "2025-03-15"}]
    result = extract_date_from_json_ld(json_ld)
    assert result is not None
    assert result[0] == date(2025, 3, 15)
    assert result[1] == "json_ld"


def test_date_extraction_meta_tag():
    meta = {"article:published_time": "2025-06-01"}
    result = extract_date_from_meta(meta)
    assert result is not None
    assert result[0] == date(2025, 6, 1)
    assert result[1] == "meta_tag"


def test_date_extraction_http_header():
    headers = {"Last-Modified": "2024-11-20"}
    result = extract_date_from_http_header(headers)
    assert result is not None
    assert result[0] == date(2024, 11, 20)
    assert result[1] == "http_header"


def test_date_extraction_text_regex():
    text = "Last updated: 2024-09-01. This page contains scholarship information."
    result = extract_date_from_text_regex(text)
    assert result is not None
    assert result[0] == date(2024, 9, 1)
    assert result[1] == "text_regex"


def test_date_extraction_none():
    text = "This text has no date information at all."
    result = extract_date_from_text_regex(text)
    assert result is None


# ── Dedup, truncation, future date ───────────────────────────────────────────

def test_dedup_by_hash():
    from app.utils.hash_utils import sha256_of_text
    text = "Some unique content that will be hashed for dedup testing purposes here."
    h1 = sha256_of_text(text)
    h2 = sha256_of_text(text)
    assert h1 == h2


def test_truncation_flag():
    from app.utils.text_utils import truncate_to_chars
    long_text = "word " * 5000
    truncated, was_truncated = truncate_to_chars(long_text, 100)
    assert was_truncated is True
    assert len(truncated) <= 100


def test_future_date_nullified():
    from app.utils.date_utils import is_future_date
    from datetime import date, timedelta
    future = date.today() + timedelta(days=30)
    assert is_future_date(future) is True
    past = date(2020, 1, 1)
    assert is_future_date(past) is False


# ── Golden fixture ────────────────────────────────────────────────────────────

def test_write_golden_fixture():
    """Write tests/fixtures/m1_output.json from mock scenario."""
    result = load_mock_scenario("scholarship_scenario")
    FIXTURES.mkdir(parents=True, exist_ok=True)
    out_path = FIXTURES / "m1_output.json"
    out_path.write_text(result.model_dump_json(indent=2), encoding="utf-8")
    assert out_path.exists()
    # Verify it can be re-loaded
    reloaded = IngestionResult.model_validate_json(out_path.read_text())
    assert len(reloaded.sources) == 6
