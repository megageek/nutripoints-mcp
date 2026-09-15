"""The Nutri Points MCP server entrypoint."""

from __future__ import annotations

import os

from fastmcp import FastMCP
from mcp_types import ToolAnnotations
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
Use list_food_logs, list_activity_logs, and list_weight_logs to read saved records. Use get_today for the
current day or get_day for a specific calendar day. Day responses may have status "setup_blocked" when daily
budget prerequisites are missing; return that Nutri Points response unchanged rather than treating it as an error.
get_weight_overview and get_pending_weight_recap are read-only views of Nutri Points' calculated weight data.
Save or update a draft first, use its returned version for further edits, and publish only when the
caller intends to make it available. validate_recipe_draft accepts only a saved draft_id: it cannot accept
recipe data or save changes. Call save_recipe_draft first, then validate its returned draft_id and follow
Nutri Points' required_next_actions before publishing. Pass through Nutri Points errors and calculated values
without changing them.
Before editing a published item, read its current edit draft. Update that draft with its id and version when one
exists; otherwise create a linked draft using the published item ID.
Recipe write ingredients use kind "fixed_food" with food_item_id or food_draft_id, or kind "generic" with
ingredient_type_id or ingredient_type_draft_id; both require quantity with a supported mode. Do not copy
display, calculated, ID, timestamp, archive, origin, or basis fields from read responses into draft payloads
unless that field is explicitly present in the write tool schema.
For recipe drafts, put cook steps only in instruction_steps. Put reheat_fridge and reheat_freezer steps in
reheat_steps_fridge and reheat_steps_freezer respectively; do not mix their sections.
Recipe drafts support prep_time_minutes, cook_time_minutes, and passive_time_minutes (each 0–10080 minutes).
Put them in the recipe draft payload when known. update_recipe_draft replaces the full recipe payload, so do not
send timing fields by themselves.
Recipe draft payloads also support image_url and storage_life_fridge_days or storage_life_freezer_days. Storage
life is an optional whole number of days from 1–3650; use null to clear it. Do not invent storage life or image URLs.
When recipe instructions explicitly give a timed appliance setting or rest, add a matching automation action to
that step. Use timer or rest with duration_seconds; oven with temperature_c and duration_seconds (optional preheat);
hob with level and duration_seconds; microwave with power_watts and duration_seconds; or air_fryer with
temperature_c and duration_seconds (optional shake). Durations are whole seconds. Never invent a duration,
temperature, wattage, or hob level in order to add automation.
"""

mcp = FastMCP("Nutri Points", instructions=SERVER_INSTRUCTIONS)
register_tools(mcp)


@mcp.tool(tags={"read"}, annotations=ToolAnnotations(readOnlyHint=True))
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
