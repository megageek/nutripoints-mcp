"""Bounded MCP input schemas derived from the pinned Nutri Points contract."""

from __future__ import annotations

import copy
import json
import re
from datetime import date, datetime
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


def output_schema(path: str, method: str) -> dict[str, Any] | None:
    """Return a tool-compatible success schema from one contract operation.

    MCP structured output must be an object. Routes with an empty successful
    response therefore intentionally have no output schema.
    """
    responses = OPENAPI["paths"][path][method.lower()].get("responses", {})
    success = next((response for status, response in responses.items() if status.startswith("2")), None)
    if success is None:
        raise ValueError(f"Contract operation {method} {path} has no successful response")
    response_schema = success.get("content", {}).get("application/json", {}).get("schema")
    if response_schema is None:
        return None

    definitions: dict[str, Any] = {}
    schema = _inline_references(response_schema, definitions)
    schema["$defs"] = definitions
    # The only top-level unions in the pinned contract are unions of object
    # responses. Explicitly expressing that fact makes them valid MCP output
    # schemas without changing their OpenAPI alternatives.
    if "oneOf" in schema or "anyOf" in schema:
        schema.setdefault("type", "object")
    Draft202012Validator.check_schema(schema)
    return schema


def _inline_references(value: Any, definitions: dict[str, Any]) -> Any:
    """Copy an OpenAPI schema while replacing component refs with local refs."""
    if isinstance(value, list):
        return [_inline_references(item, definitions) for item in value]
    if not isinstance(value, dict):
        return value

    result = copy.deepcopy(value)
    reference = result.get("$ref")
    if reference:
        name = reference.rsplit("/", 1)[-1]
        if name not in definitions:
            definitions[name] = {}
            definitions[name] = _inline_references(COMPONENTS[name], definitions)
        result["$ref"] = f"#/$defs/{name}"
    for key, item in list(result.items()):
        if key != "$ref":
            result[key] = _inline_references(item, definitions)
    return result


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


def _parse_date(value: str, name: str) -> date:
    """Parse one documented ISO 8601 calendar date."""
    if len(value) != 10 or value[4] != "-" or value[7] != "-":
        raise ValueError(f"Invalid {name}: use an ISO 8601 date (YYYY-MM-DD)")
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise ValueError(f"Invalid {name}: use an ISO 8601 date (YYYY-MM-DD)") from error


def _parse_datetime(value: str, name: str) -> datetime:
    """Parse one documented ISO 8601 datetime without changing its value."""
    if "T" not in value:
        raise ValueError(f"Invalid {name}: use an ISO 8601 datetime")
    normalized = f"{value[:-1]}+00:00" if value.endswith("Z") else value
    try:
        return datetime.fromisoformat(normalized)
    except ValueError as error:
        raise ValueError(f"Invalid {name}: use an ISO 8601 datetime") from error


def validate_log_filters(arguments: dict[str, Any]) -> None:
    """Validate stable log-listing date and timestamp filters before a request."""
    date_from = arguments.get("date_from")
    date_to = arguments.get("date_to")
    parsed_date_from = _parse_date(date_from, "date_from") if date_from is not None else None
    parsed_date_to = _parse_date(date_to, "date_to") if date_to is not None else None
    if parsed_date_from is not None and parsed_date_to is not None and parsed_date_from > parsed_date_to:
        raise ValueError("Invalid date range: date_from must not be after date_to")

    start_at = arguments.get("start_at")
    end_at = arguments.get("end_at")
    parsed_start_at = _parse_datetime(start_at, "start_at") if start_at is not None else None
    parsed_end_at = _parse_datetime(end_at, "end_at") if end_at is not None else None
    if parsed_start_at is not None and parsed_end_at is not None:
        if (parsed_start_at.tzinfo is None) != (parsed_end_at.tzinfo is None):
            raise ValueError("Invalid datetime range: start_at and end_at must both include a UTC offset or neither")
        if parsed_start_at > parsed_end_at:
            raise ValueError("Invalid datetime range: start_at must not be after end_at")


def validate_day(arguments: dict[str, Any]) -> None:
    """Validate the date path argument for the stable day-status route."""
    _parse_date(arguments["day"], "day")
