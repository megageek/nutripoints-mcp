# Nutri Points MCP Server

An MCP server exposing the [Nutri Points](https://github.com/megageek/nutripoints) API's stable, scoped contract (recipes, foods, and generic-ingredient drafts) as MCP tools/resources for LLM assistants.

This repository currently holds the development container, release, and Docker packaging setup plus a placeholder server; real Nutri Points tools are not yet implemented.

## Development

Open this repository in the Dev Container (VS Code "Reopen in Container", or GitHub Codespaces). It provisions Python 3.11 with [uv](https://docs.astral.sh/uv/) and Node.js (for the MCP Inspector via `npx`, and for Commitlint).

Copy `.env.example` to `.env` and fill in a Nutri Points base URL and scoped API key before running anything against a real instance.

```bash
uv sync --extra dev   # install dependencies
uv run pytest         # run tests
uv run nutripoints-mcp  # run the server locally (HTTP transport on :8000)
```

## Running with Docker

The server is distributed as a Docker image. For local development:

```bash
cp .env.example .env   # fill in NUTRIPOINTS_BASE_URL / NUTRIPOINTS_API_KEY
docker compose up --build
```

This starts the MCP server on `http://localhost:8000/mcp`, with `http://localhost:8000/health` as a plain HTTP health check.

Released versions are published to `ghcr.io/megageek/nutripoints-mcp` via [Release Please](#releases).

## Releases

[Release Please](https://github.com/googleapis/release-please) tracks [Conventional Commits](https://www.conventionalcommits.org/) on `main` and maintains a release pull request. Merging that PR creates the version bump, `CHANGELOG.md` entry, GitHub release and tag, and triggers the GHCR image build/scan/publish. Do not create release tags manually.
