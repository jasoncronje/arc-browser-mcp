from fastmcp import FastMCP

from arc_browser_mcp.server import SERVER_NAME, mcp


def test_server_has_expected_name() -> None:
    assert SERVER_NAME == "Arc Browser"
    assert isinstance(mcp, FastMCP)
    assert mcp.name == SERVER_NAME
