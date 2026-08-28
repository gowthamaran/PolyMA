from __future__ import annotations

import logging
import signal as os_signal
import time
import uuid
from dataclasses import fields
from typing import Any

from app.config import Settings
from app.database import Database
from backtest.metrics import summarize
from data.aggregator import aggregate_price_points, aggregate_trades
from data.models import Candle, Market
from paper.account import PaperAccount, RiskLimits
from paper.execution_model import ExecutionAssumptions, ExecutionModel
from paper.simulator import PaperSimulator
from providers.base import ProviderError
from providers.polymarket import PolymarketProvider
from strategy.ma_strategy import MAStrategy, StrategyConfig
from telegram.bot import TelegramNotifier

logger = logging.getLogger("polyma.scanner")


def candle_from_row(row: dict[str, Any]) -> Candle:
    names = {field.name for field in fields(Candle)}
    values = {key: row[key] for key in names if key in row}
    values["is_complete"] = bool(values["is_complete"])
    return Candle(**values)


def best_price(book: dict[str, Any], side: str) -> float | None:
    levels = book.get(side, [])
    if not levels:
        return None
    prices: list[float] = []
    for level in levels:
        try:
            prices.append(float(level["price"] if isinstance(level, dict) else level.price))
        except (KeyError, TypeError, ValueError, AttributeError):
            continue
    if not prices:
        return None
    return min(prices) if side == "asks" else max(prices)


class LiveScanner:
    def __init__(self, settings: Settings, database: Database, provider: PolymarketProvider | None = None):
        self.settings = settings
        self.database = database
        self.provider = provider or PolymarketProvider()
        self.stop_requested = False
        limits = RiskLimits(
            settings.max_trade_size, settings.max_open_positions, settings.max_daily_loss,
            settings.max_drawdown_percent, settings.max_consecutive_losses,
        )
        account = PaperAccount(database, settings.starting_balance, limits)
        assumptions = ExecutionAssumptions(
            settings.simulated_entry_delay_seconds, settings.slippage_bps,
            settings.spread_bps, settings.fee_bps,
        )
        self.simulator = PaperSimulator(database, account, ExecutionModel(assumptions))
        self.notifier = TelegramNotifier(
            settings.telegram_enabled, settings.telegram_bot_token, settings.telegram_chat_id
        )
        self.variants = [
            StrategyConfig(
                settings.fast_ma, settings.slow_ma, settings.volume_window, threshold,
                not settings.disable_volume_filter,
            )
            for threshold in settings.volume_thresholds
        ]
        if settings.disable_volume_filter:
            self.variants = [StrategyConfig(
                settings.fast_ma, settings.slow_ma, settings.volume_window,
                settings.volume_multiplier, False,
            )]

    def _stats(self, variant_id: str) -> dict[str, Any]:
        rows = self.database.query(
            "SELECT status, directional_return AS return FROM signals WHERE variant_id=? AND run_id='LIVE'",
            (variant_id,),
        )
        return summarize(rows)

    def _collect(self, market: Market, start: int, end: int) -> list[Candle]:
        trades = self.provider.get_trades(market.condition_id, market.token_id, start, end)
        if trades:
            return aggregate_trades(
                trades, asset=market.asset, interval_minutes=self.settings.candle_interval_minutes, as_of=end
            )
        points = self.provider.get_price_history(market.token_id, start, end)
        return aggregate_price_points(
            points, market_id=market.condition_id, asset=market.asset,
            interval_minutes=self.settings.candle_interval_minutes, as_of=end,
        )

    def _process_signals(self, market: Market) -> int:
        rows = self.database.get_candles(market_id=market.condition_id, token_id=market.token_id)
        candles = [candle_from_row(row) for row in rows]
        created = 0
        for config in self.variants:
            self.database.register_variant(
                config.variant_id, config.fast_ma, config.slow_ma, config.volume_window,
                config.volume_multiplier if config.volume_filter_enabled else None,
                config.volume_filter_enabled,
            )
            for candidate in MAStrategy(config).scan(candles):
                signal_id = self.database.insert_signal(candidate)
                if not signal_id:
                    continue
                created += 1
                is_primary = (
                    not config.volume_filter_enabled
                    or abs(config.volume_multiplier - self.settings.volume_multiplier) < 1e-9
                )
                if is_primary:
                    ask = None
                    if market.complementary_token_id:
                        try:
                            ask = best_price(self.provider.get_orderbook(market.complementary_token_id), "asks")
                        except ProviderError:
                            logger.warning("orderbook_unavailable_using_explicit_model")
                    size = self.simulator.position_size(
                        self.settings.position_sizing, self.settings.trade_size, candidate.volume_ratio
                    )
                    trade_id = self.simulator.open(candidate, size, ask)
                    if trade_id:
                        self.notifier.signal(candidate.as_dict(), self._stats(config.variant_id))
                logger.info("signal_created variant=%s signal=%s", config.variant_id, signal_id)
        return created

    def recover_and_grade(self) -> int:
        graded = 0
        for pending in self.database.pending_signals():
            rows = self.database.query(
                """SELECT * FROM candles WHERE market_id=? AND token_id=? AND timestamp=? AND is_complete=1""",
                (pending["market_id"], pending["token_id"], pending["timestamp"] + 900),
            )
            if not rows:
                continue
            nxt = candle_from_row(rows[0])
            movement = nxt.close - nxt.open
            status = "WIN" if movement < 0 else "LOSS" if movement > 0 else "NEUTRAL"
            directional_return = (nxt.open - nxt.close) / nxt.open if nxt.open else 0.0
            self.database.grade_signal(pending["signal_id"], status, nxt.open, nxt.close, directional_return)
            self.simulator.close(pending["signal_id"], nxt.close, nxt.timestamp + 900)
            updated = {**pending, "status": status}
            self.notifier.graded(updated, self._stats(pending["variant_id"]))
            logger.info("signal_graded signal=%s status=%s", pending["signal_id"], status)
            graded += 1
        return graded

    def cycle(self, assets: tuple[str, ...] | None = None, market_id: str | None = None) -> dict[str, int]:
        now = int(time.time())
        start = now - self.settings.scan_lookback_hours * 3600
        markets = self.provider.get_markets(
            assets=assets or self.settings.assets, market_id=market_id,
            include_closed=False, limit=self.settings.market_limit,
        )
        stored_candles = created_signals = errors = 0
        for market in markets:
            try:
                self.database.upsert_market(market)
                candles = self._collect(market, start, now)
                stored_candles += self.database.upsert_candles(candles)
                created_signals += self._process_signals(market)
            except ProviderError:
                errors += 1
                logger.exception("market_collection_failed market=%s", market.condition_id)
        graded = self.recover_and_grade()
        return {
            "markets": len(markets), "candles": stored_candles, "signals": created_signals,
            "graded": graded, "errors": errors,
        }

    def run_forever(self, assets: tuple[str, ...] | None = None, market_id: str | None = None) -> None:
        run_id = f"forward-{uuid.uuid4().hex[:12]}"
        self.database.execute(
            "INSERT INTO forward_runs(run_id, status, last_heartbeat) VALUES (?, 'RUNNING', CURRENT_TIMESTAMP)",
            (run_id,),
        )
        def request_stop(_signum: int, _frame: Any) -> None:
            self.stop_requested = True
        os_signal.signal(os_signal.SIGINT, request_stop)
        os_signal.signal(os_signal.SIGTERM, request_stop)
        while not self.stop_requested:
            try:
                result = self.cycle(assets, market_id)
                logger.info("scan_cycle %s", result)
                self.database.execute(
                    "UPDATE forward_runs SET last_heartbeat=CURRENT_TIMESTAMP WHERE run_id=?", (run_id,)
                )
            except Exception:
                logger.exception("scan_cycle_failed")
            deadline = time.time() + self.settings.scan_poll_seconds
            while time.time() < deadline and not self.stop_requested:
                time.sleep(min(1.0, deadline - time.time()))
        self.database.execute(
            "UPDATE forward_runs SET stopped_at=CURRENT_TIMESTAMP, status='STOPPED' WHERE run_id=?", (run_id,)
        )

