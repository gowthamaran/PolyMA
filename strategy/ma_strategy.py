from __future__ import annotations

from dataclasses import dataclass

from data.models import Candle
from strategy.indicators import sma, volume_ratio
from strategy.signals import Signal, make_signal_id


@dataclass(frozen=True)
class StrategyConfig:
    fast_ma: int = 7
    slow_ma: int = 25
    volume_window: int = 20
    volume_multiplier: float = 1.5
    volume_filter_enabled: bool = True
    require_contiguous: bool = True

    @property
    def variant_id(self) -> str:
        return f"vol-{self.volume_multiplier:.2f}x" if self.volume_filter_enabled else "volume-disabled"


@dataclass(frozen=True)
class Evaluation:
    complete: bool
    enough_history: bool
    contiguous: bool
    green: bool
    above_fast: bool
    below_slow: bool
    volume_ok: bool
    ma_fast: float | None
    ma_slow: float | None
    avg_volume: float | None
    volume_ratio: float | None
    signal: Signal | None


class MAStrategy:
    """Causal MA7/MA25 evaluator.

    For candle i, every indicator is computed from candles strictly before i.
    The current close and volume are used only after candle i is complete. This
    explicit slice is the central anti-lookahead guarantee.
    """

    def __init__(self, config: StrategyConfig):
        self.config = config

    def evaluate(self, completed_history: list[Candle], current: Candle) -> Evaluation:
        cfg = self.config
        history = [candle for candle in completed_history if candle.is_complete and candle.timestamp < current.timestamp]
        required = max(cfg.fast_ma, cfg.slow_ma, cfg.volume_window if cfg.volume_filter_enabled else 0)
        enough = len(history) >= required
        contiguous = True
        if enough and cfg.require_contiguous:
            relevant = history[-required:] + [current]
            contiguous = all(b.timestamp - a.timestamp == 900 for a, b in zip(relevant, relevant[1:]))
        if not current.is_complete or not enough or not contiguous:
            return Evaluation(
                current.is_complete, enough, contiguous, False, False, False, False,
                None, None, None, None, None,
            )

        # Anti-lookahead: current.close is deliberately absent from these inputs.
        closes = [candle.close for candle in history]
        fast = sma(closes, cfg.fast_ma)
        slow = sma(closes, cfg.slow_ma)
        avg_volume, ratio = volume_ratio(current.volume, [c.volume for c in history], cfg.volume_window)
        green = current.close > current.open
        above_fast = fast is not None and current.close > fast
        below_slow = slow is not None and current.close < slow
        volume_ok = (
            True if not cfg.volume_filter_enabled
            else ratio is not None and ratio > cfg.volume_multiplier
        )
        signal: Signal | None = None
        if green and above_fast and below_slow and volume_ok:
            signal_id, observation_id = make_signal_id(
                current.market_id, current.token_id, current.timestamp, cfg.variant_id
            )
            signal = Signal(
                signal_id=signal_id,
                observation_id=observation_id,
                variant_id=cfg.variant_id,
                market_id=current.market_id,
                token_id=current.token_id,
                asset=current.asset,
                timestamp=current.timestamp,
                open=current.open,
                high=current.high,
                low=current.low,
                close=current.close,
                volume=current.volume,
                ma7=float(fast),
                ma25=float(slow),
                avg_volume20=avg_volume,
                volume_ratio=ratio,
            )
        return Evaluation(
            True, True, True, green, above_fast, below_slow, volume_ok,
            fast, slow, avg_volume, ratio, signal,
        )

    def scan(self, candles: list[Candle]) -> list[Signal]:
        ordered = sorted(candles, key=lambda candle: candle.timestamp)
        signals: list[Signal] = []
        history: list[Candle] = []
        for candle in ordered:
            evaluation = self.evaluate(history, candle)
            if evaluation.signal:
                signals.append(evaluation.signal)
            if candle.is_complete:
                history.append(candle)
        return signals

