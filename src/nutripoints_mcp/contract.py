"""Bounded MCP input schemas derived from the pinned Nutri Points contract."""

from __future__ import annotations

import copy
import json
import re
from importlib.resources import files
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

OPENAPI = json.loads(files("nutripoints_mcp").joinpath("contracts/openapi.json").read_text())
COMPONENTS = OPENAPI["components"]["schemas"]
KEY_SCHEMA = {"type": "string", "minLength": 1, "maxLength": 128, "pattern": "^[A-Za-z0-9._:-]+$"}
ID_SCHEMA = {"type": "integer", "minimum": 1, "maximum": 9223372036854775807}
_CONTROLS = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f]")


def _is_object_union_member(value: Any) -> bool:
    """Return whether an OpenAPI union branch resolves to an object schema."""
    if not isinstance(value, dict):
        return False
    reference = value.get("$ref")
    if reference:
        return COMPONENTS[reference.rsplit("/", 1)[-1]].get("type") == "object"
    return value.get("type") == "object"


def _bounded(value: Any, definitions: dict[str, Any]) -> Any:
    if isinstance(value, list):
        return [_bounded(item, definitions) for item in value]
    if not isinstance(value, dict):
        return value
    result = copy.deepcopy(value)
    if (
        "anyOf" in result
        and len(result["anyOf"]) > 1
        and all(_is_object_union_member(member) for member in result["anyOf"])
    ):
        # The API's object alternatives are discriminated by const fields.  oneOf
        # conveys that fact to MCP clients more clearly than OpenAPI's anyOf.
        result["oneOf"] = result.pop("anyOf")
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


def _location(error: ValidationError) -> str:
    return ".".join(map(str, error.absolute_path)) or "arguments"


def _union_message(error: ValidationError) -> str | None:
    """Describe the closest object-union branch instead of a generic anyOf error."""
    if error.validator not in {"anyOf", "oneOf"} or not error.context:
        return None
    branches: dict[int, list[ValidationError]] = {}
    for child in error.context:
        branch = next((part for part in child.schema_path if isinstance(part, int)), None)
        if branch is not None:
            branches.setdefault(branch, []).append(child)
    if not branches:
        return None
    _, problems = min(branches.items(), key=lambda item: len(item[1]))
    title = problems[0].schema.get("title", "matching")
    details = "; ".join(problem.message for problem in problems[:3])
    return f"Invalid {_location(error)} for {title}: {details}"


def _validation_message(error: ValidationError) -> str:
    union_message = _union_message(error)
    if union_message:
        return union_message
    return f"Invalid {_location(error)}: {error.message}"


def validate(arguments: dict[str, Any], schema: dict[str, Any]) -> None:
    """Reject malformed arguments before the API request, including control text."""
    errors = sorted(Draft202012Validator(schema).iter_errors(arguments), key=lambda error: str(error.path))
    if errors:
        raise ValueError(_validation_message(errors[0]))

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
