from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.config import Settings
from app.database import Database
from backtest.metrics import summarize


def _safe_float(value: Any) -> float:
    return float(value or 0)


def create_app(settings: Settings, database: Database) -> FastAPI:
    app = FastAPI(title="PolyMA Lab", docs_url="/api/docs", redoc_url=None)
    root = Path(__file__).parent
    templates = Environment(loader=FileSystemLoader(root / "templates"), autoescape=select_autoescape())
    app.mount("/static", StaticFiles(directory=root / "static"), name="static")

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return templates.get_template("index.html").render()

    @app.get("/api/overview")
    def overview() -> dict[str, Any]:
        records = database.query(
            "SELECT status, directional_return AS return FROM signals WHERE run_id='LIVE' AND variant_id=?",
            (f"vol-{settings.volume_multiplier:.2f}x" if not settings.disable_volume_filter else "volume-disabled",),
        )
        metrics = summarize(records)
        account_rows = database.query("SELECT * FROM paper_account WHERE id=1")
        account = account_rows[0] if account_rows else {
            "balance": settings.starting_balance, "starting_balance": settings.starting_balance,
            "realized_pnl": 0, "peak_balance": settings.starting_balance,
        }
        forward = database.query("SELECT * FROM forward_runs ORDER BY started_at DESC LIMIT 1")
        peak = _safe_float(account.get("peak_balance")) or settings.starting_balance
        drawdown = (peak - _safe_float(account.get("balance"))) / peak if peak else 0
        return {
            **metrics,
            "paper_balance": _safe_float(account.get("balance")),
            "paper_pnl": _safe_float(account.get("realized_pnl")),
            "paper_drawdown": drawdown,
            "status": forward[0]["status"] if forward else "STOPPED",
            "paper_only": True,
            "volume_filter": "DISABLED" if settings.disable_volume_filter else "ENABLED",
        }

    @app.get("/api/signals")
    def signals(
        status: str | None = None,
        asset: str | None = None,
        limit: int = Query(200, ge=1, le=2000),
    ) -> list[dict[str, Any]]:
        clauses = ["run_id='LIVE'"]
        values: list[Any] = []
        if status:
            clauses.append("status=?")
            values.append(status.upper())
        if asset:
            clauses.append("asset=?")
            values.append(asset.upper())
        values.append(limit)
        return database.query(
            f"SELECT * FROM signals WHERE {' AND '.join(clauses)} ORDER BY timestamp DESC LIMIT ?",
            tuple(values),
        )

    @app.get("/api/markets")
    def markets() -> list[dict[str, Any]]:
        return database.query(
            """SELECT market_id, condition_id, token_id, question, asset, outcome, active, closed,
            updated_at FROM markets ORDER BY updated_at DESC LIMIT 500"""
        )

    @app.get("/api/scanner")
    def scanner() -> list[dict[str, Any]]:
        return database.query(
            """SELECT c.asset, c.market_id, c.token_id, c.timestamp, c.open, c.close,
            c.volume, c.volume_source, c.price_source
            FROM candles c JOIN (
                SELECT market_id, token_id, MAX(timestamp) timestamp FROM candles GROUP BY market_id, token_id
            ) latest USING(market_id, token_id, timestamp)
            ORDER BY c.asset, c.market_id LIMIT 500"""
        )

    @app.get("/api/variants")
    def variants() -> list[dict[str, Any]]:
        rows = database.query(
            """SELECT v.variant_id, v.volume_multiplier, v.volume_filter_enabled,
            s.status, s.directional_return AS return
            FROM strategy_variants v LEFT JOIN signals s
            ON v.variant_id=s.variant_id AND s.run_id='LIVE'
            ORDER BY v.volume_multiplier"""
        )
        grouped: dict[str, list[dict[str, Any]]] = {}
        metadata: dict[str, dict[str, Any]] = {}
        for row in rows:
            grouped.setdefault(row["variant_id"], []).append(row)
            metadata[row["variant_id"]] = row
        result = []
        for variant_id, values in grouped.items():
            metrics = summarize([row for row in values if row.get("status")])
            result.append({
                "threshold": metadata[variant_id]["volume_multiplier"],
                "variant_id": variant_id,
                "volume_filter_enabled": bool(metadata[variant_id]["volume_filter_enabled"]),
                **metrics,
            })
        return result

    @app.get("/api/trades")
    def trades() -> list[dict[str, Any]]:
        return database.query("SELECT * FROM paper_trades ORDER BY opened_at DESC LIMIT 500")

    @app.get("/api/backtests")
    def backtests() -> list[dict[str, Any]]:
        rows = database.query("SELECT * FROM backtest_runs ORDER BY started_at DESC LIMIT 50")
        for row in rows:
            if row.get("report_json"):
                try:
                    row["report"] = json.loads(row.pop("report_json"))
                except json.JSONDecodeError:
                    pass
        return rows

    @app.get("/api/settings")
    def public_settings() -> dict[str, Any]:
        return {
            "candle_interval_minutes": settings.candle_interval_minutes,
            "fast_ma": settings.fast_ma,
            "slow_ma": settings.slow_ma,
            "volume_window": settings.volume_window,
            "volume_multiplier": settings.volume_multiplier,
            "volume_thresholds": settings.volume_thresholds,
            "disable_volume_filter": settings.disable_volume_filter,
            "starting_balance": settings.starting_balance,
            "trade_size": settings.trade_size,
            "slippage_bps": settings.slippage_bps,
            "spread_bps": settings.spread_bps,
            "fee_bps": settings.fee_bps,
            "telegram_enabled": settings.telegram_enabled,
            "live_trading": False,
        }

    return app

