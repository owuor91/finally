# LLM Chat Layer — Summary

**Status:** Complete. 129 tests pass (115 prior + 14 new), ruff-clean. Built and
tested against `LLM_MOCK=true` (no `OPENROUTER_API_KEY` in this env); parsing and
malformed-output handling unit-tested with fixture JSON.

## What Was Built

The AI chat feature: `POST /api/chat` loads portfolio context, calls the LLM
(LiteLLM → OpenRouter → `openrouter/openai/gpt-oss-120b` via Cerebras, using the
`cerebras` skill's pattern), parses structured output, and auto-executes any
trades / watchlist changes the model returned.

| File | Purpose |
|------|---------|
| `backend/app/llm/service.py` | All chat logic: prompt build, Cerebras call, structured-output parsing, mock mode, trade/watchlist auto-execution. `handle_chat(...)` is the entry point. |
| `backend/app/llm/__init__.py` | Re-exports `handle_chat`, `LLMResponse`. |
| `backend/app/routes/chat.py` | `POST /api/chat` route, delegates to `handle_chat`. |
| `backend/tests/llm/test_chat.py` | 14 tests. |
| `backend/app/main.py` | One added line: `app.include_router(chat.router)` (+ import). |
| `backend/pyproject.toml` | Added `litellm>=1.51.0` (the only new dependency). |

## `/api/chat` request / response

Matches `FRONTEND_SUMMARY.md` exactly — no deviation.

**Request:** `{"message": "buy 5 nvda"}`

**Response:**
```json
{
  "message": "Done: buy 5 NVDA.",
  "trades": [{"ticker": "NVDA", "side": "buy", "quantity": 5, "error": null}],
  "watchlist_changes": [{"ticker": "PYPL", "action": "add"}]
}
```
- `trades[].error` is `null` on success, a user-facing string on validation
  failure (surfaced from `execute_trade`'s `ValueError`, verbatim — the chip
  renders red).
- `trades` / `watchlist_changes` are always present (empty arrays when none).

## Flow (per PLAN §9)

1. `build_portfolio(cache)` + a compact `[{ticker, price}]` watchlist view from
   the cache → JSON context appended to the system prompt.
2. `list_chat_messages(limit=10)` → recent history as prior turns.
3. System prompt: "FinAlly, an AI trading assistant" (analyze portfolio/risk/P&L,
   suggest trades with reasoning, execute when asked/agreed, manage watchlist,
   concise + data-driven, always valid JSON).
4. LLM call with `response_format=LLMResponse` (Pydantic), `reasoning_effort="low"`,
   `extra_body={"provider": {"order": ["cerebras"]}}`.
5. Per requested trade → **one** `execute_trade(...)` call (the single validated
   path — no reimplemented validation); `ValueError` caught into the `error` field.
6. Per watchlist change → `add`: `add_watchlist_ticker` + `await data_source.add_ticker`;
   `remove`: the remove pair. Unknown actions skipped.
7. User + assistant messages persisted via `insert_chat_message`; the assistant
   row's `actions` = `{"trades": [...], "watchlist_changes": [...]}` (the executed
   results). History is stored for PLAN compliance / debugging even though the
   frontend keeps its own per-page-load history.

## Mock mode (`LLM_MOCK=true`)

No network, fully deterministic — this is what the E2E tester should rely on.
Regex-scans the user message (case-insensitive):

| Pattern | Produces |
|---------|----------|
| `buy <n> <TICKER>` | a `buy` trade (n shares) |
| `sell <n> <TICKER>` | a `sell` trade |
| `watch <TICKER>` | watchlist `add` |
| `unwatch <TICKER>` | watchlist `remove` |

`<n>` may be fractional; `<TICKER>` is 1–6 letters. Multiple matches in one
message all fire (e.g. `"buy 1 AAPL and buy 2 MSFT"` → two trades). With any
match the reply is `"Done: buy 5 NVDA, add PYPL."`; with none it's a fixed canned
message. Trades still go through real `execute_trade` validation, so e.g.
`"buy 100000 NVDA"` returns a trade with a populated `error`.

## Malformed / failed real LLM output

`_call_llm` wraps the call + parse in a broad catch: on a network error or output
that doesn't validate against the schema, it logs and returns a safe fallback
(`message="Sorry, I ran into a problem processing that. Please try again."`, no
trades). The request never crashes and no partial/garbage trades execute.

## Tests

`backend/tests/llm/test_chat.py` — parsing (full schema, message-only defaults,
malformed → fallback, network error → fallback), mock determinism (buy/sell,
watch/unwatch, canned), and route behavior via `TestClient` with a seeded
`PriceCache` + fake async source on `app.state` and `LLM_MOCK=true`: trade
execution moves cash, multiple trades, validation error surfaced in `error`,
watchlist add/remove hit the data source, history persisted with actions, plain
message yields no actions.

```bash
cd backend
uv run --extra dev pytest -q          # 129 passed
uv run --extra dev ruff check app tests
```
