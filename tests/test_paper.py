import pytest

from app.database import Database
from paper.account import PaperAccount, RiskLimits
from paper.execution_model import ExecutionAssumptions, ExecutionModel
from paper.execution_provider import DisabledLiveExecutionProvider, LiveTradingDisabledError
from paper.simulator import PaperSimulator
from strategy.ma_strategy import MAStrategy, StrategyConfig
from tests.conftest import signal_fixture


def test_paper_pnl_and_duplicate_position(tmp_path) -> None:
    database = Database(tmp_path / "paper.db")
    database.initialize()
    signal = MAStrategy(StrategyConfig()).scan(signal_fixture())[0]
    assert database.insert_signal(signal)
    account = PaperAccount(database, 10_000, RiskLimits())
    simulator = PaperSimulator(database, account, ExecutionModel(ExecutionAssumptions(5, 0, 0, 0)))
    trade_id = simulator.open(signal, 100)
    assert trade_id
    assert account.snapshot()["available_balance"] == 9_900
    assert simulator.open(signal, 100) is None
    assert account.snapshot()["available_balance"] == 9_900
    pnl = simulator.close(signal.signal_id, 0.5, signal.timestamp + 1800)
    assert pnl == pytest.approx(25.0)
    assert account.get_balance() == pytest.approx(10_025.0)
    assert account.snapshot()["available_balance"] == pytest.approx(10_025.0)


def test_risk_limit_rejects_large_virtual_trade(tmp_path) -> None:
    database = Database(tmp_path / "paper.db")
    database.initialize()
    account = PaperAccount(database, 1000, RiskLimits(max_trade_size=100))
    assert account.can_open(101) == (False, "MAX_TRADE_SIZE")


def test_live_execution_is_impossible() -> None:
    provider = DisabledLiveExecutionProvider()
    with pytest.raises(LiveTradingDisabledError):
        provider.submit_order("anything")
    with pytest.raises(LiveTradingDisabledError):
        provider.cancel_order("anything")

