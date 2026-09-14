#!/usr/bin/env bash
set -euo pipefail

# CI uses a dummy upstream URL: /health must work without calling Nutri Points.
export NUTRIPOINTS_BASE_URL=http://127.0.0.1:19999
export NUTRIPOINTS_API_KEY=smoke-only

for ((attempt = 0; attempt < 30; attempt++)); do
	if docker info >/dev/null 2>&1; then
		break
	fi
	sleep 1
done

docker version
docker compose version
docker compose config --quiet

trap 'docker compose down --remove-orphans' EXIT
docker compose up --build --detach

# The container can accept then reset a connection while FastMCP is starting.
# Retry every transient probe failure until the service reports ready.
for ((attempt = 0; attempt < 30; attempt++)); do
	if curl --fail --silent --output /dev/null http://127.0.0.1:8000/health; then
		exit 0
	fi
	sleep 1
done

docker compose logs --no-color mcp
exit 1
