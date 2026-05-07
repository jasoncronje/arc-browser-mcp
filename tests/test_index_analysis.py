from __future__ import annotations

# ruff: noqa: E402, I001

import sys
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

from arc_browser_mcp.index import ArcIndexCache

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tests.test_index_query import FakeHistoryStore, FakeStateStore


REQUIRED_GROUP_FIELDS = {
    "analysis_type",
    "group_id",
    "reason",
    "confidence",
    "tab_ids",
    "suggested_action",
}


def index_with_tabs(*tabs):
    store = FakeStateStore()
    snapshot = store.load()
    snapshot = replace(snapshot, tabs=list(tabs))
    store.load = lambda include_recovery=False: snapshot
    return ArcIndexCache(
        state_store=store,
        history_store=FakeHistoryStore(),
    ).get()


def index_with_recovery_candidates(recovery_candidates):
    store = FakeStateStore()
    snapshot = store.load()
    snapshot = replace(snapshot, recovery_candidates=recovery_candidates)
    store.load = lambda include_recovery=False: snapshot
    return ArcIndexCache(
        state_store=store,
        history_store=FakeHistoryStore(),
    ).get()


def test_analyze_tabs_groups_missing_urls() -> None:
    snapshot = FakeStateStore().load()
    tab_1, tab_2 = snapshot.tabs
    index = index_with_tabs(tab_1, replace(tab_2, is_missing_url=True))

    result = index.analyze_tabs(analyses=["missing_url"])

    assert result["groups"][0]["analysis_type"] == "missing_url"
    assert REQUIRED_GROUP_FIELDS <= result["groups"][0].keys()
    assert result["groups"][0]["group_id"] == "missing_url:all"
    assert "current Arc state without saved URLs" in result["groups"][0]["reason"]
    assert result["groups"][0]["confidence"] == "high"
    assert result["groups"][0]["tab_ids"] == ["tab-2"]
    assert "Informational only" in result["groups"][0]["suggested_action"]
    assert result["groups"][0]["evidence"]["tabs"][0]["id"] == "tab-2"


def test_analyze_tabs_groups_junk_tabs() -> None:
    snapshot = FakeStateStore().load()
    tab_1, tab_2 = snapshot.tabs
    index = index_with_tabs(
        tab_1,
        replace(
            tab_2,
            url="chrome://settings",
            domain=None,
        ),
    )

    result = index.analyze_tabs(analyses=["junk"])

    assert result["groups"][0]["analysis_type"] == "junk"
    assert REQUIRED_GROUP_FIELDS <= result["groups"][0].keys()
    assert result["groups"][0]["group_id"] == "junk:heuristic"
    assert result["groups"][0]["reason"]
    assert result["groups"][0]["confidence"] == "low"
    assert result["groups"][0]["tab_ids"] == ["tab-2"]
    assert "Informational only" in result["groups"][0]["suggested_action"]
    assert result["groups"][0]["evidence"]["tabs"][0]["id"] == "tab-2"


def test_analyze_tabs_groups_missing_url_recovery_candidates() -> None:
    index = index_with_recovery_candidates(
        {"tab-2": [{"url": "https://example.com/recovered"}]}
    )

    result = index.analyze_tabs(analyses=["missing_url_recovery"])

    assert result["groups"][0]["analysis_type"] == "missing_url_recovery"
    assert REQUIRED_GROUP_FIELDS <= result["groups"][0].keys()
    assert result["groups"][0]["group_id"] == "missing_url_recovery:tab-2"
    assert result["groups"][0]["reason"]
    assert result["groups"][0]["confidence"] == "medium"
    assert result["groups"][0]["tab_ids"] == ["tab-2"]
    assert "Informational only" in result["groups"][0]["suggested_action"]
    assert result["groups"][0]["evidence"]["candidates"] == [
        {"url": "https://example.com/recovered"}
    ]


def test_analyze_tabs_groups_duplicates() -> None:
    snapshot = FakeStateStore().load()
    tab_1, tab_2 = snapshot.tabs
    index = index_with_tabs(
        tab_1,
        replace(tab_2, duplicate_key=tab_1.duplicate_key),
    )

    result = index.analyze_tabs(analyses=["duplicates"])

    assert result["groups"][0]["analysis_type"] == "duplicates"
    assert REQUIRED_GROUP_FIELDS <= result["groups"][0].keys()
    assert result["groups"][0]["group_id"] == f"duplicate:{tab_1.duplicate_key}"
    assert result["groups"][0]["reason"] == (
        "Multiple active tabs share the same normalized URL."
    )
    assert result["groups"][0]["confidence"] == "high"
    assert set(result["groups"][0]["tab_ids"]) == {"tab-1", "tab-2"}
    assert result["groups"][0]["recommended_keep_tab_id"] == "tab-1"
    assert "Informational only" in result["groups"][0]["suggested_action"]
    assert {tab["id"] for tab in result["groups"][0]["evidence"]["tabs"]} == {
        "tab-1",
        "tab-2",
    }


def test_analyze_tabs_groups_stale_tabs_before_threshold() -> None:
    snapshot = FakeStateStore().load()
    tab_1, tab_2 = snapshot.tabs
    index = index_with_tabs(
        tab_1,
        replace(tab_2, last_active_at=datetime(2026, 4, 30, tzinfo=UTC)),
    )

    result = index.analyze_tabs(
        analyses=["stale"],
        stale_before=datetime(2026, 5, 1, tzinfo=UTC),
    )

    assert result["groups"][0]["analysis_type"] == "stale"
    assert REQUIRED_GROUP_FIELDS <= result["groups"][0].keys()
    assert result["groups"][0]["group_id"] == "stale:before:2026-05-01T00:00:00+00:00"
    assert "no known activity after 2026-05-01T00:00:00+00:00" in result["groups"][0][
        "reason"
    ]
    assert result["groups"][0]["confidence"] == "medium"
    assert result["groups"][0]["tab_ids"] == ["tab-2"]
    assert "Informational only" in result["groups"][0]["suggested_action"]
    assert result["groups"][0]["evidence"]["tabs"][0]["id"] == "tab-2"
