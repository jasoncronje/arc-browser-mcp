from fastmcp import FastMCP

from .tools import register_tools

SERVER_NAME = "Arc Browser"

mcp = FastMCP(SERVER_NAME)
register_tools(mcp)


def main() -> None:
    mcp.run()
