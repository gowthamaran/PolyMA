from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import uvicorn

from app.config import Settings
from app.database import Database
from app.logging_setup import configure_logging
from backtest.engine import BacktestEngine, default_variants
from backtest.report import render_report
from backtest.walkforward import walk_forward
from dashboard.server import create_app
from data.aggregator import aggregate_price_points, aggregate_trades
from data.models import Candle, Market
from providers.base import ProviderError
from providers.polymarket import PolymarketProvider
from scanner.live import LiveScanner, candle_from_row
from strategy.ma_strategy import StrategyConfig


def setup() -> tuple[Settings, Database]:
    settings = Settings.from_env()
    settings.ensure_directories()
    configure_logging(settings.log_level)
    database = Database(settings.database_path)
    database.initialize()
    database.ensure_account(settings.starting_balance)
    return settings, database


def selected_assets(args: argparse.Namespace, settings: Settings) -> tuple[str, ...]:
    if getattr(args, "all_supported", False):
        return settings.assets
    assets = tuple(value.upper() for value in (getattr(args, "asset", None) or []))
    return assets or settings.assets


def discover(args: argparse.Namespace, settings: Settings, database: Database) -> int:
    provider = PolymarketProvider()
    try:
        markets = provider.get_markets(
            assets=selected_assets(args, settings), market_id=args.market,
            include_closed=args.include_closed, limit=args.limit,
        )
        for market in markets:
            database.upsert_market(market)
        grouped: dict[str, int] = {}
        for market in markets:
            grouped[market.asset] = grouped.get(market.asset, 0) + 1
        print(json.dumps({"market_tokens_discovered": len(markets), "by_asset": grouped, "markets": [
            {"id": m.market_id, "condition_id": m.condition_id, "asset": m.asset, "outcome": m.outcome, "question": m.question}
            for m in markets
        ]}, indent=2))
        return 0
    finally:
        provider.close()


def collect_historical(
    provider: PolymarketProvider,
    database: Database,
    markets: list[Market],
    start: int,
    end: int,
    interval: int,
) -> tuple[list[Candle], dict[str, int]]:
    candles: list[Candle] = []
    sources = {"REAL_TRADE_VOLUME": 0, "UNAVAILABLE": 0, "errors": 0}
    for market in markets:
        database.upsert_market(market)
        try:
            trades = provider.get_trades(market.condition_id, market.token_id, start, end)
            if trades:
                rows = aggregate_trades(trades, asset=market.asset, interval_minutes=interval, as_of=end)
            else:
                points = provider.get_price_history(market.token_id, start, end)
                rows = aggregate_price_points(
                    points, market_id=market.condition_id, asset=market.asset,
                    interval_minutes=interval, as_of=end,
                )
            candles.extend(rows)
            database.upsert_candles(rows)
            for row in rows:
                sources[row.volume_source] = sources.get(row.volume_source, 0) + 1
        except ProviderError as exc:
            sources["errors"] += 1
            print(f"warning: {market.condition_id}/{market.outcome}: {exc}", file=sys.stderr)
    return candles, sources


def run_backtest(args: argparse.Namespace, settings: Settings, database: Database) -> int:
    end = int(time.time())
    start = end - args.days * 86_400
    provider = PolymarketProvider()
    try:
        markets = provider.get_markets(
            assets=selected_assets(args, settings), market_id=args.market,
            include_closed=True, limit=args.limit,
        )
        candles, sources = collect_historical(
            provider, database, markets, start, end, settings.candle_interval_minutes
        )
    finally:
        provider.close()
    base = StrategyConfig(
        settings.fast_ma, settings.slow_ma, settings.volume_window,
        settings.volume_multiplier, not (args.disable_volume_filter or settings.disable_volume_filter),
    )
    configs = [replace(base, volume_filter_enabled=False)] if not base.volume_filter_enabled else default_variants(base, settings.volume_thresholds)
    report = BacktestEngine(database).run(candles, configs)
    chosen = base.variant_id
    print(render_report(report, chosen))
    print("\nDATA SOURCES\n" + json.dumps(sources, indent=2))
    if args.walk_forward:
        wf = walk_forward(candles, base, args.train_days, args.test_days)
        print("\nWALK FORWARD\n" + json.dumps(wf["aggregate"], indent=2))
    return 0


def scan(args: argparse.Namespace, settings: Settings, database: Database) -> int:
    scanner = LiveScanner(settings, database)
    assets = selected_assets(args, settings)
    if args.once:
        print(json.dumps(scanner.cycle(assets, args.market), indent=2))
    else:
        scanner.run_forever(assets, args.market)
    return 0


def dashboard(_args: argparse.Namespace, settings: Settings, database: Database) -> int:
    uvicorn.run(create_app(settings, database), host=settings.app_host, port=settings.app_port)
    return 0


def stats(_args: argparse.Namespace, settings: Settings, database: Database) -> int:
    primary = f"vol-{settings.volume_multiplier:.2f}x" if not settings.disable_volume_filter else "volume-disabled"
    rows = database.query(
        """SELECT status, COUNT(*) count FROM signals WHERE run_id='LIVE' AND variant_id=? GROUP BY status""",
        (primary,),
    )
    account = database.query("SELECT * FROM paper_account WHERE id=1")
    print(json.dumps({"primary_variant": primary, "signals": rows, "paper_account": account[0] if account else None}, indent=2))
    return 0


def reset_paper(args: argparse.Namespace, settings: Settings, database: Database) -> int:
    if not args.yes:
        print("Refusing destructive reset without --yes", file=sys.stderr)
        return 2
    database.reset_account(settings.starting_balance)
    print("Paper account and virtual trades reset. Historical candles/signals were preserved.")
    return 0


def export_table(args: argparse.Namespace, _settings: Settings, database: Database) -> int:
    mapping = {
        "candles": "SELECT * FROM candles ORDER BY timestamp",
        "signals": "SELECT * FROM signals ORDER BY timestamp",
        "trades": "SELECT * FROM paper_trades ORDER BY opened_at",
        "backtests": "SELECT * FROM backtest_runs ORDER BY started_at",
    }
    rows = database.query(mapping[args.kind])
    output = Path("exports") / f"{args.kind}_{datetime.now(timezone.utc):%Y%m%d_%H%M%S}.csv"
    output.parent.mkdir(exist_ok=True)
    with output.open("w", newline="", encoding="utf-8") as handle:
        if rows:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    print(output)
    return 0


def smoke_test(args: argparse.Namespace, settings: Settings, database: Database) -> int:
    provider = PolymarketProvider()
    end = int(time.time())
    start = end - args.hours * 3600
    try:
        markets = provider.get_markets(assets=selected_assets(args, settings), limit=args.limit)
        candles, sources = collect_historical(
            provider, database, markets, start, end, settings.candle_interval_minutes
        )
    finally:
        provider.close()
    config = StrategyConfig(
        settings.fast_ma, settings.slow_ma, settings.volume_window,
        settings.volume_multiplier, not args.disable_volume_filter,
    )
    report = BacktestEngine().run(candles, [config])
    output = {
        "markets_discovered": len(markets),
        "completed_candles": len([c for c in candles if c.is_complete]),
        "volume_sources": sources,
        "signals": report["variants"][config.variant_id]["signals"],
        "limitations": [
            "No-trade UTC buckets are omitted, never fabricated.",
            "Sampled CLOB price history has UNAVAILABLE volume and cannot satisfy the enabled volume filter.",
            "A 15-minute-duration market generally cannot contain the 25 prior 15-minute candles required by this hypothesis.",
        ],
    }
    print(json.dumps(output, indent=2))
    return 0


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="polyma", description="PolyMA Lab — paper-only Polymarket strategy research")
    commands = root.add_subparsers(dest="command", required=True)
    def market_options(command: argparse.ArgumentParser) -> None:
        command.add_argument("--asset", action="append", choices=["BTC", "ETH", "SOL", "XRP"])
        command.add_argument("--market")
        command.add_argument("--all-supported", action="store_true")
        command.add_argument("--limit", type=int, default=50)
    discover_p = commands.add_parser("discover")
    market_options(discover_p)
    discover_p.add_argument("--include-closed", action="store_true")
    backtest_p = commands.add_parser("backtest")
    market_options(backtest_p)
    backtest_p.add_argument("--days", type=int, default=90)
    backtest_p.add_argument("--disable-volume-filter", action="store_true")
    backtest_p.add_argument("--walk-forward", action="store_true")
    backtest_p.add_argument("--train-days", type=int, default=30)
    backtest_p.add_argument("--test-days", type=int, default=7)
    scan_p = commands.add_parser("scan")
    market_options(scan_p)
    scan_p.add_argument("--once", action="store_true")
    commands.add_parser("dashboard")
    commands.add_parser("stats")
    reset_p = commands.add_parser("reset-paper")
    reset_p.add_argument("--yes", action="store_true")
    export_p = commands.add_parser("export")
    export_p.add_argument("kind", choices=["candles", "signals", "trades", "backtests"])
    smoke_p = commands.add_parser("smoke-test")
    market_options(smoke_p)
    smoke_p.set_defaults(limit=2)
    smoke_p.add_argument("--hours", type=int, default=48)
    smoke_p.add_argument("--disable-volume-filter", action="store_true")
    return root


def main() -> int:
    args = parser().parse_args()
    settings, database = setup()
    handlers = {
        "discover": discover, "backtest": run_backtest, "scan": scan, "dashboard": dashboard,
        "stats": stats, "reset-paper": reset_paper, "export": export_table,
        "smoke-test": smoke_test,
    }
    try:
        return handlers[args.command](args, settings, database)
    except ProviderError as exc:
        print(f"Polymarket API error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

