from backtest.engine import BacktestEngine, chronological_boundaries, split_name
from backtest.metrics import summarize, wilson_interval
from strategy.ma_strategy import StrategyConfig
from tests.conftest import candle, signal_fixture


def test_chronological_split_is_never_shuffled() -> None:
    rows = [candle(index, 0.4, 0.5) for index in range(10)]
    boundaries = chronological_boundaries(list(reversed(rows)))
    labels = [split_name(row.timestamp, boundaries) for row in rows]
    assert labels == ["DEVELOPMENT"] * 6 + ["VALIDATION"] * 2 + ["TEST"] * 2


def test_backtest_grades_exact_next_candle() -> None:
    rows = signal_fixture() + [candle(26, 0.6, 0.5)]
    report = BacktestEngine().run(rows, [StrategyConfig()])
    metrics = report["variants"]["vol-1.50x"]
    assert metrics["signals"] == 1
    assert metrics["wins"] == 1
    assert metrics["losses"] == 0


def test_neutral_separate_from_win_rate() -> None:
    metrics = summarize([
        {"status": "WIN", "return": 0.1},
        {"status": "LOSS", "return": -0.1},
        {"status": "NEUTRAL", "return": 0.0},
    ])
    assert metrics["neutral"] == 1
    assert metrics["win_rate"] == 0.5


def test_small_sample_confidence_interval_is_wide() -> None:
    low, high = wilson_interval(9, 1)
    assert low is not None and high is not None
    assert low < 0.6
    assert high > 0.95

