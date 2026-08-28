from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ExecutionAssumptions:
    entry_delay_seconds: int = 5
    slippage_bps: float = 10.0
    spread_bps: float = 20.0
    fee_bps: float = 0.0


class ExecutionModel:
    """Models buying the complementary outcome for a RED prediction.

    In historical mode the complementary fair price is approximated as
    ``1 - target_price`` and explicit spread/slippage penalties are applied.
    It is labelled simulated and never treated as an observed fill.
    """

    def __init__(self, assumptions: ExecutionAssumptions):
        self.assumptions = assumptions

    def entry_price(self, target_token_price: float, executable_ask: float | None = None) -> float:
        base = executable_ask if executable_ask is not None else 1.0 - target_token_price
        penalty = (self.assumptions.slippage_bps + self.assumptions.spread_bps / 2) / 10_000
        return min(0.9999, max(0.0001, base * (1 + penalty)))

    def exit_price(self, target_token_price: float, executable_bid: float | None = None) -> float:
        base = executable_bid if executable_bid is not None else 1.0 - target_token_price
        penalty = (self.assumptions.slippage_bps + self.assumptions.spread_bps / 2) / 10_000
        return min(0.9999, max(0.0001, base * (1 - penalty)))

    def fees(self, size_dollars: float, exit_value: float) -> float:
        return (size_dollars + exit_value) * self.assumptions.fee_bps / 10_000

