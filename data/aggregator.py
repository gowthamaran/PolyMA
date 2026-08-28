from __future__ import annotations

import time
from collections import defaultdict

from data.models import Candle, PricePoint, Trade


def bucket_start(timestamp: int, interval_minutes: int = 15) -> int:
    seconds = interval_minutes * 60
    return timestamp - timestamp % seconds


def aggregate_trades(
    trades: list[Trade],
    *,
    asset: str,
    interval_minutes: int = 15,
    as_of: int | None = None,
) -> list[Candle]:
    """Aggregate only observed trades; absent buckets are intentionally omitted.

    This avoids inventing zero-volume candles. A candle is complete only when its
    deterministic UTC bucket end is not later than ``as_of``.
    """
    now = int(time.time()) if as_of is None else as_of
    grouped: dict[tuple[str, str, int], list[Trade]] = defaultdict(list)
    for trade in trades:
        grouped[(trade.market_id, trade.token_id, bucket_start(trade.timestamp, interval_minutes))].append(trade)
    candles: list[Candle] = []
    seconds = interval_minutes * 60
    for (market_id, token_id, timestamp), rows in grouped.items():
        ordered = sorted(rows, key=lambda row: (row.timestamp, row.trade_id))
        prices = [row.price for row in ordered]
        candles.append(
            Candle(
                timestamp=timestamp,
                market_id=market_id,
                token_id=token_id,
                asset=asset,
                open=prices[0],
                high=max(prices),
                low=min(prices),
                close=prices[-1],
                volume=sum(row.size for row in ordered),
                trade_count=len(ordered),
                is_complete=timestamp + seconds <= now,
                volume_source="REAL_TRADE_VOLUME",
                price_source="TRADES",
            )
        )
    return sorted(candles, key=lambda candle: candle.timestamp)


def aggregate_price_points(
    points: list[PricePoint],
    *,
    market_id: str,
    asset: str,
    interval_minutes: int = 15,
    as_of: int | None = None,
) -> list[Candle]:
    """Create clearly labelled sampled-price proxy candles with unavailable volume."""
    now = int(time.time()) if as_of is None else as_of
    grouped: dict[int, list[PricePoint]] = defaultdict(list)
    for point in points:
        grouped[bucket_start(point.timestamp, interval_minutes)].append(point)
    seconds = interval_minutes * 60
    candles: list[Candle] = []
    for timestamp, rows in grouped.items():
        ordered = sorted(rows, key=lambda row: row.timestamp)
        prices = [row.price for row in ordered]
        candles.append(
            Candle(
                timestamp=timestamp,
                market_id=market_id,
                token_id=ordered[0].token_id,
                asset=asset,
                open=prices[0],
                high=max(prices),
                low=min(prices),
                close=prices[-1],
                volume=None,
                trade_count=0,
                is_complete=timestamp + seconds <= now,
                volume_source="UNAVAILABLE",
                price_source="SAMPLED_PRICE_PROXY",
            )
        )
    return sorted(candles, key=lambda candle: candle.timestamp)

