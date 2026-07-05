"""Chat REST endpoint. Delegates all logic to app.llm.handle_chat, which loads
portfolio context, calls the LLM (or the mock), and auto-executes any trades and
watchlist changes the model returned."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel

from app.llm import handle_chat

router = APIRouter(prefix="/api/chat", tags=["chat"])


class ChatRequest(BaseModel):
    message: str


@router.post("")
async def chat(body: ChatRequest, request: Request) -> dict[str, Any]:
    return await handle_chat(
        body.message,
        request.app.state.price_cache,
        request.app.state.data_source,
    )
