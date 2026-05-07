import asyncio
import json
import tomllib
from pathlib import Path

from fastmcp import FastMCP

from arc_browser_mcp.tools import register_tools

EXPECTED_TOOL_NAMES = {
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


def run(coro):
    return asyncio.run(coro)


def test_mcpb_manifest_points_to_uv_runtime() -> None:
    manifest = json.loads(Path("manifest.json").read_text())

    assert manifest["name"] == "arc-browser-mcp"
    assert manifest["server"]["type"] == "uv"
    assert manifest["server"]["entry_point"] == "src/arc_browser_mcp/server.py"
    assert manifest["server"]["mcp_config"]["command"] == "uv"
    assert manifest["server"]["mcp_config"]["args"] == [
        "run",
        "--directory",
        "${__dirname}",
        "arc-browser-mcp",
    ]
    assert "darwin" in manifest["compatibility"]["platforms"]


def test_mcpb_manifest_matches_package_version_and_tools() -> None:
    manifest = json.loads(Path("manifest.json").read_text())
    pyproject = tomllib.loads(Path("pyproject.toml").read_text())
    mcp = FastMCP("test")
    register_tools(mcp)
    registered_tool_names = {tool.name for tool in run(mcp.list_tools())}

    assert manifest["version"] == pyproject["project"]["version"]
    assert {tool["name"] for tool in manifest["tools"]} == EXPECTED_TOOL_NAMES
    assert {tool["name"] for tool in manifest["tools"]} == registered_tool_names
    assert all(tool.get("description") for tool in manifest["tools"])
