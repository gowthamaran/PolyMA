from __future__ import annotations

from collections import defaultdict
from typing import Any, Callable

from data.models import Candle
from strategy.indicators import sma


def _is_red(candle: Candle) -> bool | None:
    if candle.close < candle.open:
        return True
    if candle.close > candle.open:
        return False
    return None


def baseline_report(candles: list[Candle], fast_window: int = 7, slow_window: int = 25) -> dict[str, dict[str, Any]]:
    grouped: dict[tuple[str, str], list[Candle]] = defaultdict(list)
    for candle in candles:
        if candle.is_complete:
            grouped[(candle.market_id, candle.token_id)].append(candle)
    rules: dict[str, Callable[[Candle, float | None, float | None], bool]] = {
        "A_any_candle": lambda current, fast, slow: True,
        "B_after_green": lambda current, fast, slow: current.close > current.open,
        "C_green_above_ma7": lambda current, fast, slow: current.close > current.open and fast is not None and current.close > fast,
        "D_green_between_ma7_ma25": lambda current, fast, slow: current.close > current.open and fast is not None and slow is not None and fast < current.close < slow,
    }
    counters = {name: {"samples": 0, "red": 0, "green": 0, "neutral": 0} for name in rules}
    for rows in grouped.values():
        ordered = sorted(rows, key=lambda item: item.timestamp)
        for index, current in enumerate(ordered[:-1]):
            nxt = ordered[index + 1]
            if nxt.timestamp != current.timestamp + 900:
                continue
            prior = [row.close for row in ordered[:index]]
            fast, slow = sma(prior, fast_window), sma(prior, slow_window)
            direction = _is_red(nxt)
            for name, rule in rules.items():
                if not rule(current, fast, slow):
                    continue
                counters[name]["samples"] += 1
                if direction is True:
                    counters[name]["red"] += 1
                elif direction is False:
                    counters[name]["green"] += 1
                else:
                    counters[name]["neutral"] += 1
    for values in counters.values():
        decisive = values["red"] + values["green"]
        values["red_rate"] = values["red"] / decisive if decisive else None
    return counters

