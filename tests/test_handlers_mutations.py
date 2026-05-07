import pytest

from arc_browser_mcp.errors import ArcBrowserMCPError
from arc_browser_mcp.handlers import (
    handle_close_tab,
    handle_close_tabs,
    handle_create_tab,
    handle_focus_space,
    handle_open_url,
    handle_reload_tab,
    handle_reload_tabs,
    handle_select_tab,
)


class FakeAdapter:
    def focus_space(self, space_id):
        return {"space_id": space_id, "focused": True}

    def select_tab(self, tab_id):
        return {"tab_id": tab_id, "selected": True}

    def close_tab(self, tab_id):
        return {"tab_id": tab_id, "closed": True}

    def open_url(self, url, tab_id=None):
        return {"url": url, "tab_id": tab_id, "opened": True}

    def reload_tab(self, tab_id):
        return {"tab_id": tab_id, "reloaded": True}


def test_mutating_handlers_delegate_to_adapter() -> None:
    adapter = FakeAdapter()

    assert handle_focus_space(adapter, "space-1")["focused"] is True
    assert handle_select_tab(adapter, "tab-1")["selected"] is True
    assert handle_close_tab(adapter, "tab-1")["closed"] is True
    assert handle_open_url(adapter, "https://example.com", tab_id="tab-1")["opened"] is True
    assert handle_reload_tab(adapter, "tab-1")["reloaded"] is True


class BatchAdapter:
    def __init__(self) -> None:
        self.closed_tab_ids: list[str] | None = None
        self.reloaded_tab_ids: list[str] | None = None
        self.create_calls: list[tuple[str, str, str | None]] = []
        self.list_calls: list[tuple[str | None, str | None]] = []
        self.select_calls: list[str] = []
        self.tab_reads = [
            [
                type(
                    "Tab",
                    (),
                    {"id": "existing-tab", "url": "https://example.com/old"},
                )()
            ],
            [
                type(
                    "Tab",
                    (),
                    {"id": "existing-tab", "url": "https://example.com/old"},
                )(),
                type(
                    "Tab",
                    (),
                    {"id": "new-tab", "url": "https://example.com/new"},
                )(),
            ],
        ]

    def close_tabs(
        self,
        tab_ids: list[str],
        dry_run: bool = False,
    ) -> dict[str, object]:
        self.closed_tab_ids = tab_ids
        return {
            "results": [
                {"tab_id": tab_id, "closed": not dry_run, "dry_run": dry_run}
                for tab_id in tab_ids
            ]
        }

    def reload_tabs(self, tab_ids: list[str]) -> dict[str, object]:
        self.reloaded_tab_ids = tab_ids
        return {"results": [{"tab_id": tab_id, "reloaded": True} for tab_id in tab_ids]}

    def list_tabs(self, *, space_id=None, window_id=None):
        self.list_calls.append((space_id, window_id))
        if not self.tab_reads:
            return []
        return self.tab_reads.pop(0)

    def add_tab_to_space(
        self,
        space_id: str,
        url: str,
        window_id: str | None = None,
    ) -> dict[str, object]:
        self.create_calls.append((space_id, url, window_id))
        return {"space_id": space_id, "url": url, "created": True}

    def select_tab(self, tab_id: str) -> dict[str, object]:
        self.select_calls.append(tab_id)
        return {"tab_id": tab_id, "selected": True}


def test_close_tabs_requires_explicit_tab_ids() -> None:
    with pytest.raises(ArcBrowserMCPError, match="explicit tab_ids"):
        handle_close_tabs(BatchAdapter(), [])


def test_close_tabs_dry_run_returns_closed_false() -> None:
    result = handle_close_tabs(BatchAdapter(), ["tab-1"], dry_run=True)

    assert result == {
        "results": [{"tab_id": "tab-1", "closed": False, "dry_run": True}]
    }


def test_close_tabs_delegates_clean_tab_ids() -> None:
    adapter = BatchAdapter()

    handle_close_tabs(adapter, [" tab-1 ", "tab-2"])

    assert adapter.closed_tab_ids == ["tab-1", "tab-2"]


def test_reload_tabs_requires_explicit_tab_ids() -> None:
    with pytest.raises(ArcBrowserMCPError, match="explicit tab_ids"):
        handle_reload_tabs(BatchAdapter(), [])


def test_reload_tabs_delegates_valid_tab_ids() -> None:
    adapter = BatchAdapter()

    result = handle_reload_tabs(adapter, ["tab-1", "tab-2"])

    assert adapter.reloaded_tab_ids == ["tab-1", "tab-2"]
    assert result == {
        "results": [
            {"tab_id": "tab-1", "reloaded": True},
            {"tab_id": "tab-2", "reloaded": True},
        ]
    }


def test_reload_tabs_delegates_clean_tab_ids() -> None:
    adapter = BatchAdapter()

    handle_reload_tabs(adapter, [" tab-1 ", "tab-2 "])

    assert adapter.reloaded_tab_ids == ["tab-1", "tab-2"]


def test_create_tab_returns_verified_new_tab_id() -> None:
    adapter = BatchAdapter()

    result = handle_create_tab(
        adapter,
        space_id="space-1",
        url="https://example.com/new",
    )

    assert result == {
        "tab_id": "new-tab",
        "space_id": "space-1",
        "url": "https://example.com/new",
        "selected": True,
    }
    assert adapter.create_calls == [("space-1", "https://example.com/new", None)]
    assert adapter.select_calls == ["new-tab"]


def test_create_tab_uses_explicit_window_id_for_verification() -> None:
    adapter = BatchAdapter()

    result = handle_create_tab(
        adapter,
        space_id="space-1",
        url="https://example.com/new",
        window_id="window-1",
    )

    assert result["tab_id"] == "new-tab"
    assert adapter.list_calls == [("space-1", "window-1"), ("space-1", "window-1")]
    assert adapter.create_calls == [("space-1", "https://example.com/new", "window-1")]


def test_create_tab_requires_verified_new_tab() -> None:
    adapter = BatchAdapter()
    adapter.tab_reads = [[], []]

    with pytest.raises(ArcBrowserMCPError, match="Could not verify created tab"):
        handle_create_tab(
            adapter,
            space_id="space-1",
            url="https://example.com/new",
            verify_timeout_seconds=0,
        )


def test_create_tab_rejects_blank_space_id() -> None:
    with pytest.raises(ArcBrowserMCPError, match="explicit space_id"):
        handle_create_tab(BatchAdapter(), space_id=" ", url="https://example.com")


@pytest.mark.parametrize("tab_id", ["analysis:duplicates", "domain:example.com"])
def test_reload_tabs_rejects_query_like_tab_ids(tab_id: str) -> None:
    with pytest.raises(ArcBrowserMCPError, match="explicit tab_ids"):
        handle_reload_tabs(BatchAdapter(), [tab_id])
