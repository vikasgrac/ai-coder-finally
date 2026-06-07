# Review

Scope: changes in the working tree since `0913790`.

## Findings

### [HIGH] Quick Start points to files that do not exist

`README.md:16` tells users to copy `.env.example`, and `README.md:18`-`README.md:19` / `README.md:49`-`README.md:50` tell them to run start/stop scripts under `scripts/`. None of `.env.example`, `scripts/start_mac.sh`, `scripts/start_windows.ps1`, `scripts/stop_mac.sh`, or `scripts/stop_windows.ps1` exist in this working tree. The updated README has become the repo entrypoint, so the first setup path now fails immediately.

Recommendation: either add the documented env example and scripts in the same change, or rewrite the README as a specification/status document until those files exist.

### [HIGH] New market-data docs reintroduce the obsolete Massive/US-market contract

`planning/market_interface.md:3`, `planning/market_interface.md:117`-`planning/market_interface.md:128`, `planning/market_interface.md:159`-`planning/market_interface.md:180`, and `planning/market_interface.md:331`-`planning/market_interface.md:344` specify `MassivePoller`, `MASSIVE_API_KEY`, Polygon endpoints, and US equity behavior. The new `planning/Massive_API.md:1`-`planning/Massive_API.md:20` doubles down on the same API/key contract. This directly contradicts the active plan, which says `TAPETIDE_API_KEY` selects Tapetide for NSE/BSE data (`planning/PLAN.md:126`-`planning/PLAN.md:137`) and claims all Massive/Polygon references were replaced (`planning/PLAN.md:463`-`planning/PLAN.md:465`). An implementation agent following these new docs will build the wrong provider and environment-variable switch.

Recommendation: remove the Massive API reference docs or archive them clearly as obsolete, and update `market_interface.md` to define `TapetidePoller`, `TAPETIDE_API_KEY`, FastMCP usage, and NSE/BSE response shapes.

### [HIGH] Stop hook can run an expensive mutating review after every Claude response

`independent-reviewer/hooks/hooks.json:2`-`independent-reviewer/hooks/hooks.json:8` registers an unfiltered global `Stop` hook that runs `codex exec "Review changes since last commit and write results to planning/REVIEW.md"`. Once installed, any Claude stop in this project can spawn Codex, spend tokens, and rewrite the working tree, even for unrelated tasks. Because the command reviews "changes since last commit" and writes into the same diff it reviews, repeated stops can also cause review-output churn that obscures the user's actual changes.

Recommendation: move this behind an explicit command, or add a wrapper that inspects the hook payload and exits unless the current stop event is specifically requesting the independent review workflow. Also exclude the generated review file from the reviewed diff or write it to an ignored generated path.

### [MEDIUM] Review output path changes only by case from the tracked file

Git tracks `planning/review.md`, but the new marketplace description and hook use `planning/REVIEW.md` (`.claude-plugin/marketplace.json:9`, `independent-reviewer/hooks/hooks.json:8`). On the default case-insensitive macOS filesystem this silently modifies the tracked lowercase file, while on a case-sensitive filesystem it can create a separate uppercase file. That makes plugin output and references platform-dependent.

Recommendation: keep the existing lowercase path everywhere, or perform an explicit case-only rename and update all references in one commit.

### [LOW] Plugin description has a visible typo

`independent-reviewer/.claude-plugin/plugin.json:3` says `independentlyreviews` without a space. This is cosmetic, but it will show up in plugin listings and makes the new plugin look unfinished.

Recommendation: change it to `independently reviews`.

## Notes

I did not run tests because the working tree changes are documentation and hook/plugin configuration only, and there is no app or test target present in the repository to execute.
