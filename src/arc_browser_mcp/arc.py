from __future__ import annotations

import json
import re
from typing import Any

from .errors import ArcAutomationError, ArcNotRunningError, ArcObjectNotFoundError
from .models import ArcSpace, ArcTab, ArcWindow
from .osascript import OsascriptRunner

ARC_RUNNING_SCRIPT = """
const se = Application("System Events");
JSON.stringify(se.processes.byName("Arc").exists())
""".strip()

OBJECT_NOT_FOUND_SENTINEL = "ARC_MCP_OBJECT_NOT_FOUND:"
OBJECT_NOT_FOUND_PATTERN = re.compile(
    rf"^(?:{re.escape(OBJECT_NOT_FOUND_SENTINEL)}|"
    rf"(?:\d+:\d+:\s*)?execution error:\s*(?:Error:\s*)*"
    rf"{re.escape(OBJECT_NOT_FOUND_SENTINEL)})\s*"
    r"(?P<message>.*?)(?:\s+\(-?\d+\))?$",
    re.DOTALL,
)


def _js_string(value: str | None) -> str:
    return json.dumps(value)


def _applescript_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


class ArcAdapter:
    def __init__(self, runner: OsascriptRunner | None = None):
        self.runner = runner or OsascriptRunner()

    def ensure_running(self) -> None:
        raw = self.runner.run_jxa(ARC_RUNNING_SCRIPT)
        try:
            is_running = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ArcAutomationError(f"Could not parse Arc running state: {raw}") from exc
        if is_running is not True:
            raise ArcNotRunningError("Arc is not running")

    def list_windows(self) -> list[ArcWindow]:
        rows = self._read_json(_list_windows_script())
        return [_window_from_record(row) for row in rows]

    def get_active_context(self, window_id: str | None = None) -> ArcWindow:
        record = self._read_json(_active_context_script(window_id))
        return _window_from_record(record)

    def list_spaces(self, window_id: str | None = None) -> list[ArcSpace]:
        rows = self._read_json(_list_spaces_script(window_id))
        return [_space_from_record(row) for row in rows]

    def get_space(self, space_id: str, window_id: str | None = None) -> ArcSpace:
        for space in self.list_spaces(window_id=window_id):
            if space.id == space_id:
                return space
        raise ArcObjectNotFoundError(f"Space not found: {space_id}")

    def list_tabs(
        self,
        *,
        window_id: str | None = None,
        space_id: str | None = None,
    ) -> list[ArcTab]:
        rows = self._read_json(
            _list_tabs_script(window_id=window_id, space_id=space_id), timeout=30.0
        )
        return [_tab_from_record(row) for row in rows]

    def get_tab(self, tab_id: str, window_id: str | None = None) -> ArcTab:
        for tab in self.list_tabs(window_id=window_id):
            if tab.id == tab_id:
                return tab
        raise ArcObjectNotFoundError(f"Tab not found: {tab_id}")

    def focus_space(self, space_id: str) -> dict[str, object]:
        self._run_applescript(_focus_space_script(space_id))
        return {"space_id": space_id, "focused": True}

    def select_tab(self, tab_id: str) -> dict[str, object]:
        self._run_applescript(_tab_command_script(tab_id, "select t"))
        return {"tab_id": tab_id, "selected": True}

    def close_tab(self, tab_id: str) -> dict[str, object]:
        self._run_applescript(_tab_command_script(tab_id, "close t"))
        return {"tab_id": tab_id, "closed": True}

    def close_tabs(
        self,
        tab_ids: list[str],
        dry_run: bool = False,
    ) -> dict[str, object]:
        if dry_run:
            return {
                "results": [
                    {"tab_id": tab_id, "closed": False, "dry_run": True}
                    for tab_id in tab_ids
                ]
            }
        results = []
        for tab_id in tab_ids:
            try:
                results.append({**self.close_tab(tab_id), "ok": True})
            except Exception as exc:
                results.append({"tab_id": tab_id, "ok": False, "error": str(exc)})
        return {"results": results}

    def reload_tab(self, tab_id: str) -> dict[str, object]:
        self._run_applescript(_tab_command_script(tab_id, "reload t"))
        return {"tab_id": tab_id, "reloaded": True}

    def reload_tabs(self, tab_ids: list[str]) -> dict[str, object]:
        results = []
        for tab_id in tab_ids:
            try:
                results.append({**self.reload_tab(tab_id), "ok": True})
            except Exception as exc:
                results.append({"tab_id": tab_id, "ok": False, "error": str(exc)})
        return {"results": results}

    def open_url(self, url: str, tab_id: str | None = None) -> dict[str, object]:
        self._run_applescript(_open_url_script(url=url, tab_id=tab_id))
        return {"url": url, "tab_id": tab_id, "opened": True}

    def execute_javascript(self, tab_id: str, javascript: str) -> dict[str, object]:
        result = self._run_applescript(_execute_javascript_script(tab_id, javascript))
        return {"tab_id": tab_id, "result": result}

    def add_tab_to_space(
        self,
        space_id: str,
        url: str,
        window_id: str | None = None,
    ) -> dict[str, object]:
        space_index = self._space_index(space_id=space_id, window_id=window_id)
        self._run_applescript(
            _add_tab_to_space_script(
                space_index=space_index,
                url=url,
                window_id=window_id,
            )
        )
        return {
            "space_id": space_id,
            "space_index": space_index,
            "url": url,
            "window_id": window_id,
            "created": True,
        }

    def _space_index(self, *, space_id: str, window_id: str | None = None) -> int:
        for index, space in enumerate(self.list_spaces(window_id=window_id), start=1):
            if space.id == space_id:
                return index
        raise ArcObjectNotFoundError(f"Space not found: {space_id}")

    def _read_json(self, script: str, *, timeout: float = 10.0) -> Any:
        self.ensure_running()
        try:
            raw = self.runner.run_jxa(script, timeout=timeout)
        except ArcAutomationError as exc:
            if message := _object_not_found_message(str(exc)):
                raise ArcObjectNotFoundError(message) from exc
            raise
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ArcAutomationError(f"Could not parse Arc response: {raw}") from exc

    def _run_applescript(self, script: str) -> str:
        self.ensure_running()
        try:
            return self.runner.run_applescript(script)
        except ArcAutomationError as exc:
            if message := _object_not_found_message(str(exc)):
                raise ArcObjectNotFoundError(message) from exc
            raise


def _window_selector_js(window_id: str | None) -> str:
    return f"""
const targetWindowId = {_js_string(window_id)};
function pickWindow() {{
  const windows = Arc.windows;
  if (windows.length === 0) {{
    throw new Error("Arc has no open windows");
  }}
  if (targetWindowId === null) {{
    return windows[0];
  }}
  for (let i = 0; i < windows.length; i++) {{
    if (windows[i].id() === targetWindowId) {{
      return windows[i];
    }}
  }}
  throw new Error(`{OBJECT_NOT_FOUND_SENTINEL} Window not found: ${{targetWindowId}}`);
}}
""".strip()


def _record_helpers_js() -> str:
    return """
function tabRecord(tab, space, window) {
  return {
    id: tab.id(),
    title: tab.title(),
    url: tab.url(),
    loading: tab.loading(),
    location: tab.location(),
    space_id: space ? space.id() : null,
    space_title: space ? space.title() : null,
    window_id: window.id(),
    window_title: window.title()
  };
}

function spaceRecord(space, window) {
  return {
    id: space.id(),
    title: space.title(),
    window_id: window.id(),
    window_title: window.title(),
    tab_count: space.tabs.length
  };
}

function windowRecord(window) {
  let activeSpace = null;
  let activeTab = null;
  try {
    activeSpace = {
      id: window.activeSpace.id(),
      title: window.activeSpace.title(),
      window_id: window.id(),
      window_title: window.title()
    };
  } catch (error) {}
  try {
    activeTab = tabRecord(window.activeTab, null, window);
  } catch (error) {}
  return {
    id: window.id(),
    title: window.title(),
    active_space: activeSpace,
    active_tab: activeTab
  };
}
""".strip()


def _list_windows_script() -> str:
    return f"""
const Arc = Application("Arc");
{_record_helpers_js()}
const result = [];
for (let i = 0; i < Arc.windows.length; i++) {{
  result.push(windowRecord(Arc.windows[i]));
}}
JSON.stringify(result)
""".strip()


def _active_context_script(window_id: str | None) -> str:
    return f"""
const Arc = Application("Arc");
{_window_selector_js(window_id)}
{_record_helpers_js()}
JSON.stringify(windowRecord(pickWindow()))
""".strip()


def _list_spaces_script(window_id: str | None) -> str:
    return f"""
const Arc = Application("Arc");
{_window_selector_js(window_id)}
{_record_helpers_js()}
const window = pickWindow();
const result = [];
for (let i = 0; i < window.spaces.length; i++) {{
  result.push(spaceRecord(window.spaces[i], window));
}}
JSON.stringify(result)
""".strip()


def _list_tabs_script(*, window_id: str | None, space_id: str | None) -> str:
    return f"""
const Arc = Application("Arc");
const targetSpaceId = {_js_string(space_id)};
{_window_selector_js(window_id)}
{_record_helpers_js()}
const window = pickWindow();
const result = [];
for (let i = 0; i < window.spaces.length; i++) {{
  const space = window.spaces[i];
  if (targetSpaceId !== null && space.id() !== targetSpaceId) {{
    continue;
  }}
  for (let j = 0; j < space.tabs.length; j++) {{
    result.push(tabRecord(space.tabs[j], space, window));
  }}
}}
JSON.stringify(result)
""".strip()


def _focus_space_script(space_id: str) -> str:
    target = _applescript_string(space_id)
    not_found_message = _applescript_string(
        _object_not_found_error("Space not found", space_id)
    )
    return f"""
tell application "Arc"
  repeat with w in windows
    repeat with s in spaces of w
      if id of s is {target} then
        focus s
        return "ok"
      end if
    end repeat
  end repeat
  error {not_found_message}
end tell
""".strip()


def _tab_command_script(tab_id: str, command: str) -> str:
    target = _applescript_string(tab_id)
    not_found_message = _applescript_string(
        _object_not_found_error("Tab not found", tab_id)
    )
    return f"""
tell application "Arc"
  repeat with w in windows
    repeat with s in spaces of w
      repeat with t in tabs of s
        if id of t is {target} then
          {command}
          return "ok"
        end if
      end repeat
    end repeat
  end repeat
  error {not_found_message}
end tell
""".strip()


def _open_url_script(*, url: str, tab_id: str | None) -> str:
    escaped_url = _applescript_string(url)
    if tab_id is not None:
        target = _applescript_string(tab_id)
        not_found_message = _applescript_string(
            _object_not_found_error("Tab not found", tab_id)
        )
        return f"""
tell application "Arc"
  repeat with w in windows
    repeat with s in spaces of w
      repeat with t in tabs of s
        if id of t is {target} then
          set URL of t to {escaped_url}
          return "ok"
        end if
      end repeat
    end repeat
  end repeat
  error {not_found_message}
end tell
""".strip()

    return f"""
tell application "Arc"
  set URL of active tab of front window to {escaped_url}
  return "ok"
end tell
""".strip()


def _execute_javascript_script(tab_id: str, javascript: str) -> str:
    target = _applescript_string(tab_id)
    escaped_js = _applescript_string(javascript)
    not_found_message = _applescript_string(
        _object_not_found_error("Tab not found", tab_id)
    )
    return f"""
tell application "Arc"
  repeat with w in windows
    repeat with s in spaces of w
      repeat with t in tabs of s
        if id of t is {target} then
          return execute t javascript {escaped_js}
        end if
      end repeat
    end repeat
  end repeat
  error {not_found_message}
end tell
""".strip()


def _add_tab_to_space_script(
    *,
    space_index: int,
    url: str,
    window_id: str | None = None,
) -> str:
    escaped_url = _applescript_string(url)
    window_selector = (
        f'(first window whose id is {_applescript_string(window_id)})'
        if window_id is not None
        else "front window"
    )
    not_found_message = _applescript_string(
        _object_not_found_error("Space index not found", str(space_index))
    )
    return f"""
tell application "Arc"
  tell {window_selector}
    try
      tell space {space_index}
        make new tab with properties {{URL:{escaped_url}}}
      end tell
    on error
      error {not_found_message}
    end try
  end tell
end tell
""".strip()


def _object_not_found_error(kind: str, object_id: str) -> str:
    return f"{OBJECT_NOT_FOUND_SENTINEL} {kind}: {object_id}"


def _object_not_found_message(message: str) -> str | None:
    match = OBJECT_NOT_FOUND_PATTERN.match(message)
    if match is None:
        return None
    return match.group("message").strip()


def _space_from_record(record: dict[str, Any]) -> ArcSpace:
    return ArcSpace(
        id=str(record["id"]),
        title=str(record["title"]),
        window_id=record.get("window_id"),
        window_title=record.get("window_title"),
        tab_count=record.get("tab_count"),
    )


def _tab_from_record(record: dict[str, Any]) -> ArcTab:
    return ArcTab(
        id=str(record["id"]),
        title=str(record["title"]),
        url=str(record.get("url") or ""),
        loading=bool(record["loading"]),
        location=str(record["location"]),
        space_id=record.get("space_id"),
        space_title=record.get("space_title"),
        window_id=record.get("window_id"),
        window_title=record.get("window_title"),
    )


def _window_from_record(record: dict[str, Any]) -> ArcWindow:
    active_space = record.get("active_space")
    active_tab = record.get("active_tab")
    return ArcWindow(
        id=str(record["id"]),
        title=str(record["title"]),
        active_space=_space_from_record(active_space) if active_space else None,
        active_tab=_tab_from_record(active_tab) if active_tab else None,
    )
