"""Tool calls against a recorded in-memory Nutri Points HTTP surface."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
from fastmcp import Client

from nutripoints_mcp import api_client
from nutripoints_mcp.server import mcp


@pytest.fixture
def recorded_api(monkeypatch: pytest.MonkeyPatch) -> list[httpx.Request]:
    calls: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.url.path == "/api/v1/ingredient-types/999":
            return httpx.Response(404, json={"detail": {"error_code": "ingredient_type_not_found"}})
        if request.url.path == "/api/v1/recipe-drafts/999/publish":
            return httpx.Response(409, json={"detail": {"error_code": "draft_version_conflict"}})
        if request.method == "DELETE":
            return httpx.Response(204)
        return httpx.Response(200, json={"id": 7, "version": 2, "items": []})

    real_client = httpx.AsyncClient
    transport = httpx.MockTransport(respond)
    monkeypatch.setattr(api_client.httpx, "AsyncClient", lambda **kwargs: real_client(transport=transport, **kwargs))
    monkeypatch.setenv("NUTRIPOINTS_BASE_URL", "https://nutripoints.example")
    monkeypatch.setenv("NUTRIPOINTS_API_KEY", "test-secret")
    return calls


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("tool", "path", "include_archived"),
    [
        ("search_recipes", "/api/v1/recipes", False),
        ("search_foods", "/api/v1/foods", True),
        ("search_generic_ingredients", "/api/v1/ingredient-types", True),
    ],
)
async def test_search_passes_contract_filters(
    recorded_api: list[httpx.Request], tool: str, path: str, include_archived: bool
) -> None:
    arguments: dict[str, Any] = {"q": "basil"}
    if include_archived:
        arguments["include_archived"] = True
    async with Client(mcp) as client:
        result = await client.call_tool(tool, arguments)
    assert result.data == {"id": 7, "version": 2, "items": []}
    assert recorded_api[-1].url.path == path
    assert recorded_api[-1].url.params["q"] == "basil"
    assert recorded_api[-1].url.params.get("include_archived") == ("true" if include_archived else None)
    assert recorded_api[-1].headers["authorization"] == "Bearer test-secret"


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("tool", "argument", "path"),
    [
        ("get_recipe", "recipe_id", "/api/v1/recipes/7"),
        ("get_food", "food_id", "/api/v1/foods/7"),
        ("get_generic_ingredient", "ingredient_type_id", "/api/v1/ingredient-types/7"),
    ],
)
async def test_published_detail_reads(recorded_api: list[httpx.Request], tool: str, argument: str, path: str) -> None:
    async with Client(mcp) as client:
        result = await client.call_tool(tool, {argument: 7})
    assert result.data["id"] == 7
    assert recorded_api[-1].url.path == path


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("domain", "base", "linked_id", "payload"),
    [
        (
            "recipe",
            "/api/v1/recipe-drafts",
            "recipe_id",
            {
                "name": "Soup",
                "total_servings": 2,
                "ingredients": [
                    {"kind": "generic", "quantity": {"mode": "grams", "value": 10}, "ingredient_type_id": 1}
                ],
            },
        ),
        (
            "food",
            "/api/v1/food-drafts",
            "food_item_id",
            {
                "name": "Basil",
                "nutrition_input_mode": "per_100g",
                "protein_g": 1,
                "carbs_g": 2,
                "fat_g": 0,
                "fiber_g": 1,
            },
        ),
        (
            "generic_ingredient",
            "/api/v1/ingredient-type-drafts",
            "ingredient_type_id",
            {
                "name": "Basil",
                "nutrition_input_mode": "per_100g",
                "protein_g": 1,
                "carbs_g": 2,
                "fat_g": 0,
                "fiber_g": 1,
            },
        ),
    ],
)
async def test_draft_lifecycle(
    recorded_api: list[httpx.Request], domain: str, base: str, linked_id: str, payload: dict[str, Any]
) -> None:
    async with Client(mcp) as client:
        saved = await client.call_tool(
            f"save_{domain}_draft", {"payload": payload, linked_id: 3, "idempotency_key": "save-1"}
        )
        updated = await client.call_tool(
            f"update_{domain}_draft", {"draft_id": 7, "payload": payload, "expected_version": 2}
        )
        published = await client.call_tool(f"publish_{domain}_draft", {"draft_id": 7, "expected_version": 2})
        discarded = await client.call_tool(f"discard_{domain}_draft", {"draft_id": 7})
    assert not any(result.is_error for result in [saved, updated, published, discarded])
    assert [request.method for request in recorded_api[-4:]] == ["POST", "PUT", "POST", "DELETE"]
    assert [request.url.path for request in recorded_api[-4:]] == [base, f"{base}/7", f"{base}/7/publish", f"{base}/7"]
    assert json.loads(recorded_api[-4].content)[linked_id] == 3
    assert recorded_api[-4].headers["idempotency-key"] == "save-1"
    assert json.loads(recorded_api[-3].content)["expected_version"] == 2
    assert json.loads(recorded_api[-2].content)["expected_version"] == 2


@pytest.mark.anyio
async def test_read_drafts_and_validate_recipe(recorded_api: list[httpx.Request]) -> None:
    cases = [
        ("get_recipe_draft_for_item", {"recipe_id": 2}, "/api/v1/recipes/2/draft"),
        ("get_food_draft_for_item", {"food_item_id": 2}, "/api/v1/foods/2/draft"),
        ("get_generic_ingredient_draft_for_item", {"ingredient_type_id": 2}, "/api/v1/ingredient-types/2/draft"),
        ("get_food_draft", {"draft_id": 2}, "/api/v1/food-drafts/2"),
        ("get_generic_ingredient_draft", {"draft_id": 2}, "/api/v1/ingredient-type-drafts/2"),
        ("validate_recipe_draft", {"draft_id": 2}, "/api/v1/recipe-drafts/2/validate"),
    ]
    async with Client(mcp) as client:
        for name, arguments, path in cases:
            result = await client.call_tool(name, arguments)
            assert not result.is_error
            assert recorded_api[-1].url.path == path


@pytest.mark.anyio
async def test_invalid_inputs_do_not_reach_api(recorded_api: list[httpx.Request]) -> None:
    malformed_food = {
        "name": "Bad\x00name",
        "nutrition_input_mode": "per_100g",
        "protein_g": 1,
        "carbs_g": 2,
        "fat_g": 0,
        "fiber_g": 1,
    }
    async with Client(mcp) as client:
        bad = [
            ("search_recipes", {"q": "x" * 121}),
            ("get_food", {"food_id": 0}),
            ("save_food_draft", {"payload": malformed_food}),
            ("publish_recipe_draft", {"draft_id": 1, "expected_version": 0}),
            ("discard_food_draft", {"draft_id": 1, "idempotency_key": "bad key"}),
        ]
        for name, arguments in bad:
            result = await client.call_tool(name, arguments, raise_on_error=False)
            assert result.is_error
    assert not recorded_api


@pytest.mark.anyio
async def test_tool_schemas_bound_all_scalar_and_collection_inputs() -> None:
    async with Client(mcp) as client:
        tools = await client.list_tools()

    def check(node: Any) -> None:
        if isinstance(node, list):
            for item in node:
                check(item)
        elif isinstance(node, dict):
            kind = node.get("type")
            if kind == "string":
                assert "maxLength" in node
            elif kind in ("number", "integer"):
                assert "minimum" in node and "maximum" in node
            elif kind == "array":
                assert "maxItems" in node
            elif kind == "object":
                assert node.get("additionalProperties") is not True
            for value in node.values():
                check(value)

    for tool in tools:
        if tool.name != "ping":
            check(tool.input_schema)


@pytest.mark.anyio
async def test_api_errors_are_tool_errors(recorded_api: list[httpx.Request]) -> None:
    async with Client(mcp) as client:
        missing = await client.call_tool("get_generic_ingredient", {"ingredient_type_id": 999}, raise_on_error=False)
        conflict = await client.call_tool(
            "publish_recipe_draft", {"draft_id": 999, "expected_version": 2}, raise_on_error=False
        )
    assert missing.is_error and "ingredient_type_not_found" in str(missing.content)
    assert conflict.is_error and "draft_version_conflict" in str(conflict.content)
    assert len(recorded_api) == 2
