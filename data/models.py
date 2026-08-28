from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True)
class Market:
    market_id: str
    condition_id: str
    question: str
    slug: str
    asset: str
    token_id: str
    complementary_token_id: str | None
    outcome: str
    active: bool
    closed: bool
    start_time: int | None = None
    end_time: int | None = None
    metadata: dict[str, Any] | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class Trade:
    market_id: str
    token_id: str
    timestamp: int
    price: float
    size: float
    trade_id: str


@dataclass(frozen=True)
class PricePoint:
    token_id: str
    timestamp: int
    price: float


@dataclass(frozen=True)
class Candle:
    timestamp: int
    market_id: str
    token_id: str
    asset: str
    open: float
    high: float
    low: float
    close: float
    volume: float | None
    trade_count: int
    is_complete: bool
    volume_source: str = "REAL_TRADE_VOLUME"
    price_source: str = "TRADES"

    @property
    def end_timestamp(self) -> int:
        return self.timestamp + 900

    @property
    def utc_time(self) -> str:
        return datetime.fromtimestamp(self.timestamp, tz=timezone.utc).isoformat()

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

