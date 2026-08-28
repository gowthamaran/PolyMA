from dataclasses import replace

from strategy.ma_strategy import MAStrategy, StrategyConfig
from tests.conftest import candle, signal_fixture


def test_future_candle_cannot_change_existing_signal() -> None:
    rows = signal_fixture()
    strategy = MAStrategy(StrategyConfig())
    original = strategy.scan(rows)
    with_future_crash = strategy.scan(rows + [candle(26, 0.99, 0.01, 1_000_000)])
    with_future_rally = strategy.scan(rows + [candle(26, 0.01, 0.99, 0.0)])
    assert original[0] == with_future_crash[0] == with_future_rally[0]


def test_current_close_and_volume_are_excluded_from_historical_averages() -> None:
    rows = signal_fixture()
    strategy = MAStrategy(StrategyConfig())
    first = strategy.evaluate(rows[:-1], rows[-1])
    changed = strategy.evaluate(rows[:-1], replace(rows[-1], close=0.65, high=0.65, volume=30.0))
    assert first.ma_fast == changed.ma_fast == 0.4
    assert first.ma_slow == changed.ma_slow
    assert first.avg_volume == changed.avg_volume == 10.0


def test_mutating_future_history_is_ignored_by_timestamp_filter() -> None:
    rows = signal_fixture()
    current = rows[-1]
    malicious_future = candle(99, 0.0, 1.0, 999999)
    clean = MAStrategy(StrategyConfig()).evaluate(rows[:-1], current)
    dirty = MAStrategy(StrategyConfig()).evaluate(rows[:-1] + [malicious_future], current)
    assert clean == dirty

