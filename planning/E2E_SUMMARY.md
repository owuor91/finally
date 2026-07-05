# E2E (Integration) Tests — Summary

**Status:** Complete. **7/7 Playwright tests pass, stable across 5 consecutive runs**
(no flakes after the fix noted below). Run against the real FastAPI app driving a
real Chromium browser, `LLM_MOCK=true`, fresh throwaway DB per run.

**No application bugs found.** Every PLAN §12 scenario works end to end, including
the two things flagged as likely bug spots: snapshot-on-trade wiring and inline
chat-error surfacing (both verified, both correct).

## What Was Built

Everything lives in `test/` (a self-contained npm project — browser/Playwright
deps are here only, never in the production frontend/backend image, per PLAN §12).

| File | Purpose |
|------|---------|
| `test/package.json` | `@playwright/test` only. |
| `test/playwright.config.ts` | Boots the backend (fresh temp DB) and runs Chromium. `RUN_AGAINST_RUNNING=1` skips the boot and hits an already-running app (used by the compose path). |
| `test/tests/finally.spec.ts` | The 7 scenarios below, serial, one worker. |
| `test/docker-compose.test.yml` | App image (repo Dockerfile) + Playwright runner container. |
| `test/.gitignore` | Ignores `node_modules/`, `.tmp/`, results/reports. |

### Scenarios (map 1:1 to PLAN §12)

1. **Fresh start** — 10 default tickers present, `$10,000.00` cash, connection dot
   goes **Live**, and an AAPL price renders then *changes* (proves the SSE stream
   is live, not just connected).
2. **Watchlist CRUD** — add `PYPL` (appears + starts streaming a price), remove it (gone).
3. **Buy** — trade bar buy 2 AAPL; cash drops >$100, position row appears.
4. **Portfolio viz** — asserts snapshot-on-trade by reading `/api/portfolio/history`
   before/after a trade (length grows), then the heatmap renders `<rect>`s and the
   P&L chart renders a `recharts-curve` line (needs ≥2 snapshots — supplied by tests 3+4).
5. **Sell** — sell the full AAPL position; cash rises, the row disappears (qty→0 delete).
6. **AI chat (mock)** — `buy 2 AAPL` → assistant reply + inline `BUY 2 AAPL` chip +
   portfolio updates; `sell 999999 AAPL` → **`Insufficient shares` surfaces inline** (not silently dropped).
7. **SSE resilience** — dot is Live, reload interrupts the EventSource, it
   auto-reconnects back to Live.

## How To Run

### A. Direct (what I actually ran — Docker was unavailable in my sandbox)

The Docker daemon socket was permission-denied in this environment, so I used the
direct fallback the orchestrator described. Prereq: the frontend static export must
be present at `backend/static/` (it is — already built). Playwright's `webServer`
boots the backend itself with a fresh DB:

```bash
cd test
npm install
npx playwright install chromium
npx playwright test            # boots backend on :8000, fresh temp DB, runs all 7
```

The config runs: `LLM_MOCK=true FINALLY_DB_PATH=test/.tmp/e2e.db uv run --no-sync
uvicorn app.main:app` (cwd `backend/`), so every run starts from a clean $10k/empty
portfolio. No OpenRouter key needed (mock mode).

> Note: `uv` needs its real cache/home, so this must run **outside** a restrictive
> sandbox (in my env I ran it with the command sandbox disabled). Not an app issue.

### B. Docker Compose

`test/docker-compose.test.yml` builds the real app image from the repo-root
Dockerfile, runs it with `LLM_MOCK=true` and a **tmpfs `/app/db`** (fresh state per
run), then a `mcr.microsoft.com/playwright` container runs the suite against it
(`RUN_AGAINST_RUNNING=1`, `BASE_URL=http://app:8000`):

```bash
cd test
docker compose -f docker-compose.test.yml up --build --abort-on-container-exit
docker compose -f docker-compose.test.yml down -v
```

The `e2e` service exit code is the suite pass/fail. **Verified by the orchestrator**
(the integration tester's sandbox had no Docker access) — **7/7 passed** against the
real containerized app on the first successful run.

One real bug was found and fixed in this pass: the compose file pinned
`mcr.microsoft.com/playwright:v1.49.0-noble`, but `package.json` had
`"@playwright/test": "^1.49.0"` — a caret range — which had resolved to `1.61.1` in
the checked-in `package-lock.json`. The runner container's bundled Chromium (matching
the image's 1.49.0) didn't match the newer `playwright-core` installed at test time,
so `browserType.launch` failed outright (`Executable doesn't exist`). Fixed by pinning
`package.json` to the exact version the image provides (`"@playwright/test": "1.49.0"`,
no caret) and regenerating the lockfile — the same lesson DevOps hit with `uv.lock`:
a version pin only holds if *every* place that names a version agrees.

## Bugs Found

**One, in test infrastructure only (fixed) — no application bugs.**
- `test/package.json` / `docker-compose.test.yml` Playwright version drift, described
  above. Fixed.
- All 7 scenarios pass, stably, in both the direct and containerized paths. In particular:
  - **Snapshot-on-trade works** — history length grows immediately after each trade
    (asserted in test 4), so the P&L chart has data without waiting for the 30s loop.
  - **Chat error surfacing works** — a failing trade's `Insufficient shares` message
    renders in the inline chip rather than failing silently.

## One Test-Robustness Note (not an app bug)

My first draft of test 4 fired **two** trade-bar trades back-to-back; it flaked
~1-in-8 because the second Playwright `fill`+`click` occasionally raced the trade
bar's re-render (the whole page re-renders every 500ms on each SSE price tick). This
is a browser-automation timing artifact, **not** a backend or frontend defect — a
real user clicks one button at a time, and the button is `disabled` while a trade is
in flight. Fixed by having test 4 do a single trade (test 3 already supplies the
first snapshot the P&L chart needs). Worth knowing if anyone extends the suite:
**avoid rapid consecutive trade-bar interactions in one test; separate them with an
explicit wait for the portfolio to settle, or drive multiple trades via the API.**
