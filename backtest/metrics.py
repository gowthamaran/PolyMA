from __future__ import annotations

import math
from statistics import mean, pstdev
from typing import Any, Iterable


def wilson_interval(wins: int, losses: int, z: float = 1.959963984540054) -> tuple[float | None, float | None]:
    n = wins + losses
    if n == 0:
        return None, None
    p = wins / n
    denominator = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denominator
    margin = z * math.sqrt((p * (1 - p) + z * z / (4 * n)) / n) / denominator
    return max(0.0, center - margin), min(1.0, center + margin)


def streaks(statuses: Iterable[str]) -> tuple[int, int, int]:
    longest_win = longest_loss = current_loss = current_win = 0
    for status in statuses:
        if status == "WIN":
            current_win += 1
            current_loss = 0
            longest_win = max(longest_win, current_win)
        elif status == "LOSS":
            current_loss += 1
            current_win = 0
            longest_loss = max(longest_loss, current_loss)
        else:
            current_win = current_loss = 0
    return longest_win, longest_loss, current_loss


def maximum_drawdown(returns: Iterable[float]) -> float:
    equity = peak = 1.0
    drawdown = 0.0
    for value in returns:
        equity *= 1 + value
        peak = max(peak, equity)
        if peak:
            drawdown = max(drawdown, (peak - equity) / peak)
    return drawdown


def summarize(records: list[dict[str, Any]]) -> dict[str, Any]:
    valid = [row for row in records if row.get("status") in {"WIN", "LOSS", "NEUTRAL"}]
    statuses = [str(row["status"]) for row in valid]
    wins = statuses.count("WIN")
    losses = statuses.count("LOSS")
    neutral = statuses.count("NEUTRAL")
    denominator = wins + losses
    win_rate = wins / denominator if denominator else None
    ci_low, ci_high = wilson_interval(wins, losses)
    returns = [float(row.get("return", 0.0) or 0.0) for row in valid]
    win_returns = [value for value, status in zip(returns, statuses) if status == "WIN"]
    loss_returns = [value for value, status in zip(returns, statuses) if status == "LOSS"]
    positive = sum(value for value in returns if value > 0)
    negative = abs(sum(value for value in returns if value < 0))
    longest_win, longest_loss, current_loss = streaks(statuses)
    average = mean(returns) if returns else 0.0
    deviation = pstdev(returns) if len(returns) > 1 else 0.0
    return {
        "signals": len(valid),
        "wins": wins,
        "losses": losses,
        "neutral": neutral,
        "invalid": sum(1 for row in records if row.get("status") == "INVALID"),
        "win_rate": win_rate,
        "ci95_low": ci_low,
        "ci95_high": ci_high,
        "average_return": average,
        "average_win": mean(win_returns) if win_returns else 0.0,
        "average_loss": mean(loss_returns) if loss_returns else 0.0,
        "expected_value": average,
        "profit_factor": positive / negative if negative else (None if not positive else float("inf")),
        "sharpe_like": average / deviation * math.sqrt(len(returns)) if deviation else None,
        "max_drawdown": maximum_drawdown(returns),
        "longest_winning_streak": longest_win,
        "longest_losing_streak": longest_loss,
        "current_losing_streak": current_loss,
        "cumulative_return": math.prod(1 + value for value in returns) - 1 if returns else 0.0,
    }

