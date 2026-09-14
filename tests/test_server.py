from __future__ import annotations

import pytest
from fastmcp import Client

from nutripoints_mcp.server import mcp


@pytest.mark.anyio
async def test_ping_tool_reports_reachable() -> None:
    async with Client(mcp) as client:
        result = await client.call_tool("ping", {})

    assert result.data == "pong"


@pytest.mark.anyio
async def test_server_exposes_ingredient_reuse_guidance() -> None:
    async with Client(mcp) as client:
        instructions = client.instructions

    assert instructions is not None
    assert "search both generic ingredients and specific food items" in instructions
    assert "Inspect promising results by ID" in instructions
    assert "prefer a generic ingredient" in instructions
    assert "exact product, brand, preparation, or nutrition" in instructions
    assert "rather than inventing values" in instructions
