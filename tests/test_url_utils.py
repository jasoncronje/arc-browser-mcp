from datetime import UTC, datetime

from arc_browser_mcp.url_utils import (
    chrome_time_to_datetime,
    duplicate_key_for_url,
    extract_domain,
    normalize_text,
)


def test_extract_domain_strips_common_prefixes() -> None:
    assert extract_domain("https://www.example.com/path?q=1") == "example.com"
    assert extract_domain("https://docs.python.org/3/library/sqlite3.html") == "docs.python.org"
    assert extract_domain("") is None


def test_duplicate_key_ignores_fragments_and_common_tracking_params() -> None:
    left = "https://example.com/page?utm_source=x&id=123#section"
    right = "https://example.com/page?id=123"

    assert duplicate_key_for_url(left) == duplicate_key_for_url(right)


def test_normalize_text_compacts_case_and_whitespace() -> None:
    assert normalize_text("  Hello\nWorld  ") == "hello world"


def test_chrome_time_to_datetime_converts_microseconds_since_1601() -> None:
    result = chrome_time_to_datetime(13217451500000000)

    assert isinstance(result, datetime)
    assert result.tzinfo == UTC
