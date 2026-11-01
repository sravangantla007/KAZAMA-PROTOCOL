from __future__ import annotations
import asyncio
from datetime import datetime, timezone
from typing import Optional
import httpx
from bs4 import BeautifulSoup

try:
    import trafilatura
    HAS_TRAFILATURA = True
except ImportError:
    HAS_TRAFILATURA = False

from app.config import settings
from app.contracts.raw import RawSource, IngestionIssue
from app.utils.url_safety import is_safe_url
from app.modules.ingestion.date_extractor import (
    extract_date_from_json_ld, extract_date_from_meta,
    extract_date_from_http_header, extract_date_from_text_regex,
)
from app.utils.date_utils import is_future_date

UA = "DigitalDarkSpotBot/1.0"
_SEM = asyncio.Semaphore(5)

_BOT_CHALLENGE_PATTERNS = [
    "attention required! | cloudflare",
    "just a moment...",
    "enable javascript and cookies to continue",
    "checking your browser before accessing",
    "ddos protection by cloudflare",
    "security service to protect itself from online attacks",
    "please enable cookies",
    "ray id found at the bottom of this page",
]


def _is_bot_challenge(title: Optional[str], text: Optional[str]) -> bool:
    content = f"{title or ''} {text or ''}".lower()
    return any(p in content for p in _BOT_CHALLENGE_PATTERNS)


async def _fallback_extract_tavily(url: str) -> Optional[str]:
    """Attempt extracting content via Tavily's extract API when direct fetch is blocked."""
    api_key = settings.tavily_api_key or settings.search_api_key
    if not api_key:
        return None
    try:
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        payload = {"urls": [url]}
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post("https://api.tavily.com/extract", headers=headers, json=payload)
            if resp.status_code == 200:
                data = resp.json()
                results = data.get("results", [])
                if results and results[0].get("raw_content"):
                    return results[0]["raw_content"]
    except Exception:
        pass
    return None


async def fetch_url(
    url: str,
    source_id: str,
) -> tuple[Optional[RawSource], list[IngestionIssue]]:
    """Fetch a single URL. Returns (RawSource or None, issues)."""
    issues: list[IngestionIssue] = []

    safe, reason = is_safe_url(url)
    if not safe:
        issues.append(IngestionIssue(target=url, code="BLOCKED_URL", message=reason))
        return None, issues

    async with _SEM:
        try:
            async with httpx.AsyncClient(
                timeout=settings.fetch_timeout_s,
                follow_redirects=True,
                max_redirects=3,
                headers={"User-Agent": UA},
            ) as client:
                resp = await client.get(url)
        except httpx.TimeoutException:
            issues.append(IngestionIssue(target=url, code="TIMEOUT",
                                          message=f"Request timed out after {settings.fetch_timeout_s}s"))
            return None, issues
        except Exception as exc:
            issues.append(IngestionIssue(target=url, code="FETCH_FAILED", message=str(exc)))
            return None, issues

    # Re-check URL after redirects
    final_url = str(resp.url)
    if final_url != url:
        safe2, reason2 = is_safe_url(final_url)
        if not safe2:
            issues.append(IngestionIssue(target=url, code="BLOCKED_URL",
                                          message=f"Redirect target blocked: {reason2}"))
            return None, issues

    # Check for HTTP status error (e.g. 403 Forbidden, 429, 503)
    if resp.status_code >= 400:
        fallback_text = await _fallback_extract_tavily(url)
        if fallback_text and not _is_bot_challenge(None, fallback_text):
            issues.append(IngestionIssue(
                target=url,
                code="FETCH_FAILED",
                message=f"HTTP {resp.status_code} on direct fetch; content recovered via Tavily fallback",
                fatal=False,
            ))
            return RawSource(
                source_id=source_id,
                source_type="web",
                url_or_filename=final_url,
                text=fallback_text,
                published_date=None,
                fetched_at=datetime.now(timezone.utc),
                char_count=len(fallback_text),
            ), issues
        else:
            issues.append(IngestionIssue(target=url, code="FETCH_FAILED", message=f"HTTP {resp.status_code}"))
            return None, issues

    content_type = resp.headers.get("content-type", "")
    if "pdf" in content_type or url.lower().endswith(".pdf"):
        from app.modules.ingestion.file_parser import _parse_pdf
        raw_bytes = resp.content[:settings.max_page_bytes]
        text, pdf_issues = _parse_pdf(url, raw_bytes, [])
        issues.extend(pdf_issues)
        if not text:
            return None, issues
        src = RawSource(
            source_id=source_id,
            source_type="web",
            url_or_filename=url,
            text=text,
            published_date=None,
            fetched_at=datetime.now(timezone.utc),
        )
        return src, issues

    if "text/html" not in content_type and "text/plain" not in content_type:
        issues.append(IngestionIssue(target=url, code="UNSUPPORTED_TYPE",
                                      message=f"Content-Type not supported: {content_type}"))
        return None, issues

    raw_bytes = resp.content[:settings.max_page_bytes]
    html = raw_bytes.decode("utf-8", errors="replace")

    # Extract text
    text = None
    title = None
    if HAS_TRAFILATURA:
        text = trafilatura.extract(html)
    if not text:
        soup = BeautifulSoup(html, "html.parser")
        text = soup.get_text(separator=" ", strip=True)
        title_tag = soup.find("title")
        if title_tag:
            title = title_tag.get_text(strip=True)

    if not text:
        issues.append(IngestionIssue(target=url, code="EMPTY_TEXT", message="No text extracted"))
        return None, issues

    # Detect Cloudflare / DDoS / bot-challenge pages
    if _is_bot_challenge(title, text):
        fallback_text = await _fallback_extract_tavily(url)
        if fallback_text and not _is_bot_challenge(None, fallback_text):
            issues.append(IngestionIssue(
                target=url,
                code="FETCH_FAILED",
                message="Direct fetch hit bot challenge; content recovered via Tavily fallback",
                fatal=False,
            ))
            text = fallback_text
            title = None
        else:
            issues.append(IngestionIssue(
                target=url,
                code="FETCH_FAILED",
                message="Blocked by anti-bot challenge (Cloudflare/JS challenge)",
                fatal=False,
            ))
            return None, issues

    # Date extraction cascade
    published_date = None
    date_origin = None

    # 1. JSON-LD
    try:
        import json
        soup2 = BeautifulSoup(html, "html.parser")
        json_ld_tags = soup2.find_all("script", type="application/ld+json")
        json_ld_objects = []
        for tag in json_ld_tags:
            try:
                obj = json.loads(tag.string or "")
                if isinstance(obj, list):
                    json_ld_objects.extend(obj)
                else:
                    json_ld_objects.append(obj)
            except Exception:
                pass
        result = extract_date_from_json_ld(json_ld_objects)
        if result:
            published_date, date_origin = result
    except Exception:
        pass

    # 2. Meta tags
    if not published_date:
        try:
            soup3 = BeautifulSoup(html, "html.parser")
            meta_dict: dict[str, str] = {}
            for tag in soup3.find_all("meta"):
                name = tag.get("name") or tag.get("property") or ""
                content = tag.get("content", "")
                if name and content:
                    meta_dict[name.lower()] = content
            result = extract_date_from_meta(meta_dict)
            if result:
                published_date, date_origin = result
        except Exception:
            pass

    # 3. HTTP Last-Modified
    if not published_date:
        result = extract_date_from_http_header(dict(resp.headers))
        if result:
            published_date, date_origin = result

    # 4. Text regex
    if not published_date:
        result = extract_date_from_text_regex(text)
        if result:
            published_date, date_origin = result

    # Future date guard
    if published_date and is_future_date(published_date):
        issues.append(IngestionIssue(target=url, code="FUTURE_DATE",
                                      message=f"Published date {published_date} is in the future; nullified"))
        published_date = None
        date_origin = None

    src = RawSource(
        source_id=source_id,
        source_type="web",
        url_or_filename=final_url,
        text=text,
        published_date=published_date,
        title=title,
        date_origin=date_origin,
        fetched_at=datetime.now(timezone.utc),
        char_count=len(text),
    )
    return src, issues
