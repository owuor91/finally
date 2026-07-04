## Review — 2026-07-04

**Reviewer note:** The configured Stop hook normally hands this off to an independent `codex exec` review (per `.claude/agents/change-reviewer.md`), but `codex` isn't installed in this environment and the `independent-reviewer` plugin directory referenced elsewhere is missing (likely dropped when the working tree was reset to `origin/start` mid-session). Per user direction, Claude reviewed its own new work as a one-off exception to that agent's "do not review yourself" rule.

**Scope:** three new files, no prior commit to diff against (`git status` shows only these as untracked):
- `planning/MASSIVE_API.md`
- `planning/MARKET_INTERFACE.md`
- `planning/MARKET_SIMULATOR.md`

### Findings

1. **Private-attribute reach-through (fixed)** — `MARKET_SIMULATOR.md`'s `SimulatorDataSource._run()` read `self._sim._prices` directly on `GBMSimulator`, crossing a class boundary into a private attribute (the exact issue the old, now-deleted market-data implementation had already been reviewed and fixed for, per its since-removed summary doc). Added a public `GBMSimulator.prices` property and updated the call site.

2. **Undefined `logger` (fixed)** — `MARKET_INTERFACE.md`'s `MassiveDataSource._poll_loop()` sketch called `logger.exception(...)` with no `logging` import or module-level `logger`. Added both.

3. **Self-check oversold its own coverage (fixed)** — the simulator doc's "Self-check" section claimed the test also verified correlated tickers move together more often than uncorrelated ones, but the actual snippet only asserted prices stay positive. Reworded the claim to match what the code actually checks rather than adding a statistical (and potentially flaky) assertion to back up the original claim.

4. **`PriceCache` version-per-`set()` is more machinery than the current spec needs (not changed, flagging only)** — `PLAN.md` §6 now describes SSE as "push updates for all tickers ... at a regular cadence," not a per-ticker diff. The cache's version counter (bumped on every individual `set()`, meant for change detection) is aimed at a diffing model the plan no longer asks for. It's harmless — a consumer can still just ignore `version` and read `get_all()` on a timer — but if nothing ever reads `version`, it's dead machinery. Left in place since it doesn't cost correctness and a future consumer (e.g. only re-emitting on real changes) could still use it; worth deleting if that use never materializes.

### Not re-verified against a live API call

`MASSIVE_API.md`'s endpoint names, parameters, and Python client method signatures (`get_snapshot_all`, `get_previous_close_agg`, `get_grouped_daily_aggs`, `list_universal_snapshots`) were checked against Massive's public docs and the `massive-com/client-python` GitHub source via web fetch, not by running the client against a real API key — there was none available in this session. Treat the response-field names (`last_trade.price`, `prev_day.close`, etc.) as high-confidence but unverified until exercised against a live call.

### Overall

The three docs are internally consistent with each other and with the current (simplified) `PLAN.md` — directory layout (`backend/market/`, no `app/` subpackage), the `MASSIVE_API_KEY` switch behavior, and the SSE cadence description all match. The three bugs above were sketch-level (docs contain illustrative code, not code under test) and have been corrected in place.
