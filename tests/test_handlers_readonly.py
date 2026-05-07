from datetime import UTC, datetime

from arc_browser_mcp.handlers import (
    handle_analyze_tabs,
    handle_get_overview,
    handle_get_sidebar_tree,
    handle_get_tab,
    handle_query_tabs,
    handle_search_history,
)


class FakeIndex:
    def __init__(self):
        self.analyze_calls = []

    def overview(self, **kwargs):
        return {"totals": {"tabs": 2}}

    def query_tabs(self, **kwargs):
        return {"total": 1, "items": [{"id": "tab-1"}], "cursor": None}

    def get_tab(self, tab_id, **kwargs):
        return {"id": tab_id}

    def sidebar_tree(self, **kwargs):
        return {"spaces": []}

    def analyze_tabs(self, **kwargs):
        self.analyze_calls.append(kwargs)
        return {"groups": []}


class FakeIndexCache:
    def __init__(self):
        self.index = FakeIndex()

    def get(self, **kwargs):
        return self.index


class FakeHistoryStore:
    def search(self, **kwargs):
        return []


class FakePaginatedHistoryStore:
    def __init__(self):
        self.calls = []

    def search(self, **kwargs):
        self.calls.append(kwargs)
        return [{"id": f"history-{index}"} for index in range(kwargs["limit"])]


def test_v2_read_handlers_delegate_to_index() -> None:
    cache = FakeIndexCache()

    assert handle_get_overview(cache)["totals"]["tabs"] == 2
    assert handle_query_tabs(cache, query="python")["items"][0]["id"] == "tab-1"
    assert handle_get_tab(cache, tab_id="tab-1")["id"] == "tab-1"
    assert handle_get_sidebar_tree(cache)["spaces"] == []
    assert handle_analyze_tabs(cache, analyses=["duplicates"])["groups"] == []


def test_handle_analyze_tabs_treats_naive_stale_threshold_as_utc() -> None:
    cache = FakeIndexCache()

    assert handle_analyze_tabs(
        cache,
        analyses=["stale"],
        stale_before="2026-05-01T00:00:00",
    ) == {"groups": []}
    assert cache.index.analyze_calls == [
        {
            "analyses": ["stale"],
            "stale_before": datetime(2026, 5, 1, tzinfo=UTC),
        }
    ]


def test_handle_search_history_serializes_history_rows() -> None:
    result = handle_search_history(FakeHistoryStore(), query="python")

    assert result == {"total": 0, "cursor": None, "items": []}


def test_handle_search_history_fetches_extra_row_to_detect_next_page() -> None:
    history_store = FakePaginatedHistoryStore()

    result = handle_search_history(history_store, query="python", limit=2)

    assert history_store.calls == [{"limit": 3, "query": "python"}]
    assert result == {
        "total": 3,
        "cursor": "2",
        "items": [{"id": "history-0"}, {"id": "history-1"}],
    }
