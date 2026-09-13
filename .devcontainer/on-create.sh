#!/usr/bin/env bash
set -euo pipefail

for path in .venv /home/vscode/uv-cache; do
    sudo mkdir -p "$path"
    sudo chown -R vscode:vscode "$path"
done

if [[ -f .devcontainer/hooks/on-create.sh ]]; then
    source .devcontainer/hooks/on-create.sh
fi
