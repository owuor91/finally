"""Chat logic for FinAlly's AI assistant.

Plain functions, no service class. `handle_chat` is the single entry point the
`/api/chat` route calls. The LLM is reached via LiteLLM -> OpenRouter -> Cerebras
(the `cerebras` skill's pattern). When LLM_MOCK=true we skip the network entirely
and return a deterministic rule-based response for E2E tests.
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

from pydantic import BaseModel

from app.db import (
    add_watchlist_ticker,
    insert_chat_message,
    list_chat_messages,
    list_watchlist,
    remove_watchlist_ticker,
)
from app.portfolio import build_portfolio

logger = logging.getLogger(__name__)

MODEL = "openrouter/openai/gpt-oss-120b"
EXTRA_BODY = {"provider": {"order": ["cerebras"]}}
HISTORY_LIMIT = 10

SYSTEM_PROMPT = (
    "You are FinAlly, an AI trading assistant embedded in a simulated trading "
    "workstation. Analyze the user's portfolio composition, risk concentration, "
    "and P&L. Suggest trades with brief reasoning. Execute trades when the user "
    "asks or agrees, and manage the watchlist proactively. Be concise and "
    "data-driven. Market orders only, instant fill, fake money.\n\n"
    "Always respond with valid JSON matching the required schema. Put any trades "
    "to execute in `trades` and any watchlist edits in `watchlist_changes`; leave "
    "them empty when none apply."
)


class Trade(BaseModel):
    ticker: str
    side: str
    quantity: float


class WatchlistChange(BaseModel):
    ticker: str
    action: str


class LLMResponse(BaseModel):
    message: str
    trades: list[Trade] = []
    watchlist_changes: list[WatchlistChange] = []


# Mock-mode patterns (documented in LLM_SUMMARY.md for the E2E tester).
_TRADE_RE = re.compile(r"\b(buy|sell)\s+(\d+(?:\.\d+)?)\s+([A-Za-z]{1,6})\b", re.IGNORECASE)
_WATCH_RE = re.compile(r"\b(watch|unwatch)\s+([A-Za-z]{1,6})\b", re.IGNORECASE)


def _mock_response(message: str) -> LLMResponse:
    trades = [
        Trade(ticker=m.group(3).upper(), side=m.group(1).lower(), quantity=float(m.group(2)))
        for m in _TRADE_RE.finditer(message)
    ]
    changes = [
        WatchlistChange(
            ticker=m.group(2).upper(),
            action="add" if m.group(1).lower() == "watch" else "remove",
        )
        for m in _WATCH_RE.finditer(message)
    ]
    if trades or changes:
        parts = [f"{t.side} {t.quantity:g} {t.ticker}" for t in trades]
        parts += [f"{c.action} {c.ticker}" for c in changes]
        text = "Done: " + ", ".join(parts) + "."
    else:
        text = "Mock assistant reply. Set LLM_MOCK=false for real analysis."
    return LLMResponse(message=text, trades=trades, watchlist_changes=changes)


def _watchlist_view(cache: Any) -> list[dict[str, Any]]:
    out = []
    for ticker in list_watchlist():
        update = cache.get(ticker)
        out.append({"ticker": ticker, "price": update.price if update else None})
    return out


def _build_messages(
    message: str, portfolio: dict, watchlist: list[dict], history: list[dict]
) -> list[dict[str, str]]:
    context = json.dumps({"portfolio": portfolio, "watchlist": watchlist})
    messages = [{"role": "system", "content": f"{SYSTEM_PROMPT}\n\nCurrent state:\n{context}"}]
    for h in history:
        messages.append({"role": h["role"], "content": h["content"]})
    messages.append({"role": "user", "content": message})
    return messages


def _call_llm(messages: list[dict[str, str]]) -> LLMResponse:
    from litellm import completion

    try:
        response = completion(
            model=MODEL,
            messages=messages,
            response_format=LLMResponse,
            reasoning_effort="low",
            extra_body=EXTRA_BODY,
        )
        return LLMResponse.model_validate_json(response.choices[0].message.content)
    except Exception:  # noqa: BLE001 - network or malformed output must not crash the request
        logger.exception("LLM call/parse failed")
        return LLMResponse(
            message="Sorry, I ran into a problem processing that. Please try again."
        )


def _generate(message: str, portfolio: dict, watchlist: list[dict], history: list[dict]) -> LLMResponse:
    if os.getenv("LLM_MOCK") == "true":
        return _mock_response(message)
    return _call_llm(_build_messages(message, portfolio, watchlist, history))


async def handle_chat(message: str, cache: Any, data_source: Any, user_id: str = "default") -> dict:
    from app.portfolio import execute_trade

    portfolio = build_portfolio(cache, user_id=user_id)
    watchlist = _watchlist_view(cache)
    history = list_chat_messages(user_id=user_id, limit=HISTORY_LIMIT)

    insert_chat_message("user", message, user_id=user_id)

    llm = _generate(message, portfolio, watchlist, history)

    trades: list[dict[str, Any]] = []
    for t in llm.trades:
        ticker, side = t.ticker.upper(), t.side.lower()
        error = None
        try:
            execute_trade(ticker, side, t.quantity, cache, user_id=user_id)
        except ValueError as e:
            error = str(e)
        trades.append({"ticker": ticker, "side": side, "quantity": t.quantity, "error": error})

    changes: list[dict[str, str]] = []
    for w in llm.watchlist_changes:
        ticker, action = w.ticker.upper(), w.action.lower()
        if action == "add":
            add_watchlist_ticker(ticker, user_id=user_id)
            await data_source.add_ticker(ticker)
        elif action == "remove":
            remove_watchlist_ticker(ticker, user_id=user_id)
            await data_source.remove_ticker(ticker)
        else:
            continue
        changes.append({"ticker": ticker, "action": action})

    insert_chat_message(
        "assistant",
        llm.message,
        actions={"trades": trades, "watchlist_changes": changes},
        user_id=user_id,
    )

    return {"message": llm.message, "trades": trades, "watchlist_changes": changes}
