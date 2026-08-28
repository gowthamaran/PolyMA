from __future__ import annotations

import json
import hashlib
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterable, Iterator

from data.models import Candle, Market


SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS markets (
    market_id TEXT NOT NULL,
    condition_id TEXT NOT NULL,
    token_id TEXT NOT NULL,
    complementary_token_id TEXT,
    question TEXT NOT NULL,
    slug TEXT NOT NULL,
    asset TEXT NOT NULL,
    outcome TEXT NOT NULL,
    active INTEGER NOT NULL,
    closed INTEGER NOT NULL,
    start_time INTEGER,
    end_time INTEGER,
    metadata_json TEXT,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (condition_id, token_id)
);

CREATE TABLE IF NOT EXISTS candles (
    market_id TEXT NOT NULL,
    token_id TEXT NOT NULL,
    asset TEXT NOT NULL,
    timestamp INTEGER NOT NULL,
    open REAL NOT NULL,
    high REAL NOT NULL,
    low REAL NOT NULL,
    close REAL NOT NULL,
    volume REAL,
    trade_count INTEGER NOT NULL,
    is_complete INTEGER NOT NULL,
    volume_source TEXT NOT NULL,
    price_source TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (market_id, token_id, timestamp)
);

CREATE TABLE IF NOT EXISTS strategy_variants (
    variant_id TEXT PRIMARY KEY,
    fast_ma INTEGER NOT NULL,
    slow_ma INTEGER NOT NULL,
    volume_window INTEGER NOT NULL,
    volume_multiplier REAL,
    volume_filter_enabled INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS signals (
    signal_id TEXT PRIMARY KEY,
    observation_id TEXT NOT NULL,
    run_id TEXT NOT NULL DEFAULT 'LIVE',
    variant_id TEXT NOT NULL,
    market_id TEXT NOT NULL,
    token_id TEXT NOT NULL,
    asset TEXT NOT NULL,
    timestamp INTEGER NOT NULL,
    open REAL NOT NULL,
    high REAL NOT NULL,
    low REAL NOT NULL,
    close REAL NOT NULL,
    volume REAL,
    ma7 REAL NOT NULL,
    ma25 REAL NOT NULL,
    avg_volume20 REAL,
    volume_ratio REAL,
    prediction TEXT NOT NULL DEFAULT 'RED',
    status TEXT NOT NULL DEFAULT 'PENDING',
    next_open REAL,
    next_close REAL,
    directional_return REAL,
    split_name TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    graded_at TEXT,
    UNIQUE (market_id, token_id, timestamp, variant_id, run_id)
);

CREATE TABLE IF NOT EXISTS paper_trades (
    trade_id TEXT PRIMARY KEY,
    signal_id TEXT NOT NULL UNIQUE,
    market_id TEXT NOT NULL,
    token_id TEXT NOT NULL,
    status TEXT NOT NULL,
    side TEXT NOT NULL,
    size_dollars REAL NOT NULL,
    entry_price REAL NOT NULL,
    exit_price REAL,
    quantity REAL NOT NULL,
    fees REAL NOT NULL DEFAULT 0,
    pnl REAL,
    opened_at INTEGER NOT NULL,
    closed_at INTEGER,
    assumptions_json TEXT NOT NULL,
    FOREIGN KEY(signal_id) REFERENCES signals(signal_id)
);

CREATE TABLE IF NOT EXISTS paper_account (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    starting_balance REAL NOT NULL,
    balance REAL NOT NULL,
    available_balance REAL NOT NULL,
    peak_balance REAL NOT NULL,
    realized_pnl REAL NOT NULL DEFAULT 0,
    consecutive_losses INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS backtest_runs (
    run_id TEXT PRIMARY KEY,
    started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finished_at TEXT,
    parameters_json TEXT NOT NULL,
    period_start INTEGER,
    period_end INTEGER,
    market_count INTEGER NOT NULL DEFAULT 0,
    candle_count INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL,
    report_json TEXT
);

CREATE TABLE IF NOT EXISTS forward_runs (
    run_id TEXT PRIMARY KEY,
    started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    stopped_at TEXT,
    status TEXT NOT NULL,
    last_heartbeat TEXT
);

CREATE TABLE IF NOT EXISTS daily_statistics (
    date TEXT NOT NULL,
    variant_id TEXT NOT NULL,
    signals INTEGER NOT NULL,
    wins INTEGER NOT NULL,
    losses INTEGER NOT NULL,
    neutral INTEGER NOT NULL,
    pnl REAL NOT NULL,
    PRIMARY KEY (date, variant_id)
);

CREATE INDEX IF NOT EXISTS idx_candles_asset_time ON candles(asset, timestamp);
CREATE INDEX IF NOT EXISTS idx_candles_token_time ON candles(token_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_signals_status_time ON signals(status, timestamp);
CREATE INDEX IF NOT EXISTS idx_signals_variant_split ON signals(variant_id, split_name);
CREATE INDEX IF NOT EXISTS idx_paper_trades_status ON paper_trades(status);
"""


class Database:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        connection = self.connect()
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self) -> None:
        with self.transaction() as connection:
            connection.executescript(SCHEMA)

    def upsert_market(self, market: Market) -> None:
        with self.transaction() as connection:
            connection.execute(
                """INSERT INTO markets (
                    market_id, condition_id, token_id, complementary_token_id, question, slug,
                    asset, outcome, active, closed, start_time, end_time, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(condition_id, token_id) DO UPDATE SET
                    market_id=excluded.market_id, complementary_token_id=excluded.complementary_token_id,
                    question=excluded.question, slug=excluded.slug, asset=excluded.asset,
                    outcome=excluded.outcome, active=excluded.active, closed=excluded.closed,
                    start_time=excluded.start_time, end_time=excluded.end_time,
                    metadata_json=excluded.metadata_json, updated_at=CURRENT_TIMESTAMP""",
                (
                    market.market_id, market.condition_id, market.token_id, market.complementary_token_id,
                    market.question, market.slug, market.asset, market.outcome, int(market.active),
                    int(market.closed), market.start_time, market.end_time,
                    json.dumps(market.metadata or {}, default=str),
                ),
            )

    def upsert_candles(self, candles: Iterable[Candle]) -> int:
        rows = list(candles)
        if not rows:
            return 0
        with self.transaction() as connection:
            connection.executemany(
                """INSERT INTO candles (
                    market_id, token_id, asset, timestamp, open, high, low, close, volume,
                    trade_count, is_complete, volume_source, price_source
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(market_id, token_id, timestamp) DO UPDATE SET
                    open=excluded.open, high=excluded.high, low=excluded.low, close=excluded.close,
                    volume=excluded.volume, trade_count=excluded.trade_count,
                    is_complete=excluded.is_complete, volume_source=excluded.volume_source,
                    price_source=excluded.price_source""",
                [
                    (
                        c.market_id, c.token_id, c.asset, c.timestamp, c.open, c.high, c.low,
                        c.close, c.volume, c.trade_count, int(c.is_complete), c.volume_source,
                        c.price_source,
                    )
                    for c in rows
                ],
            )
        return len(rows)

    def register_variant(
        self, variant_id: str, fast_ma: int, slow_ma: int, volume_window: int,
        volume_multiplier: float | None, volume_filter_enabled: bool,
    ) -> None:
        with self.transaction() as connection:
            connection.execute(
                """INSERT OR REPLACE INTO strategy_variants
                (variant_id, fast_ma, slow_ma, volume_window, volume_multiplier, volume_filter_enabled)
                VALUES (?, ?, ?, ?, ?, ?)""",
                (variant_id, fast_ma, slow_ma, volume_window, volume_multiplier, int(volume_filter_enabled)),
            )

    def insert_signal(self, signal: Any, run_id: str | None = None, split_name: str | None = None) -> str | None:
        values = signal.as_dict() if hasattr(signal, "as_dict") else dict(signal)
        storage_id = values["signal_id"]
        if run_id:
            storage_id = hashlib.sha256(f"{storage_id}|{run_id}".encode()).hexdigest()[:32]
        with self.transaction() as connection:
            cursor = connection.execute(
                """INSERT OR IGNORE INTO signals (
                    signal_id, observation_id, run_id, variant_id, market_id, token_id, asset,
                    timestamp, open, high, low, close, volume, ma7, ma25, avg_volume20,
                    volume_ratio, prediction, status, split_name
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    storage_id, values["observation_id"], run_id or "LIVE", values["variant_id"],
                    values["market_id"], values["token_id"], values["asset"], values["timestamp"],
                    values["open"], values["high"], values["low"], values["close"],
                    values.get("volume"), values["ma7"], values["ma25"],
                    values.get("avg_volume20"), values.get("volume_ratio"), values.get("prediction", "RED"),
                    values.get("status", "PENDING"), split_name,
                ),
            )
            return storage_id if cursor.rowcount == 1 else None

    def grade_signal(
        self, signal_id: str, status: str, next_open: float, next_close: float,
        directional_return: float,
    ) -> None:
        with self.transaction() as connection:
            connection.execute(
                """UPDATE signals SET status=?, next_open=?, next_close=?, directional_return=?,
                graded_at=CURRENT_TIMESTAMP WHERE signal_id=? AND status='PENDING'""",
                (status, next_open, next_close, directional_return, signal_id),
            )

    def get_candles(self, market_id: str | None = None, token_id: str | None = None) -> list[dict[str, Any]]:
        clauses = ["is_complete=1"]
        values: list[Any] = []
        if market_id:
            clauses.append("market_id=?")
            values.append(market_id)
        if token_id:
            clauses.append("token_id=?")
            values.append(token_id)
        with self.connect() as connection:
            rows = connection.execute(
                f"SELECT * FROM candles WHERE {' AND '.join(clauses)} ORDER BY timestamp", values
            ).fetchall()
        return [dict(row) for row in rows]

    def pending_signals(self) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute("SELECT * FROM signals WHERE status='PENDING' AND run_id='LIVE' ORDER BY timestamp").fetchall()
        return [dict(row) for row in rows]

    def query(self, sql: str, parameters: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        with self.connect() as connection:
            return [dict(row) for row in connection.execute(sql, parameters).fetchall()]

    def execute(self, sql: str, parameters: tuple[Any, ...] = ()) -> int:
        with self.transaction() as connection:
            cursor = connection.execute(sql, parameters)
            return cursor.rowcount

    def start_backtest(self, run_id: str, parameters: dict[str, Any], period_start: int | None, period_end: int | None) -> None:
        with self.transaction() as connection:
            connection.execute(
                """INSERT INTO backtest_runs
                (run_id, parameters_json, period_start, period_end, status) VALUES (?, ?, ?, ?, 'RUNNING')""",
                (run_id, json.dumps(parameters), period_start, period_end),
            )

    def finish_backtest(self, run_id: str, market_count: int, candle_count: int, report: dict[str, Any]) -> None:
        with self.transaction() as connection:
            connection.execute(
                """UPDATE backtest_runs SET finished_at=CURRENT_TIMESTAMP, market_count=?, candle_count=?,
                status='COMPLETED', report_json=? WHERE run_id=?""",
                (market_count, candle_count, json.dumps(report, default=str), run_id),
            )

    def ensure_account(self, starting_balance: float) -> None:
        with self.transaction() as connection:
            connection.execute(
                """INSERT OR IGNORE INTO paper_account
                (id, starting_balance, balance, available_balance, peak_balance)
                VALUES (1, ?, ?, ?, ?)""",
                (starting_balance, starting_balance, starting_balance, starting_balance),
            )

    def reset_account(self, starting_balance: float) -> None:
        with self.transaction() as connection:
            connection.execute("DELETE FROM paper_trades")
            connection.execute("DELETE FROM paper_account")
        self.ensure_account(starting_balance)
