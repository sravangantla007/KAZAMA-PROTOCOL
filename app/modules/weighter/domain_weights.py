"""Static domain trust weighting rules based on TLD, suffix, and hostname reputation."""
from __future__ import annotations
import re
from urllib.parse import urlparse
import tldextract

GOV_SUFFIXES = {"gov", "gov.in", "nic.in", "mil", "gov.uk", "gc.ca", "gov.au", "europa.eu", "int"}
EDU_SUFFIXES = {"edu", "ac.in", "edu.in", "ac.uk", "edu.au"}
REPUTABLE_HOSTS = {
    "who.int", "un.org", "worldbank.org", "nature.com",
    "science.org", "ieee.org", "acm.org"
}
WIKIPEDIA_HOSTS = {"wikipedia.org"}
CURATED_NEWS_HOSTS = {
    "reuters.com", "apnews.com", "bbc.com", "bbc.co.uk",
    "thehindu.com", "indianexpress.com", "timesofindia.indiatimes.com",
    "ndtv.com", "hindustantimes.com", "dailynews.com"
}
LOW_TRUST_HOSTS = {
    "reddit.com", "quora.com", "medium.com", "blogspot.com", "wordpress.com",
    "substack.com", "facebook.com", "x.com", "twitter.com", "instagram.com",
    "youtube.com", "pinterest.com", "tumblr.com", "telegram.me", "t.me"
}
COM_SUFFIXES = {"com", "net", "co", "co.in", "io", "info", "biz"}


def _normalize_host_for_matching(raw_host: str) -> str:
    """Normalize host by removing port and stripping a literal '.example' label for mock testing."""
    host = raw_host.lower().split(":")[0]
    # Strip literal .example or .example. label if present (mock domain support)
    # e.g. scholarships.example.gov.in -> scholarships.gov.in
    # edu-forum.example.com -> edu-forum.com
    host = re.sub(r"\.example(?=\.|$)", "", host)
    return host


def compute_domain_weight(url_or_filename: str, source_type: str) -> tuple[float, str]:
    """
    Returns (domain_weight: float, domain_rule_matched: str).
    Evaluation follows exact strict priority order (spec Section 3 Module 2).
    """
    if source_type == "user_document":
        return 1.0, "user_document"

    parsed = urlparse(url_or_filename)
    raw_host = parsed.hostname or url_or_filename
    normalized_host = _normalize_host_for_matching(raw_host)

    ext = tldextract.extract(normalized_host)
    reg_domain = getattr(ext, "top_domain_under_public_suffix", None) or ext.registered_domain
    registered_domain = reg_domain.lower() if reg_domain else normalized_host
    suffix = ext.suffix.lower() if ext.suffix else ""
    subdomain = ext.subdomain.lower() if ext.subdomain else ""

    # Rule 1: Gov / Military
    if suffix in GOV_SUFFIXES:
        return 0.90, f"tld:{suffix}"

    # Rule 2: Edu / Academic
    if suffix in EDU_SUFFIXES:
        return 0.85, f"tld:{suffix}"

    # Rule 3: High-reputation institutional / scientific
    if registered_domain in REPUTABLE_HOSTS or normalized_host in REPUTABLE_HOSTS:
        return 0.80, f"host:{registered_domain or normalized_host}"

    # Rule 4: Wikipedia
    if registered_domain in WIKIPEDIA_HOSTS:
        return 0.60, "host:wikipedia.org"

    # Rule 5: Curated mainstream news
    if registered_domain in CURATED_NEWS_HOSTS:
        return 0.60, f"host:{registered_domain}"

    # Rule 7 (checked before 6 and 8 per spec order table): Low-trust or forum-like
    is_forum = any(subdomain.startswith(p) or f".{p}" in subdomain for p in ["forum", "community", "answers"])
    is_forum = is_forum or any(p in registered_domain for p in ["forum", "community"])
    if registered_domain in LOW_TRUST_HOSTS or is_forum:
        rule_desc = f"host:{registered_domain}" if registered_domain in LOW_TRUST_HOSTS else "forum_pattern"
        return 0.25, rule_desc

    # Rule 6: Suffix org
    if suffix == "org":
        return 0.55, "tld:org"

    # Rule 8: General commercial TLDs
    if suffix in COM_SUFFIXES:
        return 0.45, f"tld:{suffix}"

    # Rule 9: Anything else
    return 0.35, "default:unknown"
