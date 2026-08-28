from __future__ import annotations

from typing import Any


def _pct(value: float | None) -> str:
    return "N/A" if value is None else f"{value * 100:.2f}%"


def conclusion(report: dict[str, Any], chosen_variant: str) -> tuple[str, str]:
    metrics = report["variants"].get(chosen_variant, {}).get("out_of_sample", {})
    samples = int(metrics.get("wins", 0)) + int(metrics.get("losses", 0))
    low, high = metrics.get("ci95_low"), metrics.get("ci95_high")
    if samples < 100 or low is None or high is None:
        return "INCONCLUSIVE", "The held-out sample is too small for a firm conclusion."
    if low > 0.5:
        return "SUPPORTED", "The held-out 95% interval is entirely above a 50% directional baseline."
    if high <= 0.5:
        return "NOT SUPPORTED", "The held-out 95% interval does not exceed 50%."
    return "INCONCLUSIVE", "The held-out confidence interval overlaps 50%."


def render_report(report: dict[str, Any], chosen_variant: str) -> str:
    metrics = report["variants"].get(chosen_variant, {})
    out = metrics.get("out_of_sample", {})
    label, reason = conclusion(report, chosen_variant)
    lines = [
        "=" * 64,
        "POLYMA LAB — STRATEGY REPORT",
        "=" * 64,
        f"Run: {report.get('run_id')}",
        f"Market tokens: {report.get('market_tokens', 0)}",
        f"Completed candles: {report.get('candles', 0)}",
        f"Variant: {chosen_variant}",
        f"Signals: {metrics.get('signals', 0)}",
        f"Wins / Losses / Neutral: {metrics.get('wins', 0)} / {metrics.get('losses', 0)} / {metrics.get('neutral', 0)}",
        f"Directional Win Rate: {_pct(metrics.get('win_rate'))}",
        f"95% CI: {_pct(metrics.get('ci95_low'))} – {_pct(metrics.get('ci95_high'))}",
        f"Out-of-Sample Signals: {out.get('signals', 0)}",
        f"Out-of-Sample Win Rate: {_pct(out.get('win_rate'))}",
        f"Out-of-Sample 95% CI: {_pct(out.get('ci95_low'))} – {_pct(out.get('ci95_high'))}",
        f"Expected directional return/call: {_pct(metrics.get('expected_value'))}",
        f"Max Drawdown: {_pct(metrics.get('max_drawdown'))}",
        f"Longest Losing Streak: {metrics.get('longest_losing_streak', 0)}",
        "",
        "CONCLUSION",
        label,
        reason,
        "",
        "Directional accuracy is not paper-trading profitability. Execution",
        "costs and simulated fill P&L must be evaluated separately.",
        "=" * 64,
    ]
    return "\n".join(lines)

