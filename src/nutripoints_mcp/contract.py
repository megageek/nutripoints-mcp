"""Bounded MCP input schemas derived from the pinned Nutri Points contract."""

from __future__ import annotations

import copy
import json
import re
from importlib.resources import files
from typing import Any

from jsonschema import Draft202012Validator

OPENAPI = json.loads(files("nutripoints_mcp").joinpath("contracts/openapi.json").read_text())
COMPONENTS = OPENAPI["components"]["schemas"]
KEY_SCHEMA = {"type": "string", "minLength": 1, "maxLength": 128, "pattern": "^[A-Za-z0-9._:-]+$"}
ID_SCHEMA = {"type": "integer", "minimum": 1, "maximum": 9223372036854775807}
_CONTROLS = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f]")


def _bounded(value: Any, definitions: dict[str, Any]) -> Any:
    if isinstance(value, list):
        return [_bounded(item, definitions) for item in value]
    if not isinstance(value, dict):
        return value
    result = copy.deepcopy(value)
    reference = result.get("$ref")
    if reference:
        name = reference.rsplit("/", 1)[-1]
        if name not in definitions:
            definitions[name] = {}
            definitions[name] = _bounded(COMPONENTS[name], definitions)
        result["$ref"] = f"#/$defs/{name}"
    for key, item in list(result.items()):
        if key != "$ref":
            result[key] = _bounded(item, definitions)
    kind = result.get("type")
    if kind == "string":
        result.setdefault("maxLength", 20000)
    elif kind == "integer":
        result.setdefault("minimum", -9223372036854775808)
        result.setdefault("maximum", 9223372036854775807)
    elif kind == "number":
        result.setdefault("maximum", 1000000000)
        result.setdefault("minimum", -1000000000)
    elif kind == "array":
        result.setdefault("maxItems", 100)
    elif kind == "object":
        result.setdefault("additionalProperties", False)
    return result


def input_schema(properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    """Inline reachable OpenAPI definitions and add safety bounds where absent."""
    definitions: dict[str, Any] = {}
    schema = {
        "type": "object",
        "properties": _bounded(properties, definitions),
        "required": required,
        "additionalProperties": False,
        "$defs": definitions,
    }
    Draft202012Validator.check_schema(schema)
    return schema


def validate(arguments: dict[str, Any], schema: dict[str, Any]) -> None:
    """Reject malformed arguments before the API request, including control text."""
    errors = sorted(Draft202012Validator(schema).iter_errors(arguments), key=lambda error: str(error.path))
    if errors:
        error = errors[0]
        location = ".".join(map(str, error.path)) or "arguments"
        raise ValueError(f"Invalid {location}: {error.message}")

    def check_text(value: Any) -> None:
        if isinstance(value, str) and _CONTROLS.search(value):
            raise ValueError("Unsupported control character in tool input")
        if isinstance(value, dict):
            for child in value.values():
                check_text(child)
        elif isinstance(value, list):
            for child in value:
                check_text(child)

    check_text(arguments)
