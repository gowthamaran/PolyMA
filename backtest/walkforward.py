from __future__ import annotations

from typing import Any

from backtest.engine import BacktestEngine
from data.models import Candle
from strategy.ma_strategy import StrategyConfig


def walk_forward(
    candles: list[Candle],
    config: StrategyConfig,
    train_days: int = 30,
    test_days: int = 7,
) -> dict[str, Any]:
    if not candles:
        return {"windows": [], "aggregate": {}}
    ordered = sorted(candles, key=lambda c: c.timestamp)
    day = 86_400
    cursor = ordered[0].timestamp
    end = ordered[-1].timestamp
    windows: list[dict[str, Any]] = []
    while cursor + (train_days + test_days) * day <= end + day:
        train_end = cursor + train_days * day
        test_end = train_end + test_days * day
        research = [c for c in ordered if cursor <= c.timestamp < train_end]
        forward = [c for c in ordered if train_end <= c.timestamp < test_end]
        if research and forward:
            report = BacktestEngine().run(forward, [config])
            windows.append({
                "train_start": cursor,
                "train_end": train_end,
                "test_end": test_end,
                "research_candles": len(research),
                "forward": report["variants"][config.variant_id],
            })
        cursor += test_days * day
    total_wins = sum(window["forward"]["wins"] for window in windows)
    total_losses = sum(window["forward"]["losses"] for window in windows)
    return {
        "windows": windows,
        "aggregate": {
            "windows": len(windows),
            "wins": total_wins,
            "losses": total_losses,
            "win_rate": total_wins / (total_wins + total_losses) if total_wins + total_losses else None,
        },
    }

