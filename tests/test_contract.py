"""The pinned contract is available in the installed server package."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from importlib.resources import files
from pathlib import Path
from zipfile import ZipFile


def test_pinned_openapi_is_packaged() -> None:
    pin = json.loads((Path(__file__).parents[1] / "contract-version.json").read_text(encoding="utf-8"))
    resource = files("nutripoints_mcp").joinpath("contracts/openapi.json")
    snapshot = resource.read_bytes()
    document = json.loads(snapshot)

    assert pin["generation"] == "stable-rw-v17"
    assert hashlib.sha256(snapshot).hexdigest() == pin["openapi_sha256"]
    assert document["openapi"].startswith("3.")
    assert "/api/v1/foods" in document["paths"]
    assert "/api/v1/recipes" in document["paths"]
    assert "/api/v1/ingredient-types" in document["paths"]
    assert "/api/v1/ingredient-types/{ingredient_type_id}" in document["paths"]
    assert "/api/v1/food-drafts" in document["paths"]
    assert "/api/v1/foods/{food_item_id}/draft" in document["paths"]
    assert "/api/v1/ingredient-types/{ingredient_type_id}/draft" in document["paths"]
    assert "food_item_serving_id" in document["components"]["schemas"]["RecipeIngredientRead"]["properties"]
    recipe_payload = document["components"]["schemas"]["RecipeDraftPayload"]["properties"]
    assert {"reheat_steps_fridge", "reheat_steps_freezer"} <= recipe_payload.keys()


def test_sync_rejects_unverified_wheel(tmp_path: Path) -> None:
    wheel = tmp_path / "contract.whl"
    with ZipFile(wheel, "w") as archive:
        archive.writestr(
            "nutripoints_api_contract/data/generations/stable-rw-v17/openapi.json",
            '{"openapi":"3.1.0","paths":{"/api/v1/foods":{}}}',
        )

    script = Path(__file__).parents[1] / "scripts/sync_contract.py"
    result = subprocess.run([sys.executable, str(script), "--wheel", str(wheel)], capture_output=True, text=True)
    assert result.returncode != 0
    assert "SHA-256 mismatch" in result.stderr
