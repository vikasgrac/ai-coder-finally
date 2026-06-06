# Change Review

## Findings

### [HIGH] The backend implementation was deleted while the docs still require and reference it.

The working tree deletes the entire `backend/` uv project, including `backend/pyproject.toml`, market-data interfaces, simulator, stream code, and all backend tests. Current project docs still describe a FastAPI backend as an active implementation boundary in `planning/PLAN.md` lines 90-112, and `CLAUDE.md` lines 20-26 instruct future work to build `TapetidePoller` against the same `MarketDataInterface` and shared cache as the "existing simulator." With those files removed, there is no existing interface, simulator, SSE stream, or backend test suite to extend, so the next implementation agent will either fail or recreate incompatible code.

Recommendation: restore the backend package and tests, or update the plan/agent docs to clearly state this repo has been reset to documentation-only and that backend implementation must be rebuilt from scratch.

### [HIGH] `CLAUDE.md` points agents at deleted planning files.

`CLAUDE.md` line 5 says the completed market-data component is summarized in `planning/MARKET_DATA_SUMMARY.md` with details in `planning/archive`, but this diff deletes `planning/MARKET_DATA_SUMMARY.md` and the archived market-data documents. That makes the primary agent instruction point to missing reference material exactly when agents are told to consult it.

Recommendation: either restore those docs or remove/update the reference in `CLAUDE.md`.

### [HIGH] The README was reduced to an unusable broken title.

`README.md` now contains only two lines: `# FinAlly -` and `AI Trading Workstation`. The previous quick start, architecture, environment variables, and project structure were removed. This leaves users and future agents with no repository-level setup instructions, and the heading itself is malformed.

Recommendation: restore the README content, then update only the parts that changed, such as Tapetide vs Massive and INR defaults.

### [MEDIUM] The new review agent can recurse instead of performing a review.

`.claude/agents/reviewer.md` lines 6-9 instruct the reviewer not to review the changes and instead run `Codex exec "Please review all changes in the project since the last commit and write your feedback to planning/review.md"`. That prompt is the same review task, so invoking this agent can spawn another Codex review process that may load the same instructions and repeat the delegation. It also uses `Codex` with a capital `C`, which may fail on case-sensitive systems where the CLI is `codex`.

Recommendation: make the agent perform the review directly, or change the instruction to a non-recursive command that cannot re-trigger the same agent behavior.

### [MEDIUM] The plan still contains stale Massive references despite claiming they were all replaced.

`planning/PLAN.md` line 70 still says real market data comes via Massive API, and line 168 still refers to a "Massive poller." This contradicts the new Section 13 note at line 465 saying all Massive/Polygon.io references were replaced with `TAPETIDE_API_KEY` and `TapetidePoller`.

Recommendation: replace the remaining Massive references with Tapetide wording before using the plan as an implementation contract.

## Notes

I did not run tests because the current working tree deletes the backend project and test suite, leaving no runnable implementation to validate.
