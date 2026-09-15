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
        if request.url.path == "/api/v1/days/today":
            return httpx.Response(
                200,
                json={
                    "status": "setup_blocked",
                    "date": "2026-09-15",
                    "timezone": "UTC",
                    "detail": {"error_code": "budget_not_ready", "message": "Add a weigh-in.", "retryable": False},
                },
            )
        if request.url.path == "/api/v1/days/2026-09-14":
            return httpx.Response(
                200,
                json={
                    "status": "ready",
                    "date": "2026-09-14",
                    "timezone": "UTC",
                    "food_entries": [],
                    "activity_entries": [],
                },
            )
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
                "instruction_steps": [{"section": "cook", "body_markdown": "Simmer until tender."}],
                "reheat_steps_freezer": [{"section": "reheat_freezer", "body_markdown": "Heat until hot."}],
                "image_url": "https://example.com/soup.jpg",
                "storage_life_fridge_days": 3,
                "storage_life_freezer_days": 90,
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
    if domain == "recipe":
        saved_payload = json.loads(recorded_api[-4].content)["payload"]
        assert saved_payload["instruction_steps"][0]["section"] == "cook"
        assert saved_payload["reheat_steps_freezer"][0]["section"] == "reheat_freezer"
        assert saved_payload["image_url"] == "https://example.com/soup.jpg"
        assert saved_payload["storage_life_fridge_days"] == 3
        assert saved_payload["storage_life_freezer_days"] == 90


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
@pytest.mark.parametrize(
    "name",
    ["list_food_logs", "list_activity_logs", "list_weight_logs"],
)
async def test_log_reads_forward_contract_filters(recorded_api: list[httpx.Request], name: str) -> None:
    arguments = {
        "date_from": "2026-09-01",
        "date_to": "2026-09-15",
        "start_at": "2026-09-01T08:00:00Z",
        "end_at": "2026-09-15T18:00:00Z",
        "limit": 25,
    }
    async with Client(mcp) as client:
        result = await client.call_tool(name, arguments)
    assert not result.is_error
    assert recorded_api[-1].url.path == f"/api/v1/logs/{name.removeprefix('list_').removesuffix('_logs')}"
    assert dict(recorded_api[-1].url.params) == {key: str(value) for key, value in arguments.items()}


@pytest.mark.anyio
async def test_weight_and_day_reads_preserve_api_responses(recorded_api: list[httpx.Request]) -> None:
    async with Client(mcp) as client:
        overview = await client.call_tool("get_weight_overview", {"range": "1y"})
        recap = await client.call_tool("get_pending_weight_recap", {})
        today = await client.call_tool("get_today", {})
        day = await client.call_tool("get_day", {"day": "2026-09-14"})

    assert not any(result.is_error for result in (overview, recap, today, day))
    assert overview.data == {"id": 7, "version": 2, "items": []}
    assert recap.data == {"id": 7, "version": 2, "items": []}
    assert today.data["status"] == "setup_blocked"
    assert today.data["detail"]["error_code"] == "budget_not_ready"
    assert day.data["status"] == "ready"
    assert day.data["food_entries"] == []
    assert [request.url.path for request in recorded_api[-4:]] == [
        "/api/v1/weight/overview",
        "/api/v1/weight/recap/pending",
        "/api/v1/days/today",
        "/api/v1/days/2026-09-14",
    ]
    assert recorded_api[-4].url.params["range"] == "1y"


@pytest.mark.anyio
async def test_validate_recipe_draft_only_accepts_a_saved_draft_id(recorded_api: list[httpx.Request]) -> None:
    async with Client(mcp) as client:
        tools = {tool.name: tool for tool in await client.list_tools()}
        validate_tool = tools["validate_recipe_draft"]
        result = await client.call_tool(
            "validate_recipe_draft", {"draft_id": 2, "payload": {"name": "Unsaved recipe"}}, raise_on_error=False
        )

    assert "existing, saved recipe draft" in validate_tool.description
    assert "does not accept recipe data" in validate_tool.description
    assert validate_tool.input_schema["required"] == ["draft_id"]
    assert set(validate_tool.input_schema["properties"]) == {"draft_id", "idempotency_key"}
    assert result.is_error
    assert "payload" in str(result.content)
    assert not recorded_api


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
@pytest.mark.parametrize(
    ("name", "arguments", "field"),
    [
        ("list_food_logs", {"date_from": "2026-02-30"}, "date_from"),
        ("list_activity_logs", {"date_from": "2026-09-16", "date_to": "2026-09-15"}, "date range"),
        ("list_weight_logs", {"start_at": "2026-09-01"}, "start_at"),
        (
            "list_food_logs",
            {"start_at": "2026-09-16T08:00:00Z", "end_at": "2026-09-15T08:00:00Z"},
            "datetime range",
        ),
        ("list_activity_logs", {"limit": 0}, "limit"),
        ("get_day", {"day": "20260915"}, "day"),
        ("get_weight_overview", {"range": "7d"}, "range"),
    ],
)
async def test_log_weight_and_day_reads_reject_invalid_input_locally(
    recorded_api: list[httpx.Request], name: str, arguments: dict[str, Any], field: str
) -> None:
    async with Client(mcp) as client:
        result = await client.call_tool(name, arguments, raise_on_error=False)
    assert result.is_error
    assert field in str(result.content)
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
async def test_tools_are_annotated_as_read_or_write() -> None:
    async with Client(mcp) as client:
        tools = {tool.name: tool for tool in await client.list_tools()}

    read_tools = {
        "ping",
        "validate_recipe_draft",
        "list_food_logs",
        "list_activity_logs",
        "list_weight_logs",
        "get_weight_overview",
        "get_pending_weight_recap",
        "get_today",
        "get_day",
        *(f"search_{domain}s" for domain in ("recipe", "food", "generic_ingredient")),
        *(f"get_{domain}" for domain in ("recipe", "food", "generic_ingredient")),
        *(f"get_{domain}_draft" for domain in ("food", "generic_ingredient")),
        *(f"get_{domain}_draft_for_item" for domain in ("recipe", "food", "generic_ingredient")),
    }

    assert read_tools <= tools.keys()
    for name, tool in tools.items():
        assert tool.annotations is not None
        assert tool.annotations.read_only_hint is (name in read_tools)


@pytest.mark.anyio
async def test_write_schemas_expose_constrained_payloads_and_recipe_unions() -> None:
    async with Client(mcp) as client:
        tools = {tool.name: tool for tool in await client.list_tools()}

    for domain in ("recipe", "food", "generic_ingredient"):
        for action in ("save", "update"):
            payload = tools[f"{action}_{domain}_draft"].input_schema["properties"]["payload"]
            assert payload["type"] == "object"
            assert payload["additionalProperties"] is False

    ingredients = tools["save_recipe_draft"].input_schema["properties"]["payload"]["properties"]["ingredients"]
    assert "oneOf" in ingredients["items"]
    branches = ingredients["items"]["oneOf"]
    assert {branch["properties"]["kind"]["const"] for branch in branches} == {"fixed_food", "generic"}
    assert all(branch["additionalProperties"] is False for branch in branches)
    assert {"grams", "milliliters", "serving_variant", "base_servings"} == set(
        branches[0]["properties"]["quantity"]["properties"]["mode"]["enum"]
    )
    assert branches[0]["properties"]["quantity"]["properties"]["food_item_serving_id"]
    assert all("allOf" in branch for branch in branches)
    assert all("oneOf" in branch["allOf"][0] for branch in branches)
    assert all("allOf" in branch["properties"]["quantity"] for branch in branches)

    recipe_payload = tools["save_recipe_draft"].input_schema["properties"]["payload"]
    for timing_field in ("prep_time_minutes", "cook_time_minutes", "passive_time_minutes"):
        assert recipe_payload["properties"][timing_field] == {
            "default": 0,
            "maximum": 10080.0,
            "minimum": 0.0,
            "title": timing_field.replace("_", " ").title(),
            "type": "integer",
        }
    storage_life_schema = {"type": "integer", "minimum": 1, "maximum": 3650}
    for storage_field in ("storage_life_fridge_days", "storage_life_freezer_days"):
        assert recipe_payload["properties"][storage_field]["anyOf"] == [storage_life_schema, {"type": "null"}]
    assert recipe_payload["properties"]["instruction_steps"]["items"]["properties"]["section"]["const"] == "cook"
    assert (
        recipe_payload["properties"]["reheat_steps_fridge"]["items"]["properties"]["section"]["const"]
        == "reheat_fridge"
    )
    assert (
        recipe_payload["properties"]["reheat_steps_freezer"]["items"]["properties"]["section"]["const"]
        == "reheat_freezer"
    )
    description = tools["update_recipe_draft"].description
    assert "food_item_serving_id" in description
    assert "reheat_steps_fridge" in description
    assert "reheat_steps_freezer" in description
    assert "automation action" in description
    assert "whole seconds" in description
    assert "prep_time_minutes" in description
    assert "cook_time_minutes" in description
    assert "passive_time_minutes" in description
    assert "replaces the full recipe payload" in description
    assert "storage_life_fridge_days" in description
    assert "storage_life_freezer_days" in description
    save_description = tools["save_recipe_draft"].description
    assert "get_recipe_draft_for_item" in save_description
    assert "update_recipe_draft" in save_description

    update_schema = tools["update_recipe_draft"].input_schema
    assert {"draft_id", "expected_version", "payload"} <= set(update_schema["required"])
    assert update_schema["properties"]["expected_version"] == {
        "type": "integer",
        "minimum": 1,
        "maximum": 9223372036854775807,
    }


@pytest.mark.anyio
async def test_recipe_draft_step_sections_are_checked_before_api(recorded_api: list[httpx.Request]) -> None:
    payload = {
        "name": "Soup",
        "total_servings": 2,
        "ingredients": [{"kind": "generic", "quantity": {"mode": "grams", "value": 10}, "ingredient_type_id": 1}],
        "instruction_steps": [{"section": "reheat_freezer", "body_markdown": "Heat until hot."}],
    }
    async with Client(mcp) as client:
        result = await client.call_tool("save_recipe_draft", {"payload": payload}, raise_on_error=False)
    assert result.is_error
    assert "cook" in str(result.content)
    assert not recorded_api


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("image_url", "x" * 1001),
        ("storage_life_fridge_days", 0),
        ("storage_life_freezer_days", 3651),
    ],
)
async def test_recipe_draft_rejects_invalid_image_and_storage_life_locally(
    recorded_api: list[httpx.Request], field: str, value: str | int
) -> None:
    payload: dict[str, Any] = {
        "name": "Soup",
        "total_servings": 2,
        "ingredients": [{"kind": "generic", "quantity": {"mode": "grams", "value": 10}, "ingredient_type_id": 1}],
        field: value,
    }
    async with Client(mcp) as client:
        result = await client.call_tool("save_recipe_draft", {"payload": payload}, raise_on_error=False)
    assert result.is_error
    assert field in str(result.content)
    assert not recorded_api


@pytest.mark.anyio
@pytest.mark.parametrize(
    "ingredient",
    [
        {"kind": "fixed_food", "quantity": {"mode": "grams", "value": 10}},
        {
            "kind": "fixed_food",
            "food_item_id": 1,
            "food_draft_id": 2,
            "quantity": {"mode": "grams", "value": 10},
        },
        {"kind": "generic", "quantity": {"mode": "grams", "value": 10}},
        {
            "kind": "generic",
            "ingredient_type_id": 1,
            "ingredient_type_draft_id": 2,
            "quantity": {"mode": "grams", "value": 10},
        },
        {"kind": "fixed_food", "food_item_id": 1, "quantity": {"mode": "grams"}},
        {"kind": "fixed_food", "food_item_id": 1, "quantity": {"mode": "serving_variant"}},
    ],
)
async def test_recipe_draft_rejects_invalid_ingredient_references_and_quantities_locally(
    recorded_api: list[httpx.Request], ingredient: dict[str, Any]
) -> None:
    payload = {"name": "Soup", "total_servings": 2, "ingredients": [ingredient]}
    async with Client(mcp) as client:
        result = await client.call_tool("save_recipe_draft", {"payload": payload}, raise_on_error=False)
    assert result.is_error
    assert not recorded_api


@pytest.mark.anyio
async def test_recipe_draft_update_rejects_null_expected_version_locally(recorded_api: list[httpx.Request]) -> None:
    payload = {
        "name": "Soup",
        "total_servings": 2,
        "ingredients": [{"kind": "generic", "ingredient_type_id": 1, "quantity": {"mode": "grams", "value": 10}}],
    }
    async with Client(mcp) as client:
        result = await client.call_tool(
            "update_recipe_draft",
            {"draft_id": 1, "expected_version": None, "payload": payload},
            raise_on_error=False,
        )
    assert result.is_error
    assert "expected_version" in str(result.content)
    assert not recorded_api


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


@pytest.mark.anyio
async def test_write_validation_reports_closest_union_branch_without_api_call(
    recorded_api: list[httpx.Request],
) -> None:
    malformed_recipe = {
        "name": "Soup",
        "total_servings": 2,
        "ingredients": [
            {
                "kind": "fixed_food",
                "food_item_id": 1,
                "resolution_policy": "fixed_food",
                "quantity": {"mode": "grams", "value": 10},
            }
        ],
    }
    async with Client(mcp) as client:
        result = await client.call_tool("save_recipe_draft", {"payload": malformed_recipe}, raise_on_error=False)
    assert result.is_error
    assert "payload.ingredients.0" in str(result.content)
    assert "DraftFixedIngredient" in str(result.content)
    assert "resolution_policy" in str(result.content)
    assert not recorded_api


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("tool", "payload", "field"),
    [
        (
            "save_food_draft",
            {
                "name": "Basil",
                "nutrition_input_mode": "per_100g",
                "protein_g": 1,
                "carbs_g": 2,
                "fat_g": 0,
                "fiber_g": 1,
                "basis_type": "weight",
            },
            "basis_type",
        ),
        (
            "save_generic_ingredient_draft",
            {
                "name": "Basil",
                "nutrition_input_mode": "per_100g",
                "protein_g": 1,
                "carbs_g": 2,
                "fat_g": 0,
                "fiber_g": 1,
                "created_at": "2026-09-14T00:00:00Z",
            },
            "created_at",
        ),
    ],
)
async def test_food_and_generic_writes_reject_read_only_fields_locally(
    recorded_api: list[httpx.Request], tool: str, payload: dict[str, Any], field: str
) -> None:
    async with Client(mcp) as client:
        result = await client.call_tool(tool, {"payload": payload}, raise_on_error=False)
    assert result.is_error
    assert field in str(result.content)
    assert not recorded_api
