"""Every domain tool reports input and upstream errors without unsafe requests."""

from __future__ import annotations

from typing import Any

import pytest
from fastmcp import Client

from nutripoints_mcp import api_client
from nutripoints_mcp.server import mcp

FOOD_PAYLOAD = {
    "name": "Basil",
    "nutrition_input_mode": "per_100g",
    "protein_g": 1,
    "carbs_g": 2,
    "fat_g": 0,
    "fiber_g": 1,
}
RECIPE_PAYLOAD = {
    "name": "Soup",
    "total_servings": 2,
    "ingredients": [{"kind": "generic", "quantity": {"mode": "grams", "value": 10}, "ingredient_type_id": 1}],
}


def valid_arguments(name: str) -> dict[str, Any]:
    if name.startswith("search_"):
        return {"q": "basil"}
    if name.startswith("save_"):
        return {"payload": RECIPE_PAYLOAD if "recipe" in name else FOOD_PAYLOAD}
    if name.startswith("update_"):
        return {
            "draft_id": 1,
            "expected_version": 1,
            "payload": RECIPE_PAYLOAD if "recipe" in name else FOOD_PAYLOAD,
        }
    if name.startswith("publish_"):
        return {"draft_id": 1, "expected_version": 1}
    if name.startswith(("discard_", "validate_")) or name.endswith("_draft"):
        return {"draft_id": 1}
    if name.endswith("_draft_for_item"):
        if "recipe" in name:
            return {"recipe_id": 1}
        return {"food_item_id" if "food" in name else "ingredient_type_id": 1}
    if name == "get_recipe":
        return {"recipe_id": 1}
    if name == "get_food":
        return {"food_id": 1}
    return {"ingredient_type_id": 1}


def invalid_arguments(name: str) -> dict[str, Any]:
    arguments = valid_arguments(name)
    if "q" in arguments:
        arguments["q"] = "x" * 121
    elif "payload" in arguments and name.startswith("save_"):
        arguments["payload"] = {"name": "Incomplete"}
    elif "expected_version" in arguments:
        arguments["expected_version"] = 0
    else:
        key = next(iter(arguments))
        arguments[key] = 0
    return arguments


@pytest.mark.anyio
async def test_each_tool_rejects_bad_input_and_surfaces_api_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = 0

    async def fail_request(*_args: Any, **_kwargs: Any) -> Any:
        nonlocal calls
        calls += 1
        raise api_client.NutriPointsAPIError("Nutri Points HTTP 422: invalid draft")

    monkeypatch.setattr(api_client, "request", fail_request)
    async with Client(mcp) as client:
        names = [tool.name for tool in await client.list_tools() if tool.name != "ping"]
        for name in names:
            bad = await client.call_tool(name, invalid_arguments(name), raise_on_error=False)
            assert bad.is_error, name
            assert calls == names.index(name), name
            upstream = await client.call_tool(name, valid_arguments(name), raise_on_error=False)
            assert upstream.is_error, name
            assert "Nutri Points HTTP 422" in str(upstream.content), name
    assert calls == len(names)
