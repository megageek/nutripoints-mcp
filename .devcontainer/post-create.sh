#!/usr/bin/env bash
set -euo pipefail

if [[ -f pyproject.toml ]]; then
    uv sync --extra dev
fi

if [[ -f package.json ]]; then
    npm ci
fi

if [[ ! -f .env && -f .env.example ]]; then
    cp .env.example .env
fi

if [[ -d .githooks ]]; then
    git config core.hooksPath .githooks
fi

if [[ -f .devcontainer/hooks/post-create.sh ]]; then
    source .devcontainer/hooks/post-create.sh
fi
