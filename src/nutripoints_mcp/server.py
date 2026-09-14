"""The Nutri Points MCP server entrypoint."""

from __future__ import annotations

import os

from fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import PlainTextResponse

from nutripoints_mcp.tools import register_tools

SERVER_INSTRUCTIONS = """Use Nutri Points as the source of truth for saved items, nutrition, points, and validation.
Before creating a recipe, search saved recipes for a reusable match. Before creating any ingredient,
search both generic ingredients and specific food items. Inspect promising results by ID; a search
result is a candidate, not proof of an exact match. Reuse a suitable saved item instead of duplicating it.
When a new ingredient is needed, prefer a generic ingredient for a reusable ingredient category.
Create a specific food item when the exact product, brand, preparation, or nutrition is necessary.
If required nutrition facts are missing, ask for them rather than inventing values.
Save or update a draft first, use its returned version for further edits, and publish only when the
caller intends to make it available. Validate recipe drafts and follow Nutri Points' required_next_actions
before publishing. Pass through Nutri Points errors and calculated values without changing them.
Recipe write ingredients use kind "fixed_food" with food_item_id or food_draft_id, or kind "generic" with
ingredient_type_id or ingredient_type_draft_id; both require quantity with a supported mode. Do not copy
display, calculated, ID, timestamp, archive, origin, or basis fields from read responses into draft payloads
unless that field is explicitly present in the write tool schema.
"""

mcp = FastMCP("Nutri Points", instructions=SERVER_INSTRUCTIONS)
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
