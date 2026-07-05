"""Portfolio trading logic: trade execution and valuation.

Plain functions. `execute_trade` is the single validated path for both REST
trades and AI-initiated trades (the chat route calls it directly).

    from app.portfolio import execute_trade, build_portfolio
"""

from .service import build_portfolio, execute_trade

__all__ = ["execute_trade", "build_portfolio"]
