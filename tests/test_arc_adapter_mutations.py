import json

import pytest

from arc_browser_mcp.arc import ArcAdapter
from arc_browser_mcp.errors import (
    ArcAutomationError,
    ArcNotRunningError,
    ArcObjectNotFoundError,
)


class QueueRunner:
    def __init__(self):
        self.jxa_outputs = ["true"]
        self.applescript_scripts: list[str] = []

    def run_jxa(self, script: str, *, timeout: float = 10.0) -> str:
        return self.jxa_outputs.pop(0)

    def run_applescript(self, script: str, *, timeout: float = 10.0) -> str:
        self.applescript_scripts.append(script)
        return "ok"


def test_focus_space_runs_focus_command() -> None:
    runner = QueueRunner()

    result = ArcAdapter(runner=runner).focus_space("space-1")

    assert result == {"space_id": "space-1", "focused": True}
    assert "focus s" in runner.applescript_scripts[0]
    assert "space-1" in runner.applescript_scripts[0]


def test_select_tab_runs_select_command() -> None:
    runner = QueueRunner()

    result = ArcAdapter(runner=runner).select_tab("tab-1")

    assert result == {"tab_id": "tab-1", "selected": True}
    assert "select t" in runner.applescript_scripts[0]


def test_close_tab_runs_close_command() -> None:
    runner = QueueRunner()

    result = ArcAdapter(runner=runner).close_tab("tab-1")

    assert result == {"tab_id": "tab-1", "closed": True}
    assert "close t" in runner.applescript_scripts[0]


def test_close_tabs_dry_run_does_not_run_applescript() -> None:
    runner = QueueRunner()

    result = ArcAdapter(runner=runner).close_tabs(["tab-1", "tab-2"], dry_run=True)

    assert result == {
        "results": [
            {"tab_id": "tab-1", "closed": False, "dry_run": True},
            {"tab_id": "tab-2", "closed": False, "dry_run": True},
        ]
    }
    assert runner.applescript_scripts == []


def test_close_tabs_closes_each_tab_id() -> None:
    runner = QueueRunner()
    runner.jxa_outputs = ["true", "true"]

    result = ArcAdapter(runner=runner).close_tabs(["tab-1", "tab-2"])

    assert result == {
        "results": [
            {"tab_id": "tab-1", "closed": True, "ok": True},
            {"tab_id": "tab-2", "closed": True, "ok": True},
        ]
    }
    assert len(runner.applescript_scripts) == 2
    assert "tab-1" in runner.applescript_scripts[0]
    assert "tab-2" in runner.applescript_scripts[1]


def test_open_url_sets_target_tab_url() -> None:
    runner = QueueRunner()

    result = ArcAdapter(runner=runner).open_url("https://example.com", tab_id="tab-1")

    assert result == {"url": "https://example.com", "tab_id": "tab-1", "opened": True}
    assert 'set URL of t to "https://example.com"' in runner.applescript_scripts[0]


def test_open_url_preserves_non_ascii_url_in_applescript() -> None:
    runner = QueueRunner()

    ArcAdapter(runner=runner).open_url("https://example.com/café", tab_id="tab-1")

    script = runner.applescript_scripts[0]
    assert '"https://example.com/café"' in script
    assert "\\u00e9" not in script


def test_open_url_with_empty_tab_id_uses_targeted_lookup() -> None:
    runner = QueueRunner()

    ArcAdapter(runner=runner).open_url("https://example.com", tab_id="")

    script = runner.applescript_scripts[0]
    assert "repeat with t in tabs of s" in script
    assert 'error "ARC_MCP_OBJECT_NOT_FOUND: Tab not found: "' in script
    assert "active tab of front window" not in script


def test_reload_tab_runs_reload_command() -> None:
    runner = QueueRunner()

    result = ArcAdapter(runner=runner).reload_tab("tab-1")

    assert result == {"tab_id": "tab-1", "reloaded": True}
    assert "reload t" in runner.applescript_scripts[0]


def test_reload_tabs_reloads_each_tab_id() -> None:
    runner = QueueRunner()

    result = ArcAdapter(runner=runner).reload_tabs(["tab-1"])

    assert result == {"results": [{"tab_id": "tab-1", "reloaded": True, "ok": True}]}
    assert len(runner.applescript_scripts) == 1
    assert "reload t" in runner.applescript_scripts[0]


def test_tab_command_escapes_id_in_error_message() -> None:
    runner = QueueRunner()
    tab_id = 'tab-"quoted"\nnext'

    ArcAdapter(runner=runner).select_tab(tab_id)

    script = runner.applescript_scripts[0]
    assert 'tab-\\"quoted\\"\\nnext' in script
    assert 'Tab not found: tab-"quoted"' not in script


def test_applescript_not_found_errors_are_normalized() -> None:
    class NotFoundRunner(QueueRunner):
        def run_applescript(self, script: str, *, timeout: float = 10.0) -> str:
            raise ArcAutomationError(
                "ARC_MCP_OBJECT_NOT_FOUND: Tab not found: tab-1"
            )

    with pytest.raises(ArcObjectNotFoundError, match="Tab not found: tab-1"):
        ArcAdapter(runner=NotFoundRunner()).reload_tab("tab-1")


def test_prefixed_applescript_not_found_errors_are_normalized() -> None:
    class NotFoundRunner(QueueRunner):
        def run_applescript(self, script: str, *, timeout: float = 10.0) -> str:
            raise ArcAutomationError(
                "execution error: ARC_MCP_OBJECT_NOT_FOUND: Tab not found: tab-1"
            )

    with pytest.raises(ArcObjectNotFoundError, match="Tab not found: tab-1"):
        ArcAdapter(runner=NotFoundRunner()).reload_tab("tab-1")


def test_line_prefixed_applescript_not_found_errors_are_normalized() -> None:
    class NotFoundRunner(QueueRunner):
        def run_applescript(self, script: str, *, timeout: float = 10.0) -> str:
            raise ArcAutomationError(
                "6:55: execution error: ARC_MCP_OBJECT_NOT_FOUND: "
                "Tab not found: tab-1 (-2700)"
            )

    with pytest.raises(ArcObjectNotFoundError, match="Tab not found: tab-1"):
        ArcAdapter(runner=NotFoundRunner()).reload_tab("tab-1")


def test_non_sentinel_applescript_not_found_text_stays_automation_error() -> None:
    class JavaScriptErrorRunner(QueueRunner):
        def run_applescript(self, script: str, *, timeout: float = 10.0) -> str:
            raise ArcAutomationError("JavaScript error: Tab not found: fake")

    with pytest.raises(ArcAutomationError, match="JavaScript error"):
        ArcAdapter(runner=JavaScriptErrorRunner()).execute_javascript(
            "tab-1",
            "throw new Error('Tab not found: fake')",
        )


def test_javascript_sentinel_text_stays_automation_error() -> None:
    class JavaScriptErrorRunner(QueueRunner):
        def run_applescript(self, script: str, *, timeout: float = 10.0) -> str:
            raise ArcAutomationError(
                "JavaScript error: ARC_MCP_OBJECT_NOT_FOUND: Tab not found: fake"
            )

    with pytest.raises(ArcAutomationError, match="JavaScript error"):
        ArcAdapter(runner=JavaScriptErrorRunner()).execute_javascript(
            "tab-1",
            "throw new Error('ARC_MCP_OBJECT_NOT_FOUND: Tab not found: fake')",
        )


def test_execute_javascript_runs_generated_applescript() -> None:
    runner = QueueRunner()

    result = ArcAdapter(runner=runner).execute_javascript("tab-1", "document.title")

    assert result == {"tab_id": "tab-1", "result": "ok"}
    assert runner.jxa_outputs == []
    assert len(runner.applescript_scripts) == 1
    script = runner.applescript_scripts[0]
    assert 'if id of t is "tab-1"' in script
    assert 'execute t javascript "document.title"' in script


def test_add_tab_to_space_runs_generated_applescript() -> None:
    runner = QueueRunner()
    runner.jxa_outputs = [
        "true",
        json.dumps(
            [
                {
                    "id": "space-1",
                    "title": "Personal",
                    "window_id": "window-1",
                    "window_title": "Window",
                    "tab_count": 3,
                }
            ]
        ),
        "true",
    ]

    result = ArcAdapter(runner=runner).add_tab_to_space(
        "space-1",
        "https://example.com",
    )

    assert result == {
        "space_id": "space-1",
        "space_index": 1,
        "url": "https://example.com",
        "window_id": None,
        "created": True,
    }
    assert runner.jxa_outputs == []
    assert len(runner.applescript_scripts) == 1
    script = runner.applescript_scripts[0]
    assert "tell front window" in script
    assert "tell space 1" in script
    assert 'properties {URL:"https://example.com"}' in script


def test_add_tab_to_space_can_target_explicit_window() -> None:
    runner = QueueRunner()
    runner.jxa_outputs = [
        "true",
        json.dumps(
            [
                {
                    "id": "space-0",
                    "title": "Personal",
                    "window_id": "window-1",
                    "window_title": "Window",
                    "tab_count": 3,
                },
                {
                    "id": "space-1",
                    "title": "Health",
                    "window_id": "window-1",
                    "window_title": "Window",
                    "tab_count": 4,
                },
            ]
        ),
        "true",
    ]

    ArcAdapter(runner=runner).add_tab_to_space(
        "space-1",
        "https://example.com",
        window_id="window-1",
    )

    script = runner.applescript_scripts[0]
    assert 'tell (first window whose id is "window-1")' in script
    assert "tell space 2" in script
    assert 'properties {URL:"https://example.com"}' in script


def test_mutating_methods_do_not_run_applescript_when_arc_is_not_running() -> None:
    runner = QueueRunner()
    runner.jxa_outputs = ["false"]

    with pytest.raises(ArcNotRunningError):
        ArcAdapter(runner=runner).close_tab("tab-1")

    assert runner.applescript_scripts == []
