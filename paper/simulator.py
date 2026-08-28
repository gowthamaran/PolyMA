from __future__ import annotations

import json
import uuid
from dataclasses import asdict
from typing import Any

from app.database import Database
from paper.account import PaperAccount
from paper.execution_model import ExecutionModel
from strategy.signals import Signal


class PaperSimulator:
    def __init__(self, database: Database, account: PaperAccount, execution: ExecutionModel):
        self.database = database
        self.account = account
        self.execution = execution

    def position_size(self, mode: str, configured_size: float, confidence: float | None = None) -> float:
        if mode == "fixed_percentage":
            return min(self.account.get_balance() * configured_size / 100, self.account.limits.max_trade_size)
        if mode == "confidence":
            factor = max(0.25, min(1.0, confidence or 0.5))
            return min(configured_size * factor, self.account.limits.max_trade_size)
        return min(configured_size, self.account.limits.max_trade_size)

    def open(
        self,
        signal: Signal | dict[str, Any],
        size_dollars: float,
        complementary_ask: float | None = None,
    ) -> str | None:
        row = signal.as_dict() if isinstance(signal, Signal) else signal
        allowed, _reason = self.account.can_open(size_dollars)
        if not allowed:
            return None
        entry = self.execution.entry_price(float(row["close"]), complementary_ask)
        quantity = size_dollars / entry
        trade_id = f"paper-{uuid.uuid4().hex[:20]}"
        assumptions = asdict(self.execution.assumptions) | {
            "price_model": "OBSERVED_COMPLEMENT_ASK" if complementary_ask is not None else "SYNTHETIC_COMPLEMENT_1_MINUS_TARGET",
            "real_order_submitted": False,
        }
        with self.database.transaction() as connection:
            cursor = connection.execute(
                """INSERT OR IGNORE INTO paper_trades
                (trade_id, signal_id, market_id, token_id, status, side, size_dollars,
                entry_price, quantity, opened_at, assumptions_json)
                VALUES (?, ?, ?, ?, 'OPEN', 'BUY_COMPLEMENT', ?, ?, ?, ?, ?)""",
                (
                    trade_id, row["signal_id"], row["market_id"], row["token_id"], size_dollars,
                    entry, quantity, int(row["timestamp"]) + 900 + self.execution.assumptions.entry_delay_seconds,
                    json.dumps(assumptions),
                ),
            )
            inserted = cursor.rowcount == 1
        if not inserted:
            return None
        self.account.reserve(size_dollars)
        return trade_id

    def close(self, signal_id: str, target_exit_price: float, closed_at: int, complementary_bid: float | None = None) -> float | None:
        rows = self.database.query(
            "SELECT * FROM paper_trades WHERE signal_id=? AND status='OPEN'", (signal_id,)
        )
        if not rows:
            return None
        trade = rows[0]
        exit_price = self.execution.exit_price(target_exit_price, complementary_bid)
        exit_value = float(trade["quantity"]) * exit_price
        fees = self.execution.fees(float(trade["size_dollars"]), exit_value)
        pnl = exit_value - float(trade["size_dollars"]) - fees
        self.database.execute(
            """UPDATE paper_trades SET status='CLOSED', exit_price=?, fees=?, pnl=?, closed_at=?
            WHERE trade_id=?""",
            (exit_price, fees, pnl, closed_at, trade["trade_id"]),
        )
        self.account.settle(float(trade["size_dollars"]), pnl)
        return pnl


class PaperExecutionProvider(PaperAccount):
    """The only enabled execution provider in PolyMA Lab."""
