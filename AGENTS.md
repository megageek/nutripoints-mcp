# Nutri Points MCP Server – Agent Instructions

## Goal
Build and maintain an MCP (Model Context Protocol) server that exposes the [Nutri Points](https://github.com/megageek/nutripoints) API as tools and resources for LLM assistants, using Python and FastMCP.

## Current Stack
- Python 3.11+
- FastMCP (`fastmcp` package) for the MCP server, tools, and resources
- `httpx` as the HTTP client to the Nutri Points API
- `uv` for dependency management
- No database and no frontend — this server is a stateless bridge between MCP clients and the Nutri Points HTTP API

## Rules
- This server is not authoritative for anything: nutrition points, validation, and recipe/food state all live in Nutri Points. Never recompute, fabricate, or "helpfully" correct a value the Nutri Points API already returned or rejected.
- Write clear, small functions with type hints.
- Prefer straightforward code over abstractions.
- When a new dependency or library would materially improve correctness, reliability, maintainability, performance, developer experience, or user experience, explicitly offer it as an option before choosing a workaround. Include a brief recommendation and tradeoffs; if declined, proceed with the best workaround and clearly state resulting limitations.
- Do not silently introduce avoidable workarounds solely to bypass adding a dependency when a dependency-backed solution is cleaner and safer.
- For security-sensitive changes (auth/API-key handling, credential storage), evaluate dependency-backed security tooling (for example vulnerability scanning/SAST tooling) as a first-class option; if not adopted, document the rationale and residual risk in the same change.
- Commit completed project changes to git with a clear commit message.
- Never use timeouts or automatic resolution for questions. If you ask me a question, wait until I explicitly answer it.

## Nutri Points API Contract Consumption
- Pin to a specific Nutri Points stable contract generation (a `stable-rw-vN` entry from that repo's `contracts/` package and `docs/dev/api.md`); record the pinned generation somewhere obvious (README, a constant, or a dependency pin) and update it deliberately, not incidentally.
- Treat the pinned generation's documented request/response shapes and error codes as the contract. Do not guess at undocumented fields or behavior from a running instance; check `docs/dev/api.md` in the `nutripoints` repo (or the packaged OpenAPI/fixtures) instead.
- Only call routes that are part of the stable contract for the pinned generation. Calling an internal/unstable Nutri Points route from a tool is a deliberate exception that must be documented, since it can change without notice.
- Respect scoped API keys: this server should work correctly with a key scoped to only the tools it actually needs (`recipes:*`, `foods:*`, `ingredient-types:*`, etc.), not assume every key has wildcard (`*`) access.
- When bumping the pinned generation, review `docs/dev/api.md`'s changelog entry for that generation, update affected tool schemas/descriptions and tests in the same change, and check whether previously-working tool calls need adjustment.

## Input Validation
- Every MCP tool parameter must define an explicit type/shape and concrete length/range bounds in its schema; do not accept unbounded free text or numbers.
- A tool's declared parameter schema is a hint to the calling model, not enforcement — validate again in code before sending a request to the Nutri Points API, and return a clear tool error rather than forwarding malformed input.
- Free-text fields must reject unsupported control characters where relevant.
- Reuse shared validation helpers where available; do not introduce ad-hoc limits without a clear reason.
- Any intentional validation exception must be documented in the same change with rationale.

## Thin Tool and Resource Handlers
- Keep MCP tool/resource handler functions focused on parsing and validating the call arguments, invoking the Nutri Points API client, and formatting the MCP response.
- Put Nutri Points API request/response handling, retries, and any cross-call logic in a dedicated client/service layer, not in the tool handler itself.
- If a tool handler starts doing multi-step orchestration, aggregation across several Nutri Points calls, or error-code interpretation, extract that into a service function.
- Prefer splitting tool modules by domain (recipes, foods, ingredient types, logs) before they become a single catch-all file.

## Idempotent and Replay-Safe Tool Calls
- Prefer passing through the Nutri Points API's own `Idempotency-Key` mechanism for retry-safety rather than inventing separate dedup logic in this server.
- If a tool composes multiple Nutri Points API calls into one logical operation, make the composition's failure/retry behavior explicit (what happens if call 2 of 3 fails) rather than leaving it implicit.
- Treat retry and replay semantics as something to design deliberately for any new mutating tool, not an afterthought.

## Code Size and Structure
- Keep files reasonably small and split them by functional responsibility when they grow.
- Prefer extracting tool modules, the Nutri Points API client, and pure helper logic instead of growing coordinator files.
- Preferred file targets: tool/resource/client/service modules under 250 lines, test files under 250 lines.
- Review thresholds: tool/resource/client/service modules at 350 lines, test files at 350 lines.
- If a file crosses the review threshold, split it into functionally related parts unless there is a clear reason not to.
- Avoid arbitrary fragmentation: split by responsibility, not just by line count.
- When editing an already-large file, prefer extracting the new work instead of extending the file further.

## Test Reliability and Safety
- Freeze/mock time in tests that depend on date/time behavior.
- Avoid locale/timezone-fragile assertions unless the test is explicitly validating locale/timezone behavior.
- Do not make real network calls to a live Nutri Points instance (or any other external service) in tests; use mocks/fakes/recorded fixtures for the Nutri Points HTTP API.
- Never log or commit credentials, API keys, or full tokens in logs, fixtures, snapshots, or test artifacts.
- Do not dismiss an unexpected test failure, timeout, hang, flaky result, or runner crash because a rerun passes. Continue the active task when the failure is unrelated and the rerun succeeds, but before finishing either investigate and fix the instability when reasonably in scope or search for an existing tracking issue and update it. If none exists, create one recording the command, symptoms, environment, relevant output, and rerun outcome.
- Do not create duplicate test-stability issues, introduce automatic retries, weaken assertions, or disable tests merely to obtain a passing run.
- Cover success, validation-error, and Nutri Points API-error response paths for each tool, not just the happy path.

## Required Verification
- Run `uv run pytest` for every change.
- For every edited `.py` file, run `uv run ruff check --select E,F,I,UP,B,SIM <edited-python-files>` and fix all findings in edited files before finishing. (No `B008`/`F401` ignores yet — those exist in the `nutripoints` repo for FastAPI `Depends()` defaults and intentional model-registration imports, neither of which applies here; add an ignore only with a similarly clear, documented reason.)
- If a change affects which Nutri Points routes/scopes are used, verify manually against a real (or recorded) Nutri Points instance before considering the change done, in addition to unit tests.

## Keep In Sync
- Update `README.md` when setup, usage, configuration, or the pinned Nutri Points contract generation changes.
- Keep each tool's MCP description/docstring accurate to its actual current behavior; update it in the same change when behavior changes.
- Update tests whenever behavior changes.
- Update `AGENTS.md` when new standing repo rules are established.

## Git Workflow
- Completed changes must be committed to git.
- Use Conventional Commit messages (`feat: ...`, `fix: ...`, `feat!: ...` for breaking changes, etc.) even though Commitlint is not yet wired into CI for this repo.
- In restricted or sandboxed agent environments, if `gh auth status` reports an invalid token, retry the same check with approved network access before asking the user to reauthenticate. The GitHub CLI can misreport blocked API access as an authentication failure; only treat the token as invalid if the network-enabled check also fails.
- Do not rewrite history unless explicitly requested.
- Leave the repo in a clean state when finishing work.
- If a commit cannot be made, explain why.

## Do/Don't
- DO keep tool behavior aligned with the pinned Nutri Points stable contract generation.
- DO update automated coverage relevant to the change.
- DO document any deliberate exception (calling an unstable route, skipping a validation bound, inventing local dedup logic) in the same change.
- DON'T fabricate or locally recompute values the Nutri Points API is authoritative for.
- DON'T call unstable/internal Nutri Points routes without documenting why.
- DON'T add persistent storage without a clear, deliberate reason — this server is currently stateless by design.

## Definition of Done
- The requested tool/resource behavior is implemented.
- Any unexpected test instability encountered during the work has been fixed or recorded in an existing or new tracking issue with enough evidence to investigate.
- Any new tool input path includes validation coverage for valid input and invalid boundary/malformed input cases.
- `uv run pytest` passes.
- Edited Python files pass `uv run ruff check --select E,F,I,UP,B,SIM <edited-python-files>`.
- `README.md` and tool descriptions are updated when setup, usage, or tool behavior changes.
- Completed changes are committed to git.
