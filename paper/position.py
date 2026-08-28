from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Position:
    trade_id: str
    signal_id: str
    market_id: str
    token_id: str
    size_dollars: float
    entry_price: float
    quantity: float
    opened_at: int
    status: str = "OPEN"
    exit_price: float | None = None
    pnl: float | None = None

