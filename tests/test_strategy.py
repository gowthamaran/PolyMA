from dataclasses import replace

from strategy.ma_strategy import MAStrategy, StrategyConfig
from strategy.signals import grade_next_candle
from tests.conftest import candle, signal_fixture


def test_full_signal_generation() -> None:
    rows = signal_fixture()
    evaluation = MAStrategy(StrategyConfig()).evaluate(rows[:-1], rows[-1])
    assert evaluation.green
    assert evaluation.above_fast
    assert evaluation.below_slow
    assert evaluation.volume_ok
    assert evaluation.ma_fast == 0.4
    assert abs(evaluation.ma_slow - 0.688) < 1e-12
    assert evaluation.volume_ratio == 1.6
    assert evaluation.signal is not None


def test_volume_threshold_is_strictly_greater() -> None:
    rows = signal_fixture()
    current = replace(rows[-1], volume=15.0)
    assert MAStrategy(StrategyConfig(volume_multiplier=1.5)).evaluate(rows[:-1], current).signal is None
    assert MAStrategy(StrategyConfig(volume_multiplier=1.49)).evaluate(rows[:-1], current).signal is not None


def test_disable_volume_filter_is_labelled_and_allows_missing_volume() -> None:
    rows = signal_fixture()
    current = replace(rows[-1], volume=None)
    config = StrategyConfig(volume_filter_enabled=False)
    evaluation = MAStrategy(config).evaluate(rows[:-1], current)
    assert config.variant_id == "volume-disabled"
    assert evaluation.signal is not None


def test_incomplete_and_noncontiguous_candles_are_rejected() -> None:
    rows = signal_fixture()
    incomplete = replace(rows[-1], is_complete=False)
    assert MAStrategy(StrategyConfig()).evaluate(rows[:-1], incomplete).signal is None
    gap_history = rows[:-2] + [replace(rows[-2], timestamp=rows[-2].timestamp - 900)]
    assert not MAStrategy(StrategyConfig()).evaluate(gap_history, rows[-1]).contiguous


def test_next_candle_grading_including_neutral() -> None:
    signal = MAStrategy(StrategyConfig()).scan(signal_fixture())[0]
    red = candle(26, 0.6, 0.5)
    green = candle(26, 0.5, 0.6)
    neutral = candle(26, 0.5, 0.5)
    assert grade_next_candle(signal, red)[0] == "WIN"
    assert grade_next_candle(signal, green)[0] == "LOSS"
    assert grade_next_candle(signal, neutral)[0] == "NEUTRAL"
    assert grade_next_candle(signal, replace(red, is_complete=False))[0] == "PENDING"
    assert grade_next_candle(signal, candle(27, 0.6, 0.5))[0] == "INVALID"

