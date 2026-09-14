"""Register focused MCP tools for the pinned draft and catalog routes."""

from __future__ import annotations

from typing import Any

from fastmcp import FastMCP
from fastmcp.tools.function_tool import FunctionTool

from nutripoints_mcp import api_client
from nutripoints_mcp.contract import COMPONENTS, ID_SCHEMA, KEY_SCHEMA, OPENAPI, input_schema, validate


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
    if method != "GET":
        properties["idempotency_key"] = KEY_SCHEMA
    for key, value in properties.items():
        if key.endswith("_id") or key == "draft_id" or key == "expected_version":
            if key in required:
                properties[key] = ID_SCHEMA
            elif value.get("anyOf"):
                properties[key] = {"anyOf": [ID_SCHEMA, {"type": "null"}]}
    if method == "PUT" and "expected_version" in properties:
        required.append("expected_version")
    return properties, list(dict.fromkeys(required)), body_fields


def _add(
    mcp: FastMCP,
    name: str,
    description: str,
    method: str,
    path: str,
) -> None:
    properties, required, body_fields = _parameters(path, method)
    schema = input_schema(properties, required)
    query_fields = {
        parameter["name"] for parameter in _operation(path, method).get("parameters", []) if parameter["in"] == "query"
    }

    async def handle(**arguments: Any) -> Any:
        validate(arguments, schema)
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

    mcp.add_tool(FunctionTool(name=name, description=description, parameters=schema, fn=handle))


DOMAINS = {
    "recipe": ("/api/v1/recipes", "/api/v1/recipe-drafts", "recipe_id"),
    "food": ("/api/v1/foods", "/api/v1/food-drafts", "food_item_id"),
    "generic_ingredient": ("/api/v1/ingredient-types", "/api/v1/ingredient-type-drafts", "ingredient_type_id"),
}


def register_tools(mcp: FastMCP) -> None:
    """Expose only the stable-rw-v15 routes used by the initial workflow."""
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
            f"Save a new {domain.replace('_', ' ')} draft; pass {item_id} to edit an existing item.",
            "POST",
            drafts,
        )
        _add(
            mcp,
            f"update_{domain}_draft",
            f"Replace a {domain.replace('_', ' ')} draft using its version.",
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
        "Ask Nutri Points to validate and calculate a recipe draft.",
        "POST",
        "/api/v1/recipe-drafts/{draft_id}/validate",
    )
