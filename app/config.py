from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv


def _bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def _csv_float(name: str, default: str) -> tuple[float, ...]:
    return tuple(float(item.strip()) for item in os.getenv(name, default).split(",") if item.strip())


def _csv_str(name: str, default: str) -> tuple[str, ...]:
    return tuple(item.strip().upper() for item in os.getenv(name, default).split(",") if item.strip())


@dataclass(frozen=True)
class Settings:
    app_env: str = "development"
    app_host: str = "127.0.0.1"
    app_port: int = 8000
    database_path: Path = Path("data/polyma.db")
    log_level: str = "INFO"
    candle_interval_minutes: int = 15
    fast_ma: int = 7
    slow_ma: int = 25
    volume_window: int = 20
    volume_multiplier: float = 1.5
    volume_thresholds: tuple[float, ...] = (1.0, 1.25, 1.5, 1.75, 2.0, 2.5, 3.0)
    disable_volume_filter: bool = False
    starting_balance: float = 10_000.0
    trade_size: float = 100.0
    position_sizing: str = "fixed_dollar"
    max_trade_size: float = 500.0
    max_open_positions: int = 3
    max_daily_loss: float = 500.0
    max_drawdown_percent: float = 20.0
    max_consecutive_losses: int = 5
    simulated_entry_delay_seconds: int = 5
    slippage_bps: float = 10.0
    fee_bps: float = 0.0
    spread_bps: float = 20.0
    scan_poll_seconds: int = 30
    scan_lookback_hours: int = 48
    market_limit: int = 100
    assets: tuple[str, ...] = field(default_factory=lambda: ("BTC", "ETH", "SOL", "XRP"))
    telegram_enabled: bool = False
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    @classmethod
    def from_env(cls, env_file: str | None = ".env") -> "Settings":
        if env_file:
            load_dotenv(env_file, override=False)
        return cls(
            app_env=os.getenv("APP_ENV", "development"),
            app_host=os.getenv("APP_HOST", "127.0.0.1"),
            app_port=int(os.getenv("APP_PORT", "8000")),
            database_path=Path(os.getenv("DATABASE_PATH", "data/polyma.db")),
            log_level=os.getenv("LOG_LEVEL", "INFO"),
            candle_interval_minutes=int(os.getenv("CANDLE_INTERVAL_MINUTES", "15")),
            fast_ma=int(os.getenv("FAST_MA", "7")),
            slow_ma=int(os.getenv("SLOW_MA", "25")),
            volume_window=int(os.getenv("VOLUME_WINDOW", "20")),
            volume_multiplier=float(os.getenv("VOLUME_MULTIPLIER", "1.5")),
            volume_thresholds=_csv_float("VOLUME_THRESHOLDS", "1.0,1.25,1.5,1.75,2.0,2.5,3.0"),
            disable_volume_filter=_bool("DISABLE_VOLUME_FILTER"),
            starting_balance=float(os.getenv("STARTING_BALANCE", "10000")),
            trade_size=float(os.getenv("TRADE_SIZE", "100")),
            position_sizing=os.getenv("POSITION_SIZING", "fixed_dollar"),
            max_trade_size=float(os.getenv("MAX_TRADE_SIZE", "500")),
            max_open_positions=int(os.getenv("MAX_OPEN_POSITIONS", "3")),
            max_daily_loss=float(os.getenv("MAX_DAILY_LOSS", "500")),
            max_drawdown_percent=float(os.getenv("MAX_DRAWDOWN_PERCENT", "20")),
            max_consecutive_losses=int(os.getenv("MAX_CONSECUTIVE_LOSSES", "5")),
            simulated_entry_delay_seconds=int(os.getenv("SIMULATED_ENTRY_DELAY_SECONDS", "5")),
            slippage_bps=float(os.getenv("SLIPPAGE_BPS", "10")),
            fee_bps=float(os.getenv("FEE_BPS", "0")),
            spread_bps=float(os.getenv("SPREAD_BPS", "20")),
            scan_poll_seconds=int(os.getenv("SCAN_POLL_SECONDS", "30")),
            scan_lookback_hours=int(os.getenv("SCAN_LOOKBACK_HOURS", "48")),
            market_limit=int(os.getenv("MARKET_LIMIT", "100")),
            assets=_csv_str("ASSETS", "BTC,ETH,SOL,XRP"),
            telegram_enabled=_bool("TELEGRAM_ENABLED"),
            telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN", ""),
            telegram_chat_id=os.getenv("TELEGRAM_CHAT_ID", ""),
        )

    def ensure_directories(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        for path in (Path("logs"), Path("exports")):
            path.mkdir(parents=True, exist_ok=True)


settings = Settings.from_env()

