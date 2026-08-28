from __future__ import annotations

from collections.abc import Sequence


def sma(values: Sequence[float], window: int) -> float | None:
    if window <= 0:
        raise ValueError("window must be positive")
    if len(values) < window:
        return None
    sample = values[-window:]
    return sum(sample) / window


def volume_ratio(current: float | None, historical: Sequence[float | None], window: int) -> tuple[float | None, float | None]:
    if current is None or len(historical) < window:
        return None, None
    sample = list(historical[-window:])
    if any(value is None for value in sample):
        return None, None
    average = sum(float(value) for value in sample) / window
    if average == 0:
        return average, None
    return average, current / average

