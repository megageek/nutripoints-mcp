from __future__ import annotations

import pytest
from fastmcp import Client

from nutripoints_mcp.server import mcp


@pytest.mark.anyio
async def test_ping_tool_reports_reachable() -> None:
    async with Client(mcp) as client:
        result = await client.call_tool("ping", {})

    assert result.data == "pong"
