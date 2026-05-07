import pytest

from arc_browser_mcp.cli import (
    SmokeCheck,
    build_install_output,
    doctor_checks,
    main,
    run_read_only_smoke,
)
from arc_browser_mcp.errors import ArcObjectNotFoundError
from arc_browser_mcp.models import ArcSpace, ArcTab, ArcWindow


class SmokeAdapter:
    def __init__(self):
        self.calls: list[tuple[str, dict[str, str | None]]] = []

    def list_spaces(self, window_id: str | None = None) -> list[ArcSpace]:
        self.calls.append(("list_spaces", {"window_id": window_id}))
        return [
            ArcSpace(
                id="space-1",
                title="Personal",
                window_id="window-1",
                window_title="Window",
                tab_count=2,
            )
        ]

    def get_active_context(self, window_id: str | None = None) -> ArcWindow:
        self.calls.append(("get_active_context", {"window_id": window_id}))
        if window_id == "":
            raise ArcObjectNotFoundError("Window not found: ")
        return ArcWindow(
            id="window-1",
            title="Window",
            active_space=ArcSpace(id="space-1", title="Personal"),
            active_tab=ArcTab(
                id="tab-1",
                title="Example",
                url="https://example.com",
                loading=False,
                location="pinned",
                space_id="space-1",
            ),
        )

    def list_tabs(
        self,
        *,
        window_id: str | None = None,
        space_id: str | None = None,
    ) -> list[ArcTab]:
        self.calls.append(
            ("list_tabs", {"window_id": window_id, "space_id": space_id})
        )
        if space_id == "":
            return []
        tabs = [
            ArcTab(
                id="tab-1",
                title="Pinned",
                url="https://example.com/pinned",
                loading=False,
                location="pinned",
                space_id="space-1",
            ),
            ArcTab(
                id="tab-2",
                title="Regular",
                url="https://example.com/regular",
                loading=False,
                location="unpinned",
                space_id="space-1",
            ),
        ]
        if space_id == "space-1":
            return tabs
        return tabs + [
            ArcTab(
                id="tab-3",
                title="Top App",
                url="https://example.com/top-app",
                loading=False,
                location="topApp",
                space_id="space-2",
            )
        ]


def test_build_install_output_for_codex() -> None:
    output = build_install_output("codex")

    assert "codex mcp add arc-browser -- uvx arc-browser-mcp" in output


def test_build_install_output_for_claude_code() -> None:
    output = build_install_output("claude-code")

    assert "claude mcp add --transport stdio --scope user arc-browser" in output
    assert "uvx arc-browser-mcp" in output


def test_build_install_output_for_opencode() -> None:
    output = build_install_output("opencode")

    assert '"arc_browser"' in output
    assert '"uvx"' in output
    assert '"arc-browser-mcp"' in output


def test_build_install_output_for_claude_desktop() -> None:
    output = build_install_output("claude-desktop")

    assert "mcpServers" in output
    assert "uvx" in output
    assert "arc-browser-mcp" in output
    assert '"type": "stdio"' not in output
    assert "Claude Desktop Extension / DXT package" in output


def test_build_install_output_rejects_unsupported_client() -> None:
    with pytest.raises(ValueError, match="Unsupported client: unsupported"):
        build_install_output("unsupported")


def test_install_command_rejects_unsupported_client() -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["install", "--client", "unsupported"])

    assert exc_info.value.code == 2


def test_doctor_checks_report_platform_and_commands(monkeypatch) -> None:
    monkeypatch.setattr("platform.system", lambda: "Darwin")
    monkeypatch.setattr("shutil.which", lambda command: f"/usr/bin/{command}")

    checks = doctor_checks(arc_app_exists=True)

    assert all(check.ok for check in checks)
    assert {check.name for check in checks} == {"macOS", "osascript", "uvx", "Arc app"}


def test_doctor_command_reports_failure_and_nonzero(monkeypatch, capsys) -> None:
    monkeypatch.setattr("platform.system", lambda: "Darwin")
    monkeypatch.setattr(
        "shutil.which",
        lambda command: None if command == "uvx" else f"/usr/bin/{command}",
    )
    monkeypatch.setattr("arc_browser_mcp.cli.Path.exists", lambda self: True)

    exit_code = main(["doctor"])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "fail" in captured.out
    assert "uvx" in captured.out


def test_install_command_prints_guidance(capsys) -> None:
    exit_code = main(["install", "--client", "codex"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "codex mcp add arc-browser -- uvx arc-browser-mcp" in captured.out


def test_serve_routes_to_server_main_without_blocking(monkeypatch) -> None:
    calls = []

    def fake_serve() -> None:
        calls.append("serve")

    monkeypatch.setattr("arc_browser_mcp.server.main", fake_serve)

    assert main([]) == 0
    assert main(["serve"]) == 0
    assert calls == ["serve", "serve"]


def test_smoke_read_only_runs_safety_checks(monkeypatch, capsys) -> None:
    class FakeIndex:
        def overview(self):
            return {
                "totals": {"spaces": 1, "tabs": 2, "missing_urls": 0},
                "spaces": [],
            }

        def query_tabs(self, **kwargs):
            return {
                "total": 2,
                "items": [{"id": "tab-1"}, {"id": "tab-2"}],
                "cursor": None,
            }

    class FakeCache:
        def get(self):
            return FakeIndex()

    monkeypatch.setattr("arc_browser_mcp.index.ArcIndexCache", FakeCache)

    exit_code = main(["smoke", "--read-only"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "ok   arc_get_overview: spaces=1, tabs=2" in captured.out
    assert "ok   arc_query_tabs: 2 tab(s)" in captured.out


def test_read_only_smoke_checks_state_backed_overview() -> None:
    class FakeIndex:
        def overview(self):
            return {
                "totals": {"spaces": 1, "tabs": 2, "missing_urls": 0},
                "spaces": [],
            }

        def query_tabs(self, **kwargs):
            return {
                "total": 2,
                "items": [{"id": "tab-1"}, {"id": "tab-2"}],
                "cursor": None,
            }

    class FakeCache:
        def get(self):
            return FakeIndex()

    checks = run_read_only_smoke(index_cache=FakeCache(), live_adapter=None)

    assert SmokeCheck("arc_get_overview", True, "spaces=1, tabs=2") in checks
    assert SmokeCheck("arc_query_tabs", True, "2 tab(s)") in checks


def test_smoke_read_only_does_not_run_live_adapter_operations(
    monkeypatch,
    capsys,
) -> None:
    class FakeIndex:
        def overview(self):
            return {
                "totals": {"spaces": 1, "tabs": 2, "missing_urls": 0},
                "spaces": [],
            }

        def query_tabs(self, **kwargs):
            return {
                "total": 2,
                "items": [{"id": "tab-1"}, {"id": "tab-2"}],
                "cursor": None,
            }

    class FakeCache:
        def get(self):
            return FakeIndex()

    def fail_adapter_factory():
        raise AssertionError("read-only smoke must not create a live adapter")

    monkeypatch.setattr("arc_browser_mcp.index.ArcIndexCache", FakeCache)

    exit_code = main(["smoke", "--read-only"], adapter_factory=fail_adapter_factory)

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "arc_get_overview" in captured.out
    assert "arc_query_tabs" in captured.out


def test_smoke_requires_read_only_flag() -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["smoke"])

    assert exc_info.value.code == 2
