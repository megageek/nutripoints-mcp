# Nutri Points MCP Server

An MCP server exposing the [Nutri Points](https://github.com/megageek/nutripoints) API's stable, scoped contract (recipes, foods, and generic-ingredient drafts) as MCP tools/resources for LLM assistants.

This repository currently holds the development container, release, and Docker packaging setup plus a placeholder server; real Nutri Points tools are not yet implemented.

## API contract

The server is pinned to Nutri Points `stable-rw-v12` through the public
[`nutripoints-api-contracts` v12.0.0 release](https://github.com/megageek/nutripoints-api-contracts/releases/tag/v12.0.0).
The pinned version and wheel SHA-256 are recorded in `contract-version.json`. Its
OpenAPI document is checked into `src/nutripoints_mcp/contracts/openapi.json` and
included in the Python package and Docker image, so development and runtime do not
depend on GitHub availability. The snapshot is the source for future MCP tool
schemas; the detailed contract and generation changelog are in
[`docs/dev/api.md`](https://github.com/megageek/nutripoints/blob/main/docs/dev/api.md).

To refresh the snapshot after deliberately updating the pin and reviewing that
generation's changelog, run `python scripts/sync_contract.py`. The script verifies
the release wheel's SHA-256 before extracting OpenAPI. For local cross-repository
development, pass `--wheel path/to/nutripoints_api_contracts-<version>-py3-none-any.whl`.
Update affected tools and tests in the same change when advancing the generation.

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
