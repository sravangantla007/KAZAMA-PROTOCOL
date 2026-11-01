from __future__ import annotations
import base64
import io
from pathlib import Path
from typing import Optional
import chardet

from app.contracts.raw import IngestionIssue
from app.config import settings

_PDF_MAGIC = b"%PDF-"


def _is_pdf(data: bytes, extension: str) -> bool:
    return extension.lower() == ".pdf" or data[:5] == _PDF_MAGIC


def parse_file(
    filename: str,
    content_base64: str,
    mime_type: Optional[str] = None,
) -> tuple[Optional[str], list[IngestionIssue]]:
    """
    Returns (extracted_text, issues). Text is None on fatal parse failure.
    """
    issues: list[IngestionIssue] = []
    sanitized = Path(filename).name  # strip paths

    try:
        data = base64.b64decode(content_base64)
    except Exception:
        issues.append(IngestionIssue(target=sanitized, code="PARSE_FAILED", message="Invalid base64", fatal=True))
        return None, issues

    if len(data) > settings.max_file_bytes:
        issues.append(IngestionIssue(target=sanitized, code="FILE_TOO_LARGE",
                                      message=f"File exceeds {settings.max_file_bytes} bytes", fatal=True))
        return None, issues

    ext = Path(sanitized).suffix.lower()
    if _is_pdf(data, ext):
        return _parse_pdf(sanitized, data, issues)
    elif ext == ".txt":
        return _parse_txt(sanitized, data, issues)
    else:
        issues.append(IngestionIssue(target=sanitized, code="UNSUPPORTED_TYPE",
                                      message=f"Unsupported file type: '{ext}'", fatal=True))
        return None, issues


def _parse_txt(filename: str, data: bytes, issues: list[IngestionIssue]) -> tuple[Optional[str], list[IngestionIssue]]:
    for encoding in ("utf-8", None, "latin-1"):
        try:
            if encoding is None:
                detected = chardet.detect(data)
                encoding = detected.get("encoding") or "utf-8"
            text = data.decode(encoding)
            return text, issues
        except (UnicodeDecodeError, LookupError):
            continue
    issues.append(IngestionIssue(target=filename, code="PARSE_FAILED", message="Could not decode text file"))
    return None, issues


def _parse_pdf(filename: str, data: bytes, issues: list[IngestionIssue]) -> tuple[Optional[str], list[IngestionIssue]]:
    text = _parse_pdf_pdfplumber(data)
    if text is None:
        text = _parse_pdf_pypdf(data)
    if text is None or len(text.strip()) < 50:
        issues.append(IngestionIssue(target=filename, code="SCANNED_PDF_NO_TEXT",
                                      message="PDF appears to be scanned or contains no extractable text"))
        return None, issues
    return text, issues


def _parse_pdf_pdfplumber(data: bytes) -> Optional[str]:
    try:
        import pdfplumber
        pages = []
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            for page in pdf.pages[:50]:
                t = page.extract_text()
                if t:
                    pages.append(t)
        return "\n".join(pages) if pages else None
    except Exception:
        return None


def _parse_pdf_pypdf(data: bytes) -> Optional[str]:
    try:
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(data))
        pages = []
        for page in reader.pages[:50]:
            t = page.extract_text()
            if t:
                pages.append(t)
        return "\n".join(pages) if pages else None
    except Exception:
        return None
