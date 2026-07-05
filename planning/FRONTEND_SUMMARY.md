# Frontend — Summary

**Status:** Complete. Builds to a static export, 11 unit tests passing, verified rendering in a real browser (graceful degradation with no backend).

## What Was Built

A single-page Next.js (TypeScript) trading terminal styled as a Bloomberg-like dark UI with an AI copilot. Configured for **static export** (`output: 'export'`) so FastAPI can serve the built `out/` directory from one origin — no Node runtime, no API routes, no CORS.

All API/SSE calls hit the same origin (`/api/*`). The app runs and renders fully **without** a backend: fetches fail silently into empty states, the connection dot goes red, and the watchlist falls back to the 10 default tickers.

### Tech choices (deliberately minimal)
- **State**: React `useState`/`useCallback` only — no Redux/Zustand.
- **Styling**: Tailwind CSS, custom dark theme. No component library.
- **Charts**: Recharts only (`LineChart` for the main + P&L charts, `Treemap` for the heatmap). Sparklines are a hand-rolled inline SVG `<polyline>` — no second charting lib.
- **Live data**: native `EventSource` (auto-reconnect) via the `usePrices` hook.
- **Tests**: Vitest + React Testing Library + jsdom.

## Directory Structure

```
frontend/
├── package.json            # next 14.2.35, react 18, recharts 2, vitest
├── next.config.mjs         # output: 'export', images.unoptimized
├── tailwind.config.ts      # theme colors (accent/blue/purple/up/down)
├── vitest.config.ts        # jsdom env, @ alias -> src
├── vitest.setup.ts         # jest-dom matchers + scrollIntoView stub
├── src/
│   ├── app/
│   │   ├── layout.tsx
│   │   ├── page.tsx        # composes everything, owns all state + data fetching
│   │   └── globals.css     # flash-up / flash-down keyframes
│   ├── lib/
│   │   ├── types.ts        # all API/SSE shapes (see assumptions below)
│   │   ├── api.ts          # fetch wrappers for every /api endpoint
│   │   ├── usePrices.ts    # EventSource hook: prices + sparkline history + conn status
│   │   └── format.ts       # usd / pct / num / pnlColor helpers
│   ├── components/
│   │   ├── Header.tsx            # total value, cash, P&L, connection dot
│   │   ├── Watchlist.tsx         # rows + add input + per-row remove
│   │   ├── PriceCell.tsx         # green/red flash-fade on price change
│   │   ├── Sparkline.tsx         # inline SVG polyline
│   │   ├── MainChart.tsx         # selected ticker price-over-time (Recharts)
│   │   ├── PnLChart.tsx          # portfolio value over time (Recharts)
│   │   ├── PortfolioHeatmap.tsx  # treemap sized by value, colored by P&L
│   │   ├── PositionsTable.tsx    # live P&L recomputed from SSE feed
│   │   ├── TradeBar.tsx          # ticker + qty + Buy/Sell, instant fill
│   │   └── ChatPanel.tsx         # collapsible AI sidebar w/ inline confirmations
│   └── __tests__/          # priceflash, watchlist, positions, chat
```

## API Assumptions (BACKEND: match these or flag mismatches)

The SSE format and `PriceUpdate` shape are taken from the real `backend/app/market` code, so those are firm. The REST response shapes below are **my assumptions** where PLAN.md §8 left them unspecified — please match them or tell me to change.

### SSE — `GET /api/stream/prices` (firm, matches existing backend)
Each event's `data:` is a JSON **object keyed by ticker** (not one ticker per event):
```json
{ "AAPL": {"ticker":"AAPL","price":190.5,"previous_price":189.0,
           "timestamp":1699,"change":1.5,"change_percent":0.79,"direction":"up"}, ... }
```

### `GET /api/portfolio`
```json
{
  "cash_balance": 10000.0,
  "positions_value": 0.0,
  "total_value": 10000.0,
  "total_unrealized_pnl": 0.0,
  "positions": [
    { "ticker": "AAPL", "quantity": 10, "avg_cost": 100.0,
      "current_price": 190.5, "market_value": 1905.0,
      "unrealized_pnl": 905.0, "unrealized_pnl_percent": 90.5 }
  ]
}
```
The header's P&L % is derived as `total_unrealized_pnl / (positions_value − total_unrealized_pnl) * 100`.

### `POST /api/portfolio/trade`
Request `{ "ticker": "AAPL", "quantity": 10, "side": "buy" }`. Response body is ignored — the frontend refetches `/api/portfolio` after. On failure return a non-2xx with `{"detail": "..."}` or `{"error": "..."}`; the message is surfaced in the trade bar.

### `GET /api/portfolio/history`
Array (or `{"snapshots":[...]}` — both tolerated) of:
```json
[ { "total_value": 10000.0, "recorded_at": "2026-07-05T12:00:00Z" } ]
```

### `GET /api/watchlist`
Array of tickers, tolerant of these shapes: `["AAPL","GOOGL"]`, `[{"ticker":"AAPL"}]`, or `{"watchlist":[...]}`. Only the ticker symbol is used — **live prices come from the SSE feed, not this endpoint.** If it returns empty the frontend keeps the 10 defaults.

### `POST /api/watchlist` / `DELETE /api/watchlist/{ticker}`
POST body `{ "ticker": "PYPL" }`. Both are fire-and-forget with optimistic UI (local update first, resync on error).

### `POST /api/chat`
Request `{ "message": "buy 5 nvda" }`. Response per PLAN.md §9:
```json
{ "message": "Bought 5 NVDA.",
  "trades": [ {"ticker":"NVDA","side":"buy","quantity":5, "error": null} ],
  "watchlist_changes": [ {"ticker":"PYPL","action":"add"} ] }
```
`trades`/`watchlist_changes` are optional. A per-trade `error` string (if present) renders the chip red. After each chat reply the frontend resyncs portfolio + watchlist. Chat history is **frontend-only per page load** (no `GET /api/chat` is called).

## Notable Behaviors
- **Price flash**: `PriceCell` compares to its previous price and remounts via `key` to restart the CSS animation on every tick.
- **Sparklines / main chart**: accumulated on the client from SSE since page load (capped at 120 points); they fill in progressively.
- **Positions table** recomputes current price / P&L live from the SSE feed between the 15s portfolio refreshes, falling back to server values.
- **Polling**: portfolio + history refetch every 15s and immediately after any trade or chat action.

## Run

```bash
cd frontend
npm install
npm run dev      # http://localhost:3000 (dev)
npm run build    # static export -> frontend/out/  (this is what FastAPI serves)
npm test         # vitest (11 tests)
```

## Known / Deferred
- Two `npm audit` advisories remain inside Next 14's own bundled tree (a bundled `postcss`); clearing them needs a Next 16 major upgrade, out of scope here. The direct high-severity Next advisory (2025-12-11) is patched by pinning `next@14.2.35`.
