"""LLM chat layer: prompt construction, the Cerebras call, structured-output
parsing, mock mode, and trade/watchlist auto-execution.

    from app.llm import handle_chat
"""

from .service import LLMResponse, handle_chat

__all__ = ["handle_chat", "LLMResponse"]
