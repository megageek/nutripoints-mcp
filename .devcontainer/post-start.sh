#!/usr/bin/env bash
set -euo pipefail

if [[ -f .devcontainer/hooks/post-start.sh ]]; then
    source .devcontainer/hooks/post-start.sh
fi
