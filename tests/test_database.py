from app.database import Database
from strategy.ma_strategy import MAStrategy, StrategyConfig
from tests.conftest import signal_fixture


def test_duplicate_signal_prevention(tmp_path) -> None:
    database = Database(tmp_path / "test.db")
    database.initialize()
    signal = MAStrategy(StrategyConfig()).scan(signal_fixture())[0]
    assert database.insert_signal(signal)
    assert database.insert_signal(signal) is None
    assert len(database.pending_signals()) == 1


def test_backtest_runs_can_store_same_observation_independently(tmp_path) -> None:
    database = Database(tmp_path / "test.db")
    database.initialize()
    signal = MAStrategy(StrategyConfig()).scan(signal_fixture())[0]
    first = database.insert_signal(signal, run_id="run-a")
    second = database.insert_signal(signal, run_id="run-b")
    assert first and second and first != second


def test_restart_pending_signal_can_be_graded(tmp_path) -> None:
    database = Database(tmp_path / "test.db")
    database.initialize()
    signal = MAStrategy(StrategyConfig()).scan(signal_fixture())[0]
    signal_id = database.insert_signal(signal)
    assert signal_id
    database.grade_signal(signal_id, "WIN", 0.6, 0.5, 1 / 6)
    assert database.pending_signals() == []
    assert database.query("SELECT status FROM signals")[0]["status"] == "WIN"

