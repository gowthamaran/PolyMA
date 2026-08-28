from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger("polyma.telegram")


class TelegramNotifier:
    def __init__(self, enabled: bool, token: str, chat_id: str):
        self.enabled = bool(enabled and token and chat_id)
        self.token = token
        self.chat_id = chat_id

    def send(self, text: str) -> bool:
        if not self.enabled:
            return False
        try:
            response = httpx.post(
                f"https://api.telegram.org/bot{self.token}/sendMessage",
                json={"chat_id": self.chat_id, "text": text},
                timeout=15,
            )
            response.raise_for_status()
            return True
        except httpx.HTTPError:
            logger.exception("telegram_send_failed")
            return False

    def signal(self, signal: dict[str, Any], stats: dict[str, Any]) -> bool:
        ratio = signal.get("volume_ratio")
        volume = f"{ratio:.2f}x average" if ratio is not None else "filter disabled / unavailable"
        text = (
            "🔴 PolyMA SIGNAL\n\n"
            f"Market: {signal['asset']} — {signal['market_id']}\n"
            f"Time: {signal['timestamp']} UTC epoch\n\n"
            f"Close: {signal['close']:.4f}\nMA7: {signal['ma7']:.4f}\nMA25: {signal['ma25']:.4f}\n"
            f"Volume: {volume}\n\n"
            "Condition:\n✓ Green candle\n✓ Close > MA7\n✓ Close < MA25\n✓ Volume rule\n\n"
            "Prediction: NEXT 15M CANDLE → RED\n\nStatus: PAPER TRADE OPENED\n"
            "No real trade has been placed."
        )
        return self.send(text)

    def graded(self, signal: dict[str, Any], stats: dict[str, Any]) -> bool:
        icon = {"WIN": "✅", "LOSS": "❌", "NEUTRAL": "➖", "INVALID": "⚠️"}.get(signal["status"], "ℹ️")
        rate = stats.get("win_rate")
        rate_text = f"{rate * 100:.2f}%" if rate is not None else "N/A"
        return self.send(
            f"{icon} {signal['status']} — PolyMA PAPER\n\n"
            f"Signals: {stats.get('signals', 0)}\nWins: {stats.get('wins', 0)}\n"
            f"Losses: {stats.get('losses', 0)}\nNeutral: {stats.get('neutral', 0)}\n"
            f"Directional Win Rate: {rate_text}\n\nNo real trade was placed."
        )

