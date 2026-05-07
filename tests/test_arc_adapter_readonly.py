import json

import pytest

from arc_browser_mcp.arc import ArcAdapter
from arc_browser_mcp.errors import ArcAutomationError, ArcNotRunningError, ArcObjectNotFoundError


class QueueRunner:
    def __init__(self, jxa_outputs: list[str | Exception] | None = None):
        self.jxa_outputs = jxa_outputs or []
        self.jxa_scripts: list[str] = []
        self.jxa_timeouts: list[float] = []
        self.applescript_scripts: list[str] = []

    def run_jxa(self, script: str, *, timeout: float = 10.0) -> str:
        self.jxa_scripts.append(script)
        self.jxa_timeouts.append(timeout)
        output = self.jxa_outputs.pop(0)
        if isinstance(output, Exception):
            raise output
        return output

    def run_applescript(self, script: str, *, timeout: float = 10.0) -> str:
        self.applescript_scripts.append(script)
        return ""


def test_read_only_operation_requires_running_arc() -> None:
    adapter = ArcAdapter(runner=QueueRunner(["false"]))

    with pytest.raises(ArcNotRunningError, match="Arc is not running"):
        adapter.list_spaces()


def test_list_spaces_returns_spaces_for_front_window() -> None:
    runner = QueueRunner(
        [
            "true",
            """
            [
              {"id":"space-1","title":"Personal","window_id":"win-1","window_title":"Window","tab_count":2}
            ]
            """,
        ]
    )

    spaces = ArcAdapter(runner=runner).list_spaces()

    assert spaces[0].id == "space-1"
    assert spaces[0].title == "Personal"
    assert spaces[0].tab_count == 2
    assert "System Events" in runner.jxa_scripts[0]
    assert "Application(\"Arc\")" in runner.jxa_scripts[1]


def test_list_tabs_can_filter_by_space_id() -> None:
    runner = QueueRunner(
        [
            "true",
            """
            [
              {
                "id":"tab-1",
                "title":"Example",
                "url":"https://example.com",
                "loading":false,
                "location":"unpinned",
                "space_id":"space-1",
                "space_title":"Personal",
                "window_id":"win-1",
                "window_title":"Window"
              }
            ]
            """,
        ]
    )

    tabs = ArcAdapter(runner=runner).list_tabs(space_id="space-1")

    assert tabs[0].id == "tab-1"
    assert tabs[0].url == "https://example.com"
    assert "space-1" in runner.jxa_scripts[1]


def test_list_tabs_uses_longer_timeout_for_data_jxa_call() -> None:
    runner = QueueRunner(["true", "[]"])

    ArcAdapter(runner=runner).list_tabs()

    assert runner.jxa_timeouts == [10.0, 30.0]


def test_list_tabs_escapes_space_id_in_generated_jxa() -> None:
    weird_id = 'space-"quoted"`tick`\nnext'
    runner = QueueRunner(["true", "[]"])

    ArcAdapter(runner=runner).list_tabs(space_id=weird_id)

    assert json.dumps(weird_id) in runner.jxa_scripts[1]
    assert f"const targetSpaceId = {weird_id};" not in runner.jxa_scripts[1]


def test_get_active_context_returns_window_space_and_tab() -> None:
    runner = QueueRunner(
        [
            "true",
            """
            {
              "id":"win-1",
              "title":"Window",
              "active_space":{"id":"space-1","title":"Personal","window_id":"win-1","window_title":"Window"},
              "active_tab":{
                "id":"tab-1",
                "title":"Example",
                "url":"https://example.com",
                "loading":false,
                "location":"pinned",
                "window_id":"win-1",
                "window_title":"Window"
              }
            }
            """,
        ]
    )

    context = ArcAdapter(runner=runner).get_active_context()

    assert context.id == "win-1"
    assert context.active_space is not None
    assert context.active_space.id == "space-1"
    assert context.active_tab is not None
    assert context.active_tab.location == "pinned"


def test_adapter_normalizes_not_found_errors() -> None:
    runner = QueueRunner(["true", "[]"])

    with pytest.raises(ArcObjectNotFoundError, match="Space not found"):
        ArcAdapter(runner=runner).get_space("missing-space")


def test_adapter_normalizes_window_not_found_automation_errors() -> None:
    runner = QueueRunner(
        [
            "true",
            ArcAutomationError(
                "ARC_MCP_OBJECT_NOT_FOUND: Window not found: missing-window"
            ),
        ]
    )

    with pytest.raises(ArcObjectNotFoundError, match="Window not found: missing-window"):
        ArcAdapter(runner=runner).list_spaces(window_id="missing-window")


def test_adapter_normalizes_jxa_wrapped_window_not_found_errors() -> None:
    runner = QueueRunner(
        [
            "true",
            ArcAutomationError(
                "execution error: Error: Error: ARC_MCP_OBJECT_NOT_FOUND: "
                "Window not found: missing-window (-2700)"
            ),
        ]
    )

    with pytest.raises(ArcObjectNotFoundError, match="Window not found: missing-window"):
        ArcAdapter(runner=runner).list_spaces(window_id="missing-window")


def test_adapter_does_not_normalize_non_sentinel_window_errors() -> None:
    runner = QueueRunner(
        ["true", ArcAutomationError("Error: Window not found: missing-window")]
    )

    with pytest.raises(ArcAutomationError, match="Window not found: missing-window"):
        ArcAdapter(runner=runner).list_spaces(window_id="missing-window")


def test_adapter_does_not_normalize_jxa_wrapped_non_sentinel_window_errors() -> None:
    runner = QueueRunner(
        [
            "true",
            ArcAutomationError(
                "execution error: Error: Error: Window not found: missing-window "
                "(-2700)"
            ),
        ]
    )

    with pytest.raises(ArcAutomationError, match="Window not found: missing-window"):
        ArcAdapter(runner=runner).list_spaces(window_id="missing-window")


def test_empty_window_id_is_treated_as_target_id() -> None:
    runner = QueueRunner(
        ["true", ArcAutomationError("ARC_MCP_OBJECT_NOT_FOUND: Window not found: ")]
    )

    with pytest.raises(ArcObjectNotFoundError, match="Window not found"):
        ArcAdapter(runner=runner).get_active_context(window_id="")

    script = runner.jxa_scripts[1]
    assert 'const targetWindowId = "";' in script
    assert "targetWindowId === null" in script


def test_empty_space_id_filters_instead_of_listing_all_tabs() -> None:
    runner = QueueRunner(["true", "[]"])

    tabs = ArcAdapter(runner=runner).list_tabs(space_id="")

    assert tabs == []
    script = runner.jxa_scripts[1]
    assert 'const targetSpaceId = "";' in script
    assert "targetSpaceId !== null" in script
    assert "targetSpaceId &&" not in script


def test_list_windows_returns_window_records() -> None:
    runner = QueueRunner(
        [
            "true",
            """
            [
              {
                "id":"win-1",
                "title":"Window",
                "active_space":{"id":"space-1","title":"Personal","window_id":"win-1","window_title":"Window"},
                "active_tab":{
                  "id":"tab-1",
                  "title":"Example",
                  "url":"https://example.com",
                  "loading":false,
                  "location":"pinned",
                  "window_id":"win-1",
                  "window_title":"Window"
                }
              }
            ]
            """,
        ]
    )

    windows = ArcAdapter(runner=runner).list_windows()

    assert windows[0].id == "win-1"
    assert windows[0].active_space is not None
    assert windows[0].active_space.title == "Personal"
    assert windows[0].active_tab is not None
    assert windows[0].active_tab.id == "tab-1"


def test_get_tab_raises_not_found_for_missing_tab() -> None:
    runner = QueueRunner(["true", "[]"])

    with pytest.raises(ArcObjectNotFoundError, match="Tab not found: missing-tab"):
        ArcAdapter(runner=runner).get_tab("missing-tab")
