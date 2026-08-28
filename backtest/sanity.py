from __future__ import annotations

import random
from statistics import mean, pstdev
from typing import Any


def randomized_check(candidate_outcomes: list[int], strategy_wins: int, signal_count: int, iterations: int = 1000, seed: int = 42) -> dict[str, Any]:
    """Sample without replacement from eligible chronological outcomes.

    This does not prove causality. It estimates how unusual the observed win
    count is relative to equally sized random timestamp samples.
    """
    if signal_count <= 0 or signal_count > len(candidate_outcomes):
        return {"iterations": 0, "random_mean": None, "estimated_p_value": None}
    rng = random.Random(seed)
    rates = [sum(rng.sample(candidate_outcomes, signal_count)) / signal_count for _ in range(iterations)]
    strategy_rate = strategy_wins / signal_count
    return {
        "iterations": iterations,
        "strategy_win_rate": strategy_rate,
        "random_mean": mean(rates),
        "random_std": pstdev(rates) if len(rates) > 1 else 0.0,
        "estimated_p_value": (1 + sum(rate >= strategy_rate for rate in rates)) / (iterations + 1),
        "note": "Exploratory randomization check; not a causal proof.",
    }

