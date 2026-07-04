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

---

## Review — 2026-07-04 (Consolidated Design)

**Scope:** One new file, synthesizing the three prior docs plus new FastAPI wiring:
- `planning/MARKET_DATA_DESIGN.md` — 628 lines, implementation-ready spec

### Findings

**Structural & Design**

1. **Single responsibility / branching point well-enforced** ✓ — The factory pattern in §8 is correctly identified as the sole place `MASSIVE_API_KEY` branches, with all consumers downstream reading from `PriceCache`/`MarketDataSource` interface. This makes the two implementations truly substitutable at runtime.

2. **Cache design rationale is sound** — Threading.Lock over asyncio.Lock is correct for protecting `_prices` dict from both sync `_apply_snapshot` calls (Massive, via `asyncio.to_thread`) and async cache operations. The `version` counter is flagged as potentially unused (§5 note), which is accurate — currently benign, but a good future optimization candidate if not used.

3. **`SimulatorDataSource._run()` safe from prior private-attribute bug** ✓ — The fix from the prior review (adding `GBMSimulator.prices` property, line 212) is present and used correctly (line 300).

**Massive client resilience**

4. **Poll loop exception handling is strong** ✓ — §7.3's `_poll_loop` wraps every cycle in `try/except Exception`, logs, and retries. This survives transient failures (network, 5xx, rate limits) without killing the task. Single most important resilience property documented clearly.

5. **Ticker validation timing is sound** — `add_ticker` validates synchronously before joining the poll set (lines 404–410), so `POST /api/watchlist` can fail fast with a 400 for a bad ticker instead of silently polling forever. The error-in-batch case (§7.3, `_apply_snapshot`) is also handled — per-ticker errors logged, batch continues.

6. **Price fallback logic is explicit** — The `last_trade.price` → `day.close` → `prev_day.close` chain (lines 350–351, 439–440) is documented inline and handles market-hours edge cases (e.g., `last_trade` null outside hours).

**Async / concurrency**

7. **`SimulatorDataSource.stop()` correctly awaits cancellation** ✓ — Line 286 awaits the cancelled task to ensure the loop has stopped before returning, which is necessary for clean shutdown in tests. Fire-and-forget `.cancel()` alone doesn't guarantee the write loop has flushed.

8. **FastAPI lifespan wiring is complete** ✓ — §8.1 shows the cache and source attached to `app.state`, with explicit `await source.start()` before yielding and `await source.stop()` in the finally block. The note about `get_default_watchlist_tickers()` being called explicitly (rather than lazily on first request) is correct and ensures the market data loop and DB agree on initial tickers.

9. **SSE endpoint design is fit-for-purpose** — §9.1's `stream_prices` re-emits `cache.get_all()` on a fixed 500ms cadence, which matches PLAN.md §6 ("push updates for all tickers at a regular cadence"). Does not attempt per-ticker diffing (the `version` counter's reason for future optimization), which is appropriate for the current spec.

**Data model & type safety**

10. **`PriceUpdate` immutability enforced** ✓ — `frozen=True` dataclass (line 39) prevents accidental mutation and makes the object safe to share between threads/tasks.

11. **`direction_of()` helper avoids repeated derivation** ✓ — Precomputed once per update and baked into `PriceUpdate`, rather than deriving it repeatedly in consumers. Correct optimization and simplification.

12. **Missing type hints in `_apply_snapshot` signature** — Line 433 has `snapshot` parameter with no type annotation. Should be `snapshot: list` or imported Massive type if available (mildly reduces IDE/type-checker clarity but doesn't break anything since the function uses `getattr` for defensive access).

**Simulator & correlation**

13. **Correlation matrix construction is defensive** ✓ — §6.3 notes that arbitrary hand-picked correlations aren't guaranteed positive-semidefinite, and `_rebuild_cholesky` (lines 241–245) wraps the Cholesky decomposition in try/except, falling back to identity matrix on `LinAlgError`. This is exactly the right defensive stance.

14. **Shock events probability and magnitude are tuned** ✓ — §6.4's 0.1% per-tick, 2–5% magnitude (lines 249–252) introduces occasional "notable move" moments without dominating normal drift/vol-driven action. The magnitudes are sensible for a visual demo.

15. **Cholesky rebuild only on ticker changes** ✓ — O(n³) computation deferred to `add_ticker`/`remove_ticker`, not every tick (line 255 note). Correct optimization since watchlist edits are rare vs. ticks every 500ms.

**Testing & verification**

16. **Testing strategy maps cleanly to plan** ✓ — §11 lays out unit tests for simulator (price positivity, add/remove, start/stop), Massive client (mocked snapshots, error handling, poll resilience), interface conformance, and cache thread-safety. All are achievable and aligned with PLAN.md §12.

17. **Missing test for `direction_of()` edge cases** — The helper function (lines 51–56) is deterministic and simple, but the spec doesn't call out a test for it (e.g., `price == previous_price` → "flat"). Likely fine to omit from unit tests if included implicitly in cache/snapshot tests, but worth noting.

**Documentation & consistency**

18. **Cross-references to source docs and PLAN.md are complete** ✓ — §1 references PLAN.md §6–8, §7 references MASSIVE_API.md, §12 ties back to all three source docs. Navigation is clear.

19. **"No dependencies beyond numpy/stdlib/FastAPI" is accurate** ✓ — Simulator needs `numpy` only for Cholesky; Massive needs `massive` client library (external); everything else stdlib/FastAPI. `sse-starlette` mentioned in §9.1 is a soft dependency for SSE but reasonable and documented.

20. **Env var table (§10) is complete but one detail missing** — Lists `MASSIVE_API_KEY` and `LLM_MOCK`, but the table caption says "see PLAN.md §5 for the full list." Assume that list is authoritative in PLAN.md; this doc is correctly scoped to market-data-relevant vars only.

### Not re-tested against live Massive API

Same caveat as the prior review (§Review — 2026-07-04, "Not re-verified against a live API call"): Massive endpoint names and response field shapes were not exercised against a live key.

### Overall

The consolidated design is **implementation-ready and well-architected**. It synthesizes three prior docs without losing clarity, adds strong FastAPI integration guidance (lifespan, route examples), and flags all the key design decisions (single-branch factory, thread-safe cache, resilient poll loop, Cholesky rebuild optimization, stop/await semantics). All three prior bugs (private-attribute reach-through, missing logger, self-check wording) are fixed. Code sketches are correct and defensively written (exception handling, null checks, fallbacks).

Minor gaps: one untyped signature, one untested edge case, and the ongoing "is `version` dead code?" question from §5 (still acceptable, no correctness impact). No blocking issues.

---

## Code Review — 2026-07-04 (MARKET_DATA_DESIGN.md)

**Reviewer:** High-effort structural and correctness review using 8 angles (correctness, reuse, simplification, efficiency, altitude, cross-file impact, conventions, removed-behavior).

**Scope:** 628 lines, implementation-ready specification synthesizing three prior design docs plus new FastAPI integration.

### Findings

#### Correctness

1. **Proper `asyncio.Task` lifecycle in `SimulatorDataSource.stop()`** ✓ — Lines 282–288: Awaits the cancelled task to ensure the loop stops before returning. This prevents a race where `stop()` returns while the background loop is still writing to the cache, which would break clean shutdown in tests and cause "task was destroyed but it is pending" warnings. Correct pattern for cancellation cleanup.

2. **`PriceCache.get()` unsafe under concurrent removal** — Line 99–100 reads from the dict without locking, but line 106–109 shows `remove()` mutates the dict under lock. Between the caller's `update = cache.get(ticker)` check and the use of that value, another thread could call `remove(ticker)`, leaving the caller holding a stale `PriceUpdate` reference while the same ticker is removed. For the current app (single route consuming prices synchronously, no concurrent removals except by watchlist edits on the same thread), this is benign — but the pattern is fragile. *Impact: Low for current scope, medium if trade execution ever becomes concurrent or if `remove()` races with streaming reads.*

3. **`_apply_snapshot` untyped parameter increases crash surface** — Line 433: `def _apply_snapshot(self, snapshot) -> None:` has no type annotation. Line 435–437 iterates and uses `getattr` defensively, so it doesn't crash immediately, but if the Massive client returns an unexpected shape (e.g., a dict instead of a list of objects), the error bubbles up as a harder-to-debug AttributeError in the poll loop rather than a clear type error. Adding `snapshot: list[Any]` or an explicit Massive type would tighten this. *Impact: Moderate for resilience — defensive coding in `_apply_snapshot` mitigates, but better to catch shape mismatches early.*

4. **`GBMSimulator.tick()` after `remove_ticker()` may reference stale index** — Line 232 iterates over `enumerate(self._tickers)`, line 226 removes from `self._tickers` in `remove_ticker()`. If `remove_ticker()` is called from another task while `tick()` is mid-iteration, the iterator could skip or double-count tickers. *Impact: Low in practice (watchlist mutations from HTTP routes are single-threaded in FastAPI's default sync context, and `tick()` runs on the asyncio loop), but the code would benefit from making `self._tickers` immutable during a tick or taking a snapshot.* Line 230: `z = np.random.standard_normal(len(self._tickers))` — if `self._tickers` is mutated between lines 230 and 231, the vector length no longer matches the ticker count, causing an IndexError at line 236. *This is a real concurrency bug if `add_ticker`/`remove_ticker` are awaited during a tick.*

5. **`direction_of()` edge case when price equals previous_price** — Lines 51–56: Returns `"flat"` when `price == previous_price`. For floating-point values derived from GBM (which uses `exp()` and multiplication), exact equality is vanishingly rare but theoretically possible if volatility is exactly zero for a tick. For Massive API data, two consecutive snapshots *could* report the same price (e.g., no trades since last poll). The logic is correct; this is not a bug, but worth noting for test coverage (already flagged in prior review).

#### Reuse & Simplification

6. **`build_corr_matrix()` function defined but placement ambiguous** — Lines 184–192 define `build_corr_matrix()`, which is called at line 243 in `_rebuild_cholesky()`, but the function is not enclosed in a class. The doc says it should live in `seed_prices.py` (§6.2) but the code snippet shows it inline in `simulator.py`. Recommend clarifying whether this is a module-level helper in `simulator.py` or moved to `seed_prices.py`. Current placement is fine, but the doc should reflect it.

7. **`direction_of()` is a standalone function but could be inlined** — Lines 51–56 define a pure function that is called once per `PriceUpdate` (lines 310, 446). It's simple enough to inline, but extracting it as a named function improves readability and test-ability. Current approach is appropriate.

#### Efficiency

8. **`cache.get_all()` creates a full dict copy on every SSE tick** — Line 102–104: Returns `dict(self._prices)`, which is O(n) copy. Line 540 in the SSE endpoint calls this every 500ms for all connected clients. For 10 tickers this is negligible, but for 100+ tickers or hundreds of concurrent clients, the GC pressure and CPU could matter. Consider: (a) returning a reference and freezing `_prices` during iteration, or (b) using `copy.copy()` or `dict()` more efficiently. *Impact: Low for current watchlist size, medium if scaling.*

9. **Cholesky rebuild only on ticker changes is correct, but rebuild timing under load** — Lines 241–245: O(n³) Cholesky is only recomputed on ticker mutations, not every tick. Correct optimization. However, line 220 and 227 rebuild during `add_ticker`/`remove_ticker`, which are async routes — if Cholesky rebuild is slow (for n=100+ tickers), the route could timeout. *Impact: Very low for intended scale (10 tickers), but worth documenting if watchlist size grows.*

#### Altitude (Deep fixes, not surface patches)

10. **Factory pattern correctly isolates the branching decision** ✓ — Lines 467–471: The single `create_market_data_source()` function branches on `MASSIVE_API_KEY`. Every other consumer goes through the `MarketDataSource` ABC, ensuring the simulator and Massive implementations are truly interchangeable. This is well-architected — no special cases scattered through the codebase.

11. **Thread/task boundary well-separated** ✓ — The cache uses `threading.Lock` (not `asyncio.Lock`), and data sources run background `asyncio.Task`s that write to the cache via `to_thread` for the Massive client. This cleanly separates async and threaded I/O concerns. Correct altitude for the problem.

#### Cross-file impact

12. **`PriceCache.remove()` not called in SSE streaming path** ✓ — Line 295: `SimulatorDataSource` calls `remove()` on watchlist deletion. Line 415: `MassiveDataSource` also calls `remove()`. Line 540 in the SSE endpoint uses `get_all()`, which will naturally exclude removed tickers on the next tick. No hidden coupling — the route handlers own the ordering of cache removal and DB deletion.

13. **Lifespan startup assumes `get_default_watchlist_tickers()` exists** — Line 492: Calls `await get_default_watchlist_tickers()` from `backend.db`, but the doc doesn't import or define it. This is noted as "from db/ init+seed" (line 486), which is correct — it's a dependency on the database module. The doc should add a note that this function must return a list of ticker strings and must be defined in `backend/db/__init__.py` or similar, so implementers don't miss it.

#### Conventions & Documentation

14. **§8.1 lifespan wiring should include error handling example** — Lines 488–502: The lifespan context is clean, but no example of what happens if `source.start()` fails (DB unavailable, Massive API key invalid). Consider adding a note: "If `source.start()` raises, the lifespan fails, FastAPI doesn't bind `app.state`, and all routes get a 500. Route handlers should guard `request.app.state.market_data_source` access with a helper or middleware check."

15. **Snapshot error handling lacks field validation** — Lines 436–438: Checks for `getattr(s, "error", None)` but doesn't validate that `s.ticker`, `s.last_trade`, `s.day`, `s.prev_day` exist before accessing them on lines 439–440. The `getattr` defaults are defensive but incomplete. Consider: `prev = getattr(s, "prev_day", None); prev_close = getattr(prev, "close", None) if prev else None` to avoid AttributeError if the Massive API returns a partial snapshot.

#### Removed Behavior / Dropped Invariants

16. **`version` counter is documented as potentially dead code** ✓ — Line 118 flags that `version` is bumped on every `set`/`remove` but nothing reads it currently. The SSE endpoint (line 540) just re-emits on a fixed cadence, not on `version` change. This is noted as a "future diffing optimization" — appropriate to leave in place and monitor for actual use.

### Severity Assessment

**CONFIRMED bugs (correctness):**
- Finding #4 (ticker iterator race condition) — Real if `add_ticker`/`remove_ticker` are awaited during a tick, but low probability in current FastAPI single-threaded route context. Should document or fix.
- Finding #2 (get() without lock) — Benign for current single-threaded read patterns, but fragile if trade execution becomes concurrent.

**PLAUSIBLE issues (likely harmless but worth noting):**
- Finding #3 (untyped `snapshot` parameter) — Defensive coding mitigates, but type hints would improve clarity.
- Finding #15 (incomplete field validation) — Unlikely to happen if Massive API is stable, but `getattr` chains would be safer.

**Design notes (no bugs, just observations for maintenance):**
- Findings #6, #9, #13, #14.

### Overall assessment

The design is **production-ready with minor defensive improvements recommended**. The architecture is sound: single factory, clear interface, thread-safe cache, resilient polling with error recovery, and clean FastAPI integration. Code sketches are defensively written. The two real concurrency edge cases (findings #2, #4) are low-risk in the current app scope but should be documented or refactored before multi-threaded trade execution is added.

**Recommendations for implementation:**
1. Add type hint `snapshot: list[Any]` to `_apply_snapshot` (line 433).
2. Document that `cache.get()` is not safe under concurrent removal; callers should read and use synchronously or add locking.
3. Consider making `self._tickers` immutable during `tick()` in `GBMSimulator` (snapshot before iteration, or use a tuple).
4. Add error handling note to lifespan code example (what happens if `start()` fails).
5. Improve field access in `_apply_snapshot`: use nested `getattr` with defaults to handle partial snapshots gracefully.
