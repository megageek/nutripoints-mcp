"""The Nutri Points MCP server entrypoint."""

from __future__ import annotations

import os

from fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import PlainTextResponse

from nutripoints_mcp.tools import register_tools

mcp = FastMCP("Nutri Points")
register_tools(mcp)


@mcp.tool
async def ping() -> str:
    """Confirm the MCP server is reachable."""
    return "pong"


@mcp.custom_route("/health", methods=["GET"])
async def health(_request: Request) -> PlainTextResponse:
    return PlainTextResponse("ok")


def main() -> None:
    mcp.run(
        transport="http",
        host=os.environ.get("MCP_HOST", "0.0.0.0"),
        port=int(os.environ.get("MCP_PORT", "8000")),
    )


if __name__ == "__main__":
    main()
