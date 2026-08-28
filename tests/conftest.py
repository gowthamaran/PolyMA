from __future__ import annotations

from data.models import Candle


def candle(
    index: int,
    open_price: float,
    close_price: float,
    volume: float | None = 10.0,
    *,
    complete: bool = True,
    base: int = 1_800_000_000,
) -> Candle:
    return Candle(
        timestamp=base + index * 900,
        market_id="condition-1",
        token_id="token-yes",
        asset="BTC",
        open=open_price,
        high=max(open_price, close_price),
        low=min(open_price, close_price),
        close=close_price,
        volume=volume,
        trade_count=2,
        is_complete=complete,
    )


def signal_fixture() -> list[Candle]:
    rows: list[Candle] = []
    closes = [0.8] * 18 + [0.4] * 7
    for index, value in enumerate(closes):
        rows.append(candle(index, value - 0.01, value, 10.0))
    rows.append(candle(25, 0.5, 0.6, 16.0))
    return rows

