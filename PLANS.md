# Plans

## Deferred: daily status and food logging

**Contract:** Nutri Points `stable-rw-v17`

**Blocker:** The available API key does not have the scopes required for these routes. Do not implement or exercise them against a live instance until a suitably scoped key is available.

Add MCP tools to read today's status, read a specified day's status, list food logs, and create, update, and delete food logs. Use only the corresponding routes in the pinned stable contract. Keep Nutri Points authoritative: return its status, nutrition, points, validation results, and errors without recalculation or correction.

Before implementation, confirm the exact route scopes and request/response behavior in the pinned contract documentation and obtain a key with only the necessary scopes. Define bounded schemas for every tool input and validate calls before sending them upstream, including dates, timestamps, and malformed text. Pass an optional `Idempotency-Key` through on mutating calls; do not add local deduplication.

Add recorded-response tests for successful calls, invalid inputs, and Nutri Points API errors, including `setup_blocked` day status and replay-key forwarding. Update the README and server instructions with the new workflow and required scopes. Run `uv run pytest` and the required Ruff format and lint checks for edited Python files. If route or scope usage changes, verify it manually against a recorded or real Nutri Points instance as required by `AGENTS.md`.
