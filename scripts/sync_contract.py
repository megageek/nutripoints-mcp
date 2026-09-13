"""Refresh the checked-in OpenAPI snapshot from a verified contract release."""

from __future__ import annotations

import argparse
import hashlib
import json
import urllib.request
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
PIN = ROOT / "contract-version.json"
SNAPSHOT = ROOT / "src/nutripoints_mcp/contracts/openapi.json"


def sync_contract(wheel: Path | None = None) -> None:
    """Extract the pinned generation only after verifying the release wheel."""
    pin = json.loads(PIN.read_text(encoding="utf-8"))
    version = pin["release"]
    asset = f"nutripoints_api_contracts-{version}-py3-none-any.whl"
    if wheel is None:
        url = f"https://github.com/megageek/nutripoints-api-contracts/releases/download/v{version}/{asset}"
        with urllib.request.urlopen(url) as response:
            wheel_bytes = response.read()
    else:
        wheel_bytes = wheel.read_bytes()

    digest = hashlib.sha256(wheel_bytes).hexdigest()
    if digest != pin["wheel_sha256"]:
        raise ValueError(f"Contract wheel SHA-256 mismatch: expected {pin['wheel_sha256']}, got {digest}")

    member = f"nutripoints_api_contract/data/generations/{pin['generation']}/openapi.json"
    with ZipFile(BytesIO(wheel_bytes)) as archive:
        snapshot = archive.read(member)
    if hashlib.sha256(snapshot).hexdigest() != pin["openapi_sha256"]:
        raise ValueError("Contract OpenAPI SHA-256 mismatch")
    document = json.loads(snapshot)
    if not document.get("openapi", "").startswith("3.") or not document.get("paths"):
        raise ValueError("Contract release does not contain a usable OpenAPI document")
    SNAPSHOT.write_bytes(snapshot)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheel", type=Path, help="Use a local wheel instead of downloading the release")
    args = parser.parse_args()
    sync_contract(args.wheel)


if __name__ == "__main__":
    main()
