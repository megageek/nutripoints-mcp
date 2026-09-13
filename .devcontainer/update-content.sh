#!/usr/bin/env bash
set -euo pipefail

if [[ -f pyproject.toml ]]; then
    uv sync --extra dev
fi

if [[ -f package.json ]]; then
    npm ci
fi

if [[ -f .devcontainer/hooks/update-content.sh ]]; then
    source .devcontainer/hooks/update-content.sh
fi
