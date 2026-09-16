"""Register focused MCP tools for the pinned draft and catalog routes."""

from __future__ import annotations

import copy
from collections.abc import Callable
from typing import Any

from fastmcp import FastMCP
from fastmcp.tools.function_tool import FunctionTool
from mcp_types import ToolAnnotations

from nutripoints_mcp import api_client
from nutripoints_mcp.contract import (
    COMPONENTS,
    ID_SCHEMA,
    KEY_SCHEMA,
    OPENAPI,
    input_schema,
    output_schema,
    validate,
    validate_day,
    validate_log_filters,
)

ArgumentValidator = Callable[[dict[str, Any]], None]


def _operation(path: str, method: str) -> dict[str, Any]:
    return OPENAPI["paths"][path][method.lower()]


def _parameters(path: str, method: str) -> tuple[dict[str, Any], list[str], list[str]]:
    operation = _operation(path, method)
    properties: dict[str, Any] = {}
    required: list[str] = []
    body_fields: list[str] = []
    for parameter in operation.get("parameters", []):
        properties[parameter["name"]] = parameter["schema"]
        if parameter.get("required"):
            required.append(parameter["name"])
    content = operation.get("requestBody", {}).get("content", {}).get("application/json")
    if content:
        reference = content["schema"]["$ref"]
        body_schema = COMPONENTS[reference.rsplit("/", 1)[-1]]
        properties.update(body_schema["properties"])
        required.extend(body_schema.get("required", []))
        body_fields = list(body_schema["properties"])
    if method == "PUT" and "expected_version" in properties:
        required.append("expected_version")
    if method != "GET":
        properties["idempotency_key"] = KEY_SCHEMA
    for key, value in properties.items():
        if key.endswith("_id") or key == "draft_id" or key == "expected_version":
            if key in required:
                properties[key] = ID_SCHEMA
            elif value.get("anyOf"):
                properties[key] = {"anyOf": [ID_SCHEMA, {"type": "null"}]}
    return properties, list(dict.fromkeys(required)), body_fields


def _recipe_draft_step_schema(section: str) -> dict[str, Any]:
    """Return the documented step schema for one recipe draft payload field."""
    schema = copy.deepcopy(COMPONENTS["RecipeStepPayload"])
    schema["properties"]["section"] = {"const": section, "title": "Section", "type": "string"}
    return schema


def _exactly_one_reference(first: str, second: str, title: str) -> dict[str, Any]:
    """Return the documented mutually-exclusive published-or-draft reference rule."""
    return {
        "oneOf": [
            {
                "title": title,
                "required": [first],
                "properties": {first: ID_SCHEMA, second: {"type": "null"}},
            },
            {
                "title": title,
                "required": [second],
                "properties": {first: {"type": "null"}, second: ID_SCHEMA},
            },
        ]
    }


def _quantity_selection_rules(schema: dict[str, Any]) -> None:
    """Add Nutri Points' documented mode-dependent quantity requirements."""
    properties = schema["properties"]
    value_schema = next(member for member in properties["value"]["anyOf"] if member.get("type") == "number")
    schema["allOf"] = [
        {
            "if": {"properties": {"mode": {"const": "serving_variant"}}, "required": ["mode"]},
            "then": {
                "required": ["food_item_serving_id"],
                "properties": {"food_item_serving_id": ID_SCHEMA},
            },
        },
        {
            "if": {
                "properties": {"mode": {"enum": ["grams", "milliliters", "base_servings"]}},
                "required": ["mode"],
            },
            "then": {"required": ["value"], "properties": {"value": value_schema}},
        },
    ]


def _constrain_recipe_draft_payload(properties: dict[str, Any]) -> None:
    """Apply documented recipe-draft cross-field constraints missing from OpenAPI."""
    payload = copy.deepcopy(COMPONENTS["RecipeDraftPayload"])
    for field, section in (
        ("instruction_steps", "cook"),
        ("reheat_steps_fridge", "reheat_fridge"),
        ("reheat_steps_freezer", "reheat_freezer"),
    ):
        if field in payload["properties"]:
            payload["properties"][field]["items"] = _recipe_draft_step_schema(section)
    ingredient_options = payload["properties"]["ingredients"]["items"]["anyOf"]
    ingredients = [copy.deepcopy(COMPONENTS[option["$ref"].rsplit("/", 1)[-1]]) for option in ingredient_options]
    for ingredient, first, second in (
        (ingredients[0], "food_item_id", "food_draft_id"),
        (ingredients[1], "ingredient_type_id", "ingredient_type_draft_id"),
    ):
        ingredient.setdefault("allOf", []).append(_exactly_one_reference(first, second, ingredient["title"]))
        quantity_reference = ingredient["properties"]["quantity"]["$ref"]
        quantity = copy.deepcopy(COMPONENTS[quantity_reference.rsplit("/", 1)[-1]])
        _quantity_selection_rules(quantity)
        ingredient["properties"]["quantity"] = quantity
    payload["properties"]["ingredients"]["items"]["anyOf"] = ingredients
    properties["payload"] = payload


def _add(
    mcp: FastMCP,
    name: str,
    description: str,
    method: str,
    path: str,
    *,
    category: str | None = None,
    argument_validator: ArgumentValidator | None = None,
) -> None:
    properties, required, body_fields = _parameters(path, method)
    if path.startswith("/api/v1/recipe-drafts") and "payload" in body_fields:
        _constrain_recipe_draft_payload(properties)
    schema = input_schema(properties, required)
    result_schema = output_schema(path, method)
    query_fields = {
        parameter["name"] for parameter in _operation(path, method).get("parameters", []) if parameter["in"] == "query"
    }

    async def handle(**arguments: Any) -> Any:
        validate(arguments, schema)
        if argument_validator is not None:
            argument_validator(arguments)
        route = path.format(**arguments)
        params = {key: arguments[key] for key in query_fields if key in arguments and arguments[key] is not None}
        body = {key: arguments[key] for key in body_fields if key in arguments and arguments[key] is not None}
        return await api_client.request(
            method,
            route,
            params=params or None,
            body=body or None,
            idempotency_key=arguments.get("idempotency_key"),
        )

    category = category or ("read" if method == "GET" else "write")
    if category not in {"read", "write"}:
        raise ValueError(f"Unsupported tool category: {category}")
    mcp.add_tool(
        FunctionTool(
            name=name,
            description=description,
            parameters=schema,
            output_schema=result_schema,
            fn=handle,
            tags={category},
            annotations=ToolAnnotations(readOnlyHint=category == "read"),
        )
    )


DOMAINS = {
    "recipe": ("/api/v1/recipes", "/api/v1/recipe-drafts", "recipe_id"),
    "food": ("/api/v1/foods", "/api/v1/food-drafts", "food_item_id"),
    "generic_ingredient": ("/api/v1/ingredient-types", "/api/v1/ingredient-type-drafts", "ingredient_type_id"),
}

_WRITE_GUIDANCE = {
    "recipe": (
        " Writable ingredient examples: fixed food "
        '{"kind":"fixed_food","food_item_id":12,"quantity":{"mode":"grams","value":100}}; '
        "generic "
        '{"kind":"generic","ingredient_type_id":34,"resolution_policy":"generic_allowed",'
        '"quantity":{"mode":"grams","value":10}}. Put only section "cook" steps in instruction_steps; '
        "put reheat_fridge and reheat_freezer steps in their matching reheat_steps fields. "
        "For a serving variant, use "
        '{"kind":"fixed_food","food_item_id":12,"quantity":{"mode":"serving_variant",'
        '"food_item_serving_id":34,"multiplier":2}}. Step examples: '
        'instruction_steps:[{"section":"cook","body_markdown":"Cook."}], '
        'reheat_steps_fridge:[{"section":"reheat_fridge","body_markdown":"Reheat."}], and '
        'reheat_steps_freezer:[{"section":"reheat_freezer","body_markdown":"Reheat."}]. '
        "Prefer named servings over grams or milliliters when they describe the ingredient naturally: use "
        "serving_variant for a food (for example, one egg) or base_servings for a generic ingredient. "
        "Use grams or milliliters only when no suitable named serving exists. "
        "Recipe timing fields prep_time_minutes, cook_time_minutes, and passive_time_minutes are writable "
        "integers from 0 to 10080. Include them in payload when known. update_recipe_draft replaces the full "
        "recipe payload, so do not send timing fields by themselves. "
        "Recipe payloads also accept image_url and storage_life_fridge_days or storage_life_freezer_days. "
        "Storage life is an optional whole number of days from 1 to 3650; use null to clear it. "
        "When a recipe explicitly supplies a timed appliance setting or rest, add the matching automation action; "
        "durations are whole seconds. Never invent a duration, temperature, wattage, or hob level. "
        "Published ingredient reads include food_item_serving_id for serving_variant quantities. "
        "Use only payload fields in this schema; "
        "get_recipe display, nutrition, and calculated fields are read-only."
    ),
    "food": (
        ' Example payload: {"name":"Basil","nutrition_input_mode":"per_100g",'
        '"protein_g":3,"carbs_g":2,"fat_g":1,"fiber_g":2}. Add sensible serving_variants when useful, '
        'such as pinch, teaspoon, and tablespoon for a spice: {"label":"tbsp","grams":4}. Read-only IDs, '
        "timestamps, basis_type, and calculated fields must not be sent."
    ),
    "generic_ingredient": (
        ' Example payload: {"name":"Basil","nutrition_input_mode":"per_100g",'
        '"protein_g":3,"carbs_g":2,"fat_g":1,"fiber_g":2}. Add useful serving_variants when applicable, '
        'such as pinch, teaspoon, and tablespoon for a spice: {"label":"tsp","grams":5}. A base serving '
        "is also available through base_serving_label with base_serving_grams or base_serving_milliliters. Prefer "
        "creating a generic ingredient unless an exact product, brand, preparation, or nutrition requires a "
        "specific food. Read-only IDs, timestamps, basis_type, archive, and origin fields must not be sent."
    ),
}


def register_tools(mcp: FastMCP) -> None:
    """Expose only the stable-rw-v19 routes used by the initial workflow."""
    for domain, (catalog, drafts, item_id) in DOMAINS.items():
        detail_id = "food_id" if domain == "food" else item_id
        _add(
            mcp, f"search_{domain}s", f"Search saved {domain.replace('_', ' ')}s using Nutri Points q.", "GET", catalog
        )
        _add(
            mcp,
            f"get_{domain}",
            f"Read a published {domain.replace('_', ' ')} by ID.",
            "GET",
            f"{catalog}/{{{detail_id}}}",
        )
        _add(
            mcp,
            f"get_{domain}_draft_for_item",
            f"Read the current edit draft for a published {domain.replace('_', ' ')}.",
            "GET",
            f"{catalog}/{{{item_id}}}/draft",
        )
        _add(
            mcp,
            f"save_{domain}_draft",
            f"Save a new {domain.replace('_', ' ')} draft. To edit a published item, first call "
            f"get_{domain}_draft_for_item; if it returns a draft, use update_{domain}_draft with its id and version. "
            f"If no draft exists, pass {item_id} to begin an edit draft."
            f"{_WRITE_GUIDANCE[domain]} Use idempotency_key for replay-safe retries.",
            "POST",
            drafts,
        )
        _add(
            mcp,
            f"update_{domain}_draft",
            f"Replace a {domain.replace('_', ' ')} draft using its version."
            f"{_WRITE_GUIDANCE[domain]} expected_version is required and must be the draft's current version.",
            "PUT",
            f"{drafts}/{{draft_id}}",
        )
        _add(
            mcp,
            f"publish_{domain}_draft",
            f"Publish a {domain.replace('_', ' ')} draft using its version.",
            "POST",
            f"{drafts}/{{draft_id}}/publish",
        )
        _add(
            mcp,
            f"discard_{domain}_draft",
            f"Discard a {domain.replace('_', ' ')} draft.",
            "DELETE",
            f"{drafts}/{{draft_id}}",
        )
        if domain != "recipe":
            _add(
                mcp,
                f"get_{domain}_draft",
                f"Read a {domain.replace('_', ' ')} draft by draft ID.",
                "GET",
                f"{drafts}/{{draft_id}}",
            )
    _add(
        mcp,
        "validate_recipe_draft",
        "Validate and calculate an existing, saved recipe draft by draft_id. This tool does not accept recipe "
        "data or save changes: call save_recipe_draft first, then validate the returned draft_id.",
        "POST",
        "/api/v1/recipe-drafts/{draft_id}/validate",
        category="read",
    )
    for name, description, path in (
        ("list_food_logs", "List saved food logs with optional date or timestamp filters.", "/api/v1/logs/food"),
        (
            "list_activity_logs",
            "List saved activity logs with optional date or timestamp filters.",
            "/api/v1/logs/activity",
        ),
        ("list_weight_logs", "List saved weight logs with optional date or timestamp filters.", "/api/v1/logs/weight"),
    ):
        _add(mcp, name, description, "GET", path, argument_validator=validate_log_filters)
    _add(
        mcp,
        "get_weight_overview",
        "Read Nutri Points' calculated weight overview, including trends and coaching, for the selected range.",
        "GET",
        "/api/v1/weight/overview",
    )
    _add(
        mcp,
        "get_pending_weight_recap",
        "Read Nutri Points' pending weight recap without acknowledging or changing it.",
        "GET",
        "/api/v1/weight/recap/pending",
    )
    _add(mcp, "get_today", "Read Nutri Points' current-day status and ledger.", "GET", "/api/v1/days/today")
    _add(
        mcp,
        "get_day",
        "Read Nutri Points' status and ledger for one ISO 8601 calendar day.",
        "GET",
        "/api/v1/days/{day}",
        argument_validator=validate_day,
    )
