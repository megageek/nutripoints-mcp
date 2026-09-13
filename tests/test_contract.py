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

    assert pin["generation"] == "stable-rw-v12"
    assert hashlib.sha256(snapshot).hexdigest() == pin["openapi_sha256"]
    assert document["openapi"].startswith("3.")
    assert "/api/v1/foods" in document["paths"]
    assert "/api/v1/recipes" in document["paths"]


def test_sync_rejects_unverified_wheel(tmp_path: Path) -> None:
    wheel = tmp_path / "contract.whl"
    with ZipFile(wheel, "w") as archive:
        archive.writestr(
            "nutripoints_api_contract/data/generations/stable-rw-v12/openapi.json",
            '{"openapi":"3.1.0","paths":{"/api/v1/foods":{}}}',
        )

    script = Path(__file__).parents[1] / "scripts/sync_contract.py"
    result = subprocess.run([sys.executable, str(script), "--wheel", str(wheel)], capture_output=True, text=True)
    assert result.returncode != 0
    assert "SHA-256 mismatch" in result.stderr
