from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.database import Database
from paper.execution_provider import ExecutionProvider


@dataclass(frozen=True)
class RiskLimits:
    max_trade_size: float = 500.0
    max_open_positions: int = 3
    max_daily_loss: float = 500.0
    max_drawdown_percent: float = 20.0
    max_consecutive_losses: int = 5


class PaperAccount(ExecutionProvider):
    def __init__(self, database: Database, starting_balance: float, limits: RiskLimits):
        self.database = database
        self.starting_balance = starting_balance
        self.limits = limits
        self.database.ensure_account(starting_balance)

    def snapshot(self) -> dict[str, Any]:
        rows = self.database.query("SELECT * FROM paper_account WHERE id=1")
        return rows[0]

    def get_balance(self) -> float:
        return float(self.snapshot()["balance"])

    def get_positions(self) -> list[dict[str, Any]]:
        return self.database.query("SELECT * FROM paper_trades WHERE status='OPEN' ORDER BY opened_at")

    def can_open(self, size: float) -> tuple[bool, str]:
        account = self.snapshot()
        if size <= 0 or size > self.limits.max_trade_size:
            return False, "MAX_TRADE_SIZE"
        if len(self.get_positions()) >= self.limits.max_open_positions:
            return False, "MAX_OPEN_POSITIONS"
        if size > float(account["available_balance"]):
            return False, "INSUFFICIENT_PAPER_BALANCE"
        drawdown = (float(account["peak_balance"]) - float(account["balance"])) / float(account["peak_balance"]) * 100
        if drawdown >= self.limits.max_drawdown_percent:
            return False, "MAX_DRAWDOWN"
        if int(account["consecutive_losses"]) >= self.limits.max_consecutive_losses:
            return False, "MAX_CONSECUTIVE_LOSSES"
        daily = self.database.query(
            "SELECT COALESCE(SUM(pnl),0) AS pnl FROM paper_trades WHERE status='CLOSED' AND date(closed_at, 'unixepoch')=date('now')"
        )[0]["pnl"]
        if float(daily) <= -self.limits.max_daily_loss:
            return False, "MAX_DAILY_LOSS"
        return True, "OK"

    def reserve(self, size: float) -> None:
        self.database.execute(
            "UPDATE paper_account SET available_balance=available_balance-?, updated_at=CURRENT_TIMESTAMP WHERE id=1",
            (size,),
        )

    def settle(self, reserved: float, pnl: float) -> None:
        loss_count = "consecutive_losses+1" if pnl < 0 else "0"
        with self.database.transaction() as connection:
            connection.execute(
                f"""UPDATE paper_account SET
                balance=balance+?, available_balance=available_balance+?+?, realized_pnl=realized_pnl+?,
                peak_balance=MAX(peak_balance, balance+?), consecutive_losses={loss_count},
                updated_at=CURRENT_TIMESTAMP WHERE id=1""",
                (pnl, reserved, pnl, pnl, pnl),
            )

