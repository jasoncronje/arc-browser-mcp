import subprocess

import pytest

from arc_browser_mcp.errors import ArcAutomationError
from arc_browser_mcp.osascript import OsascriptRunner


def test_run_jxa_invokes_osascript(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []
    options: dict[str, object] = {}

    def fake_run(args, capture_output, text, timeout, check):
        calls.append(args)
        options["capture_output"] = capture_output
        options["text"] = text
        options["timeout"] = timeout
        options["check"] = check
        return subprocess.CompletedProcess(args, 0, stdout="ok\n", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    output = OsascriptRunner().run_jxa("JSON.stringify(true)")

    assert output == "ok"
    assert calls == [["osascript", "-l", "JavaScript", "-e", "JSON.stringify(true)"]]
    assert options == {
        "capture_output": True,
        "text": True,
        "timeout": 10.0,
        "check": True,
    }


def test_run_applescript_wraps_subprocess_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run(args, capture_output, text, timeout, check):
        raise subprocess.CalledProcessError(
            returncode=1,
            cmd=args,
            output="",
            stderr="execution error: Arc is not running",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(ArcAutomationError, match="Arc is not running"):
        OsascriptRunner().run_applescript('tell application "Arc" to version')


def test_run_jxa_wraps_missing_osascript(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run(args, capture_output, text, timeout, check):
        raise FileNotFoundError

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(
        ArcAutomationError,
        match="osascript is not available on this system",
    ):
        OsascriptRunner().run_jxa("JSON.stringify(true)")


def test_run_jxa_wraps_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(args, capture_output, text, timeout, check):
        raise subprocess.TimeoutExpired(cmd=["osascript"], timeout=10.0)

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(ArcAutomationError, match="osascript timed out"):
        OsascriptRunner().run_jxa("JSON.stringify(true)")


def test_run_applescript_uses_stable_message_for_empty_process_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run(args, capture_output, text, timeout, check):
        raise subprocess.CalledProcessError(
            returncode=7,
            cmd=args,
            output="",
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(
        ArcAutomationError,
        match="osascript failed with exit code 7",
    ):
        OsascriptRunner().run_applescript('tell application "Arc" to version')
