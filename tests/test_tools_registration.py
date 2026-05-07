import asyncio
from datetime import UTC, datetime

import pytest
from fastmcp import FastMCP

from arc_browser_mcp.errors import ArcBrowserMCPError
from arc_browser_mcp.handlers import handle_close_tabs
from arc_browser_mcp.tools import register_tools


def run(coro):
    return asyncio.run(coro)


class FakeIndex:
    def __init__(self):
        self.analyze_calls = []

    def overview(self, **kwargs):
        return {"totals": {"tabs": 2}}

    def query_tabs(self, **kwargs):
        return {"total": 1, "cursor": None, "items": [{"id": "tab-1"}]}

    def get_tab(self, tab_id, **kwargs):
        return {"id": tab_id}

    def sidebar_tree(self, **kwargs):
        return {"spaces": []}

    def analyze_tabs(self, **kwargs):
        self.analyze_calls.append(kwargs)
        return {"total": 0, "groups": []}


class FakeIndexCache:
    def __init__(self):
        self.calls = []
        self.index = FakeIndex()

    def get(self, **kwargs):
        self.calls.append(("get", kwargs))
        return self.index


class FakeHistoryStore:
    def search(self, **kwargs):
        return []


class FakeAdapter:
    def __init__(self):
        self.calls = []
        self.tab_reads = [
            [],
            [type("Tab", (), {"id": "new-tab", "url": "https://example.com/new"})()],
        ]

    def focus_space(self, space_id):
        self.calls.append(("focus_space", space_id))
        return {"space_id": space_id, "focused": True}

    def select_tab(self, tab_id):
        self.calls.append(("select_tab", tab_id))
        return {"tab_id": tab_id, "selected": True}

    def close_tab(self, tab_id):
        self.calls.append(("close_tab", tab_id))
        return {"tab_id": tab_id, "closed": True}

    def close_tabs(self, tab_ids, dry_run=False):
        self.calls.append(("close_tabs", tab_ids, dry_run))
        return {
            "results": [
                {"tab_id": tab_id, "closed": not dry_run} for tab_id in tab_ids
            ]
        }

    def open_url(self, url, tab_id=None):
        self.calls.append(("open_url", url, tab_id))
        return {"url": url, "tab_id": tab_id, "opened": True}

    def reload_tab(self, tab_id):
        self.calls.append(("reload_tab", tab_id))
        return {"tab_id": tab_id, "reloaded": True}

    def reload_tabs(self, tab_ids):
        self.calls.append(("reload_tabs", tab_ids))
        return {"results": [{"tab_id": tab_id, "reloaded": True} for tab_id in tab_ids]}

    def execute_javascript(self, tab_id, javascript):
        self.calls.append(("execute_javascript", tab_id, javascript))
        return {"tab_id": tab_id, "result": "Example"}

    def add_tab_to_space(self, space_id, url, window_id=None):
        self.calls.append(("add_tab_to_space", space_id, url, window_id))
        return {"space_id": space_id, "url": url, "created": True}

    def list_tabs(self, *, space_id=None, window_id=None):
        self.calls.append(("list_tabs", space_id, window_id))
        return self.tab_reads.pop(0)


class FakeBatchlessAdapter:
    def __init__(self):
        self.calls = []

    def close_tab(self, tab_id):
        self.calls.append(("close_tab", tab_id))
        return {"tab_id": tab_id, "closed": True}

    def reload_tab(self, tab_id):
        self.calls.append(("reload_tab", tab_id))
        return {"tab_id": tab_id, "reloaded": True}


def test_register_tools_adds_v2_compact_tools_to_fastmcp() -> None:
    mcp = FastMCP("test")

    register_tools(
        mcp,
        adapter=FakeAdapter(),
        index_cache=FakeIndexCache(),
        history_store=FakeHistoryStore(),
    )

    tool_names = {tool.name for tool in run(mcp.list_tools())}
    expected = {
        "arc_get_overview",
        "arc_query_tabs",
        "arc_get_tab",
        "arc_get_sidebar_tree",
        "arc_search_history",
        "arc_analyze_tabs",
        "arc_create_tab",
        "arc_focus_space",
        "arc_select_tab",
        "arc_open_url",
        "arc_reload_tabs",
        "arc_close_tabs",
        "arc_execute_javascript",
    }
    assert expected <= tool_names
    assert "arc_list_tabs" not in tool_names
    assert "arc_close_tab" not in tool_names


def test_tools_have_expected_annotations_in_fastmcp() -> None:
    mcp = FastMCP("test")

    register_tools(
        mcp,
        adapter=FakeAdapter(),
        index_cache=FakeIndexCache(),
        history_store=FakeHistoryStore(),
    )

    expected_annotations = {
        "arc_get_overview": (True, False, True),
        "arc_query_tabs": (True, False, True),
        "arc_get_tab": (True, False, True),
        "arc_get_sidebar_tree": (True, False, True),
        "arc_search_history": (True, False, True),
        "arc_analyze_tabs": (True, False, True),
        "arc_create_tab": (False, False, False),
        "arc_focus_space": (False, False, False),
        "arc_select_tab": (False, False, False),
        "arc_open_url": (False, False, False),
        "arc_reload_tabs": (False, False, False),
        "arc_close_tabs": (False, True, False),
        "arc_execute_javascript": (False, False, False),
    }
    annotations_by_name = {tool.name: tool.annotations for tool in run(mcp.list_tools())}
    for name, (
        read_only_hint,
        destructive_hint,
        idempotent_hint,
    ) in expected_annotations.items():
        annotations = annotations_by_name[name]
        assert annotations.readOnlyHint is read_only_hint
        assert annotations.destructiveHint is destructive_hint
        assert annotations.idempotentHint is idempotent_hint


def test_read_only_tool_invocation_uses_injected_index_cache() -> None:
    mcp = FastMCP("test")
    index_cache = FakeIndexCache()

    register_tools(
        mcp,
        adapter=FakeAdapter(),
        index_cache=index_cache,
        history_store=FakeHistoryStore(),
    )

    result = run(
        mcp.call_tool(
            "arc_query_tabs",
            {"query": "python", "space_id": "space-1"},
        )
    )

    assert index_cache.calls == [("get", {})]
    assert result.structured_content == {
        "total": 1,
        "cursor": None,
        "items": [{"id": "tab-1"}],
    }


def test_analyze_tabs_tool_forwards_stale_threshold() -> None:
    mcp = FastMCP("test")
    index_cache = FakeIndexCache()

    register_tools(
        mcp,
        adapter=FakeAdapter(),
        index_cache=index_cache,
        history_store=FakeHistoryStore(),
    )

    result = run(
        mcp.call_tool(
            "arc_analyze_tabs",
            {
                "analyses": ["stale"],
                "stale_before": "2026-05-01T00:00:00+00:00",
            },
        )
    )

    assert result.structured_content == {"total": 0, "groups": []}
    assert index_cache.index.analyze_calls == [
        {
            "analyses": ["stale"],
            "limit": 50,
            "include_evidence": True,
            "stale_before": datetime(2026, 5, 1, tzinfo=UTC),
        }
    ]


def test_mutating_tool_invocation_uses_injected_adapter_batch_handler() -> None:
    mcp = FastMCP("test")
    adapter = FakeAdapter()

    register_tools(
        mcp,
        adapter=adapter,
        index_cache=FakeIndexCache(),
        history_store=FakeHistoryStore(),
    )

    result = run(
        mcp.call_tool(
            "arc_close_tabs",
            {"tab_ids": ["tab-1"], "dry_run": True},
        )
    )

    assert adapter.calls == [("close_tabs", ["tab-1"], True)]
    assert result.structured_content == {
        "results": [{"tab_id": "tab-1", "closed": False}]
    }


def test_create_tab_tool_returns_verified_tab_id() -> None:
    mcp = FastMCP("test")
    adapter = FakeAdapter()

    register_tools(
        mcp,
        adapter=adapter,
        index_cache=FakeIndexCache(),
        history_store=FakeHistoryStore(),
    )

    result = run(
        mcp.call_tool(
            "arc_create_tab",
            {
                "space_id": "space-1",
                "url": "https://example.com/new",
            },
        )
    )

    assert result.structured_content == {
        "tab_id": "new-tab",
        "space_id": "space-1",
        "url": "https://example.com/new",
        "selected": True,
    }
    assert adapter.calls == [
        ("list_tabs", "space-1", None),
        ("add_tab_to_space", "space-1", "https://example.com/new", None),
        ("list_tabs", "space-1", None),
        ("select_tab", "new-tab"),
    ]


def test_batch_tools_fall_back_to_single_tab_adapter_methods() -> None:
    mcp = FastMCP("test")
    adapter = FakeBatchlessAdapter()

    register_tools(
        mcp,
        adapter=adapter,
        index_cache=FakeIndexCache(),
        history_store=FakeHistoryStore(),
    )

    close_result = run(
        mcp.call_tool(
            "arc_close_tabs",
            {"tab_ids": ["tab-1", "tab-2"]},
        )
    )
    reload_result = run(
        mcp.call_tool(
            "arc_reload_tabs",
            {"tab_ids": ["tab-3"]},
        )
    )

    assert adapter.calls == [
        ("close_tab", "tab-1"),
        ("close_tab", "tab-2"),
        ("reload_tab", "tab-3"),
    ]
    assert close_result.structured_content == {
        "results": [
            {"tab_id": "tab-1", "closed": True},
            {"tab_id": "tab-2", "closed": True},
        ]
    }
    assert reload_result.structured_content == {
        "results": [{"tab_id": "tab-3", "reloaded": True}]
    }


def test_handle_close_tabs_rejects_query_like_tab_ids() -> None:
    with pytest.raises(ArcBrowserMCPError, match="explicit tab_ids"):
        handle_close_tabs(FakeAdapter(), tab_ids=["domain:example.com"])
