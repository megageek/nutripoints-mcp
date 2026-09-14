"""HTTP client for stable Nutri Points routes."""

from __future__ import annotations

import os
from typing import Any

import httpx


class NutriPointsAPIError(Exception):
    """A transport or Nutri Points API failure suitable for an MCP tool error."""


def _format_error_detail(detail: Any) -> Any:
    """Make contract-standard validation details readable without dropping fields."""
    if not isinstance(detail, list) or not all(isinstance(item, dict) for item in detail):
        return detail
    formatted = []
    for item in detail:
        if {"loc", "msg", "type"}.issubset(item):
            location = ".".join(map(str, item["loc"])) or "body"
            formatted.append(f"{location}: {item['msg']} ({item['type']})")
        else:
            formatted.append(str(item))
    return "; ".join(formatted)


async def request(
    method: str,
    path: str,
    *,
    params: dict[str, Any] | None = None,
    body: dict[str, Any] | None = None,
    idempotency_key: str | None = None,
) -> Any:
    """Send one scoped, authenticated request and return the API's JSON unchanged."""
    base_url = os.environ.get("NUTRIPOINTS_BASE_URL", "").rstrip("/")
    api_key = os.environ.get("NUTRIPOINTS_API_KEY", "")
    if not base_url or not api_key:
        raise NutriPointsAPIError("NUTRIPOINTS_BASE_URL and NUTRIPOINTS_API_KEY must be configured")
    headers = {"Authorization": f"Bearer {api_key}"}
    if idempotency_key:
        headers["Idempotency-Key"] = idempotency_key
    try:
        async with httpx.AsyncClient(base_url=base_url, timeout=20.0) as client:
            response = await client.request(method, path, params=params, json=body, headers=headers)
    except httpx.RequestError as error:
        raise NutriPointsAPIError(f"Nutri Points request failed: {type(error).__name__}") from error
    if response.is_error:
        try:
            error_body = response.json()
            detail = error_body.get("detail", error_body) if isinstance(error_body, dict) else error_body
            detail = _format_error_detail(detail)
        except ValueError:
            detail = response.text
        raise NutriPointsAPIError(f"Nutri Points HTTP {response.status_code}: {detail}")
    if response.status_code == 204 or not response.content:
        return None
    try:
        return response.json()
    except ValueError as error:
        raise NutriPointsAPIError("Nutri Points returned invalid JSON") from error
