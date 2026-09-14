# Nutri Points MCP Server

An MCP server exposing the [Nutri Points](https://github.com/megageek/nutripoints) API's stable, scoped recipe, food-item, and generic-ingredient draft workflow as MCP tools.

Tools search saved recipes, food items, and generic ingredients; read published items and drafts; and save, update, publish, or discard drafts. Recipe drafts can also be validated before publishing. Each write is a separate call, so callers can review the draft and its version before publication. Nutri Points calculates nutrition and points.

The MCP server sends workflow instructions when a client connects. They direct assistants to search for reusable recipes and ingredients before creating new ones, inspect candidate details, and prefer generic ingredients for reusable categories. A specific food item is appropriate when an exact product or its nutrition matters. Assistants should request missing nutrition facts and use Nutri Points' draft validation and calculated values; these instructions guide the assistant and do not block tool calls.

## API contract

The server is pinned to Nutri Points `stable-rw-v15` through the public
[`nutripoints-api-contracts` v15.0.0 release](https://github.com/megageek/nutripoints-api-contracts/releases/tag/v15.0.0).
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

The Dev Container also installs Docker Engine, the Docker CLI, Buildx, and Compose through the [Docker-in-Docker feature](https://github.com/devcontainers/features/tree/main/src/docker-in-docker). Rebuild the Dev Container after changing this configuration, then run `docker version` and `docker compose version` inside it. Its Docker daemon is separate from the host daemon and requires a host that allows privileged Dev Containers. To deploy beside an existing Nutri Points container on another Docker host, run Compose on that host or select a Docker context for it. Dev Container CI builds the Compose service and checks `/health`.

Copy `.env.example` to `.env` and fill in a Nutri Points base URL and scoped API key before running anything against a real instance.
For all tools, the key needs `recipes:read`, `recipes:write`, `foods:read`, `foods:write`, `ingredient-types:read`, and `ingredient-types:write`; a narrower key works for the tools in its domain. API errors, including version conflicts and missing items, are returned as tool errors. Mutating tools accept an optional `idempotency_key` for replay-safe retries.

Search tools pass `q` to Nutri Points (up to 120 characters). Food-item and generic-ingredient searches also accept `include_archived`. To edit an existing item, save a draft with its item ID, update that draft using its returned `id` and `version`, then publish it with the current version. To create a new item, omit the item ID. Recipe drafts can reference published or caller-owned draft ingredients; Nutri Points validation reports required next actions before publication.

For example, `search_generic_ingredients` with `{"q":"basil"}` finds saved generic ingredients. `save_generic_ingredient_draft` with a complete `payload` returns a draft `id` and `version`; `publish_generic_ingredient_draft` then takes those as `draft_id` and `expected_version`. The same tool naming applies to `recipe` and `food` drafts. Search results and published detail reads come directly from Nutri Points.

The API key stays in process memory and is sent only in the Bearer header to the configured base URL; the server does not log it. Existing CI runs Semgrep, Gitleaks, Trivy, and `pip-audit`, so this change adds no separate security-scanning dependency. An HTTP base URL transmits the key without TLS; use HTTPS for a remote instance.

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
