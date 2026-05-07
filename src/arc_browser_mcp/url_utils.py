from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

CHROME_EPOCH = datetime(1601, 1, 1, tzinfo=UTC)
APPLE_EPOCH = datetime(2001, 1, 1, tzinfo=UTC)
TRACKING_PARAMS = {
    "fbclid",
    "gclid",
    "igshid",
    "mc_cid",
    "mc_eid",
    "utm_campaign",
    "utm_content",
    "utm_medium",
    "utm_source",
    "utm_term",
}


def normalize_text(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "").replace("\u00a0", " ")).strip().lower()


def extract_domain(url: str | None) -> str | None:
    if not url:
        return None
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    return host or None


def duplicate_key_for_url(url: str | None) -> str | None:
    if not url:
        return None
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        return None
    query = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if key.lower() not in TRACKING_PARAMS
    ]
    normalized_query = urlencode(sorted(query), doseq=True)
    normalized = parsed._replace(
        scheme=parsed.scheme.lower(),
        netloc=parsed.netloc.lower(),
        query=normalized_query,
        fragment="",
    )
    return urlunparse(normalized).rstrip("/")


def chrome_time_to_datetime(value: int | None) -> datetime | None:
    if not value:
        return None
    return CHROME_EPOCH + timedelta(microseconds=int(value))


def apple_time_to_datetime(value: float | int | None) -> datetime | None:
    if value is None:
        return None
    return APPLE_EPOCH + timedelta(seconds=float(value))
