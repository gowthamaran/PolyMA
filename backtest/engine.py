from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import replace
from typing import Any

from app.database import Database
from backtest.baselines import baseline_report
from backtest.metrics import summarize
from backtest.sanity import randomized_check
from data.models import Candle
from strategy.ma_strategy import MAStrategy, StrategyConfig
from strategy.signals import grade_next_candle


def chronological_boundaries(candles: list[Candle], development: float = 0.6, validation: float = 0.2) -> tuple[int, int]:
    timestamps = sorted({candle.timestamp for candle in candles if candle.is_complete})
    if not timestamps:
        return 0, 0
    development_index = min(len(timestamps) - 1, max(0, int(len(timestamps) * development) - 1))
    validation_index = min(len(timestamps) - 1, max(development_index, int(len(timestamps) * (development + validation)) - 1))
    return timestamps[development_index], timestamps[validation_index]


def split_name(timestamp: int, boundaries: tuple[int, int]) -> str:
    if timestamp <= boundaries[0]:
        return "DEVELOPMENT"
    if timestamp <= boundaries[1]:
        return "VALIDATION"
    return "TEST"


class BacktestEngine:
    def __init__(self, database: Database | None = None):
        self.database = database

    def run(
        self,
        candles: list[Candle],
        configs: list[StrategyConfig],
        *,
        run_id: str | None = None,
    ) -> dict[str, Any]:
        run_id = run_id or f"bt-{uuid.uuid4().hex[:12]}"
        complete = sorted((c for c in candles if c.is_complete), key=lambda c: c.timestamp)
        boundaries = chronological_boundaries(complete)
        if self.database:
            parameters = {"variants": [config.__dict__ for config in configs], "split": [0.6, 0.2, 0.2]}
            self.database.start_backtest(
                run_id, parameters, complete[0].timestamp if complete else None,
                complete[-1].timestamp if complete else None,
            )
        grouped: dict[tuple[str, str], list[Candle]] = defaultdict(list)
        for candle in complete:
            grouped[(candle.market_id, candle.token_id)].append(candle)

        variants: dict[str, Any] = {}
        all_outcomes: list[int] = []
        for rows in grouped.values():
            ordered = sorted(rows, key=lambda c: c.timestamp)
            for current, nxt in zip(ordered, ordered[1:]):
                if nxt.timestamp == current.timestamp + 900 and nxt.close != nxt.open:
                    all_outcomes.append(int(nxt.close < nxt.open))

        for config in configs:
            strategy = MAStrategy(config)
            records: list[dict[str, Any]] = []
            by_split: dict[str, list[dict[str, Any]]] = defaultdict(list)
            by_asset: dict[str, list[dict[str, Any]]] = defaultdict(list)
            for rows in grouped.values():
                ordered = sorted(rows, key=lambda c: c.timestamp)
                next_by_time = {c.timestamp: c for c in ordered}
                for signal in strategy.scan(ordered):
                    nxt = next_by_time.get(signal.timestamp + 900)
                    status, raw_return = grade_next_candle(signal, nxt)
                    normalized = (raw_return / nxt.open) if raw_return is not None and nxt and nxt.open else 0.0
                    record = {**signal.as_dict(), "status": status, "return": normalized}
                    split = split_name(signal.timestamp, boundaries)
                    records.append(record)
                    by_split[split].append(record)
                    by_asset[signal.asset].append(record)
                    if self.database:
                        self.database.register_variant(
                            config.variant_id, config.fast_ma, config.slow_ma, config.volume_window,
                            config.volume_multiplier if config.volume_filter_enabled else None,
                            config.volume_filter_enabled,
                        )
                        stored_id = self.database.insert_signal(signal, run_id=run_id, split_name=split)
                        if stored_id and nxt and status != "PENDING":
                            self.database.grade_signal(stored_id, status, nxt.open, nxt.close, normalized)
            summary = summarize(records)
            summary["in_sample"] = summarize(by_split["DEVELOPMENT"] + by_split["VALIDATION"])
            summary["out_of_sample"] = summarize(by_split["TEST"])
            summary["by_split"] = {name: summarize(values) for name, values in by_split.items()}
            summary["by_asset"] = {name: summarize(values) for name, values in by_asset.items()}
            decisive = summary["wins"] + summary["losses"]
            summary["randomized_sanity"] = randomized_check(
                all_outcomes, summary["wins"], decisive, iterations=1000
            )
            variants[config.variant_id] = summary

        report = {
            "run_id": run_id,
            "market_tokens": len(grouped),
            "candles": len(complete),
            "split_boundaries": {"development_end": boundaries[0], "validation_end": boundaries[1]},
            "variants": variants,
            "baselines": baseline_report(complete),
            "research_warning": "Threshold selection must use development/validation only; TEST is held out.",
        }
        if self.database:
            self.database.finish_backtest(run_id, len(grouped), len(complete), report)
        return report


def default_variants(base: StrategyConfig, thresholds: tuple[float, ...]) -> list[StrategyConfig]:
    return [replace(base, volume_multiplier=value, volume_filter_enabled=True) for value in thresholds]

