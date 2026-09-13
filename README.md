# Nutri Points MCP Server

An MCP server exposing the [Nutri Points](https://github.com/megageek/nutripoints) API's stable, scoped contract (recipes, foods, and generic-ingredient drafts) as MCP tools/resources for LLM assistants.

This repository currently holds only the development container setup; the server itself is not yet implemented.

## Development

Open this repository in the Dev Container (VS Code "Reopen in Container", or GitHub Codespaces). It provisions Python 3.11 with [uv](https://docs.astral.sh/uv/) and Node.js (for the MCP Inspector via `npx`).

Copy `.env.example` to `.env` and fill in a Nutri Points base URL and scoped API key before running anything against a real instance.
