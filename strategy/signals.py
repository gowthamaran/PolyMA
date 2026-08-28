from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass
from typing import Any

from data.models import Candle


@dataclass(frozen=True)
class Signal:
    signal_id: str
    observation_id: str
    variant_id: str
    market_id: str
    token_id: str
    asset: str
    timestamp: int
    open: float
    high: float
    low: float
    close: float
    volume: float | None
    ma7: float
    ma25: float
    avg_volume20: float | None
    volume_ratio: float | None
    prediction: str = "RED"
    status: str = "PENDING"

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def make_signal_id(market_id: str, token_id: str, timestamp: int, variant_id: str) -> tuple[str, str]:
    observation = hashlib.sha256(f"{market_id}|{token_id}|{timestamp}".encode()).hexdigest()[:24]
    signal = hashlib.sha256(f"{observation}|{variant_id}".encode()).hexdigest()[:32]
    return signal, observation


def grade_next_candle(signal: Signal | dict[str, Any], next_candle: Candle | None) -> tuple[str, float | None]:
    timestamp = signal.timestamp if isinstance(signal, Signal) else int(signal["timestamp"])
    if next_candle is None:
        return "INVALID", None
    if not next_candle.is_complete:
        return "PENDING", None
    if next_candle.timestamp != timestamp + 900:
        return "INVALID", None
    movement = next_candle.close - next_candle.open
    if movement < 0:
        return "WIN", next_candle.open - next_candle.close
    if movement > 0:
        return "LOSS", next_candle.open - next_candle.close
    return "NEUTRAL", 0.0

