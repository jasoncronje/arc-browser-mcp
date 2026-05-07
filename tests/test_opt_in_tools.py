import pytest

from arc_browser_mcp.arc import _add_tab_to_space_script, _execute_javascript_script
from arc_browser_mcp.errors import ArcBrowserMCPError
from arc_browser_mcp.handlers import handle_add_tab_to_space, handle_execute_javascript


class FakeAdapter:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str]] = []

    def execute_javascript(self, tab_id, javascript):
        self.calls.append(("execute_javascript", tab_id, javascript))
        return {"tab_id": tab_id, "result": "Example"}

    def add_tab_to_space(self, space_id, url):
        self.calls.append(("add_tab_to_space", space_id, url))
        return {"space_id": space_id, "url": url, "created": True}


def test_execute_javascript_is_disabled_by_default(monkeypatch) -> None:
    monkeypatch.delenv("ARC_MCP_ENABLE_JAVASCRIPT", raising=False)
    adapter = FakeAdapter()

    with pytest.raises(ArcBrowserMCPError, match="ARC_MCP_ENABLE_JAVASCRIPT=1"):
        handle_execute_javascript(adapter, "tab-1", "document.title")

    assert adapter.calls == []


def test_execute_javascript_delegates_when_enabled() -> None:
    result = handle_execute_javascript(
        FakeAdapter(),
        "tab-1",
        "document.title",
        enabled=True,
    )

    assert result == {"tab_id": "tab-1", "result": "Example"}


def test_execute_javascript_env_flag_enables_delegation(monkeypatch) -> None:
    monkeypatch.setenv("ARC_MCP_ENABLE_JAVASCRIPT", "1")
    adapter = FakeAdapter()

    result = handle_execute_javascript(adapter, "tab-1", "document.title")

    assert result == {"tab_id": "tab-1", "result": "Example"}
    assert adapter.calls == [("execute_javascript", "tab-1", "document.title")]


def test_execute_javascript_non_one_env_flag_stays_disabled(monkeypatch) -> None:
    monkeypatch.setenv("ARC_MCP_ENABLE_JAVASCRIPT", "true")
    adapter = FakeAdapter()

    with pytest.raises(ArcBrowserMCPError, match="ARC_MCP_ENABLE_JAVASCRIPT=1"):
        handle_execute_javascript(adapter, "tab-1", "document.title")

    assert adapter.calls == []


def test_add_tab_to_space_is_disabled_by_default(monkeypatch) -> None:
    monkeypatch.delenv("ARC_MCP_ENABLE_EXPERIMENTAL", raising=False)
    adapter = FakeAdapter()

    with pytest.raises(ArcBrowserMCPError, match="ARC_MCP_ENABLE_EXPERIMENTAL=1"):
        handle_add_tab_to_space(
            adapter,
            "space-1",
            "https://example.com",
        )

    assert adapter.calls == []


def test_add_tab_to_space_delegates_when_enabled() -> None:
    result = handle_add_tab_to_space(
        FakeAdapter(),
        "space-1",
        "https://example.com",
        enabled=True,
    )

    assert result == {"space_id": "space-1", "url": "https://example.com", "created": True}


def test_add_tab_to_space_env_flag_enables_delegation(monkeypatch) -> None:
    monkeypatch.setenv("ARC_MCP_ENABLE_EXPERIMENTAL", "1")
    adapter = FakeAdapter()

    result = handle_add_tab_to_space(adapter, "space-1", "https://example.com")

    assert result == {"space_id": "space-1", "url": "https://example.com", "created": True}
    assert adapter.calls == [
        ("add_tab_to_space", "space-1", "https://example.com"),
    ]


def test_add_tab_to_space_non_one_env_flag_stays_disabled(monkeypatch) -> None:
    monkeypatch.setenv("ARC_MCP_ENABLE_EXPERIMENTAL", "true")
    adapter = FakeAdapter()

    with pytest.raises(ArcBrowserMCPError, match="ARC_MCP_ENABLE_EXPERIMENTAL=1"):
        handle_add_tab_to_space(adapter, "space-1", "https://example.com")

    assert adapter.calls == []


def test_execute_javascript_script_escapes_user_values() -> None:
    script = _execute_javascript_script('tab-"1', 'console.log("hello")')

    assert 'if id of t is "tab-\\"1"' in script
    assert 'execute t javascript "console.log(\\"hello\\")"' in script
    assert 'error "ARC_MCP_OBJECT_NOT_FOUND: Tab not found: tab-\\"1"' in script
    assert 'tab-"1' not in script.replace('tab-\\"1', "")


def test_add_tab_to_space_script_escapes_user_values() -> None:
    script = _add_tab_to_space_script(
        space_index=4,
        url='https://example.com/?q="quoted"',
    )

    assert "tell space 4" in script
    assert 'properties {URL:"https://example.com/?q=\\"quoted\\""}' in script
    assert 'error "ARC_MCP_OBJECT_NOT_FOUND: Space index not found: 4"' in script
