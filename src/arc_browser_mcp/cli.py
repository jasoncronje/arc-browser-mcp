from __future__ import annotations

import argparse
import json
import platform
import shutil
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .errors import ArcObjectNotFoundError


@dataclass(frozen=True)
class DoctorCheck:
    name: str
    ok: bool
    detail: str


@dataclass(frozen=True)
class SmokeCheck:
    name: str
    ok: bool
    detail: str


def doctor_checks(*, arc_app_exists: bool | None = None) -> list[DoctorCheck]:
    if arc_app_exists is None:
        arc_app_exists = Path("/Applications/Arc.app").exists()

    return [
        DoctorCheck(
            name="macOS",
            ok=platform.system() == "Darwin",
            detail="required for Arc AppleScript automation",
        ),
        DoctorCheck(
            name="osascript",
            ok=shutil.which("osascript") is not None,
            detail="required for AppleScript and JXA",
        ),
        DoctorCheck(
            name="uvx",
            ok=shutil.which("uvx") is not None,
            detail="recommended for client stdio launch commands",
        ),
        DoctorCheck(
            name="Arc app",
            ok=arc_app_exists,
            detail="/Applications/Arc.app",
        ),
    ]


def build_install_output(client: str) -> str:
    if client == "codex":
        return "Run:\n\ncodex mcp add arc-browser -- uvx arc-browser-mcp\n"

    if client == "claude-code":
        return (
            "Run:\n\n"
            "claude mcp add --transport stdio --scope user arc-browser "
            "-- uvx arc-browser-mcp\n"
        )

    if client == "opencode":
        snippet = {
            "$schema": "https://opencode.ai/config.json",
            "mcp": {
                "arc_browser": {
                    "type": "local",
                    "command": ["uvx", "arc-browser-mcp"],
                    "enabled": True,
                    "timeout": 10000,
                }
            },
        }
        return (
            "Add this server entry to ~/.config/opencode/opencode.json or project "
            "opencode.json:\n\n"
            f"{json.dumps(snippet, indent=2)}\n"
        )

    if client == "claude-desktop":
        snippet = {
            "mcpServers": {
                "arc-browser": {
                    "command": "uvx",
                    "args": ["arc-browser-mcp"],
                    "env": {},
                }
            }
        }
        return (
            "For development, add this to Claude Desktop MCP config. "
            "For end users, prefer a Claude Desktop Extension / DXT package:\n\n"
            f"{json.dumps(snippet, indent=2)}\n"
        )

    raise ValueError(f"Unsupported client: {client}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="arc-browser-mcp")
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("serve", help="Run the MCP server over stdio")
    subparsers.add_parser("doctor", help="Check local Arc MCP prerequisites")
    smoke = subparsers.add_parser(
        "smoke",
        help="Run local live smoke checks against Arc",
    )
    smoke.add_argument(
        "--read-only",
        action="store_true",
        help="Only run read-only checks. Required for smoke tests.",
    )

    install = subparsers.add_parser("install", help="Print MCP client install guidance")
    install.add_argument(
        "--client",
        required=True,
        choices=["codex", "claude-code", "opencode", "claude-desktop"],
    )

    return parser


def run_read_only_smoke(
    index_cache: Any,
    live_adapter: Any | None = None,
) -> list[SmokeCheck]:
    checks: list[SmokeCheck] = []

    try:
        overview = index_cache.get().overview()
        totals = overview.get("totals", {})
        spaces_total = totals.get("spaces", 0)
        tabs_total = totals.get("tabs", 0)
        checks.append(
            SmokeCheck(
                name="arc_get_overview",
                ok=spaces_total >= 0 and tabs_total >= 0,
                detail=f"spaces={spaces_total}, tabs={tabs_total}",
            )
        )
    except Exception as exc:
        checks.append(SmokeCheck("arc_get_overview", False, str(exc)))

    try:
        result = index_cache.get().query_tabs(limit=5)
        checks.append(
            SmokeCheck(
                name="arc_query_tabs",
                ok="items" in result,
                detail=f"{result.get('total', 0)} tab(s)",
            )
        )
    except Exception as exc:
        checks.append(SmokeCheck("arc_query_tabs", False, str(exc)))

    if live_adapter is None:
        return checks

    adapter = live_adapter
    spaces = []
    context = None
    space_tabs = []

    try:
        spaces = adapter.list_spaces()
        checks.append(
            SmokeCheck(
                name="arc_list_spaces",
                ok=bool(spaces),
                detail=f"{len(spaces)} space(s)",
            )
        )
    except Exception as exc:
        checks.append(SmokeCheck("arc_list_spaces", False, str(exc)))

    try:
        context = adapter.get_active_context()
        active_space = getattr(context, "active_space", None)
        active_space_title = getattr(active_space, "title", None) or "unknown"
        checks.append(
            SmokeCheck(
                name="arc_get_active_context",
                ok=True,
                detail=f"window={context.title!r}, active_space={active_space_title!r}",
            )
        )
    except Exception as exc:
        checks.append(SmokeCheck("arc_get_active_context", False, str(exc)))

    if spaces:
        space = spaces[0]
        try:
            space_tabs = adapter.list_tabs(space_id=space.id)
            mismatched = [
                tab for tab in space_tabs if getattr(tab, "space_id", None) != space.id
            ]
            checks.append(
                SmokeCheck(
                    name="arc_list_tabs(space_id)",
                    ok=not mismatched,
                    detail=(
                        f"{len(space_tabs)} tab(s) for {space.title!r}"
                        if not mismatched
                        else f"{len(mismatched)} tab(s) had a different space_id"
                    ),
                )
            )
        except Exception as exc:
            checks.append(SmokeCheck("arc_list_tabs(space_id)", False, str(exc)))
    else:
        checks.append(
            SmokeCheck(
                name="arc_list_tabs(space_id)",
                ok=False,
                detail="skipped because no spaces were returned",
            )
        )

    try:
        empty_space_tabs = adapter.list_tabs(space_id="")
        checks.append(
            SmokeCheck(
                name="empty space_id strictness",
                ok=empty_space_tabs == [],
                detail=(
                    "returned []"
                    if empty_space_tabs == []
                    else f"returned {len(empty_space_tabs)} tab(s)"
                ),
            )
        )
    except Exception as exc:
        checks.append(SmokeCheck("empty space_id strictness", False, str(exc)))

    try:
        adapter.get_active_context(window_id="")
    except ArcObjectNotFoundError as exc:
        checks.append(
            SmokeCheck(
                name="empty window_id strictness",
                ok=True,
                detail=str(exc),
            )
        )
    except Exception as exc:
        checks.append(SmokeCheck("empty window_id strictness", False, str(exc)))
    else:
        checks.append(
            SmokeCheck(
                name="empty window_id strictness",
                ok=False,
                detail="returned the front window",
            )
        )

    return checks


def print_smoke_checks(checks: list[SmokeCheck]) -> None:
    for check in checks:
        status = "ok" if check.ok else "fail"
        print(f"{status:4} {check.name}: {check.detail}")


def main(
    argv: list[str] | None = None,
    *,
    adapter_factory: Callable[[], Any] | None = None,
) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command in (None, "serve"):
        from .server import main as serve

        serve()
        return 0

    if args.command == "doctor":
        checks = doctor_checks()
        for check in checks:
            status = "ok" if check.ok else "fail"
            print(f"{status:4} {check.name}: {check.detail}")
        return 0 if all(check.ok for check in checks) else 1

    if args.command == "install":
        print(build_install_output(args.client))
        return 0

    if args.command == "smoke":
        if not args.read_only:
            parser.error("smoke requires --read-only for live Arc safety")
        from .index import ArcIndexCache

        checks = run_read_only_smoke(index_cache=ArcIndexCache(), live_adapter=None)
        print_smoke_checks(checks)
        return 0 if all(check.ok for check in checks) else 1

    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
