from __future__ import annotations

import hashlib
import json
import logging
import re
import time
from datetime import datetime
from typing import Any, Callable

import httpx

from data.models import Market, PricePoint, Trade
from providers.base import MarketDataProvider, ProviderError

logger = logging.getLogger("polyma.provider")

GAMMA_URL = "https://gamma-api.polymarket.com"
CLOB_URL = "https://clob.polymarket.com"
DATA_URL = "https://data-api.polymarket.com"

ASSET_PATTERNS: dict[str, tuple[str, ...]] = {
    "BTC": (r"\bBTC\b", r"\bBITCOIN\b"),
    "ETH": (r"\bETH\b", r"\bETHEREUM\b"),
    "SOL": (r"\bSOL\b", r"\bSOLANA\b"),
    "XRP": (r"\bXRP\b", r"\bRIPPLE\b"),
}

ASSET_TAG_SLUGS = {"BTC": "bitcoin", "ETH": "ethereum", "SOL": "solana", "XRP": "xrp"}


def _parse_json_array(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return [str(item) for item in parsed] if isinstance(parsed, list) else []
        except json.JSONDecodeError:
            return []
    return []


def _epoch(value: Any) -> int | None:
    if not value:
        return None
    if isinstance(value, (int, float)):
        return int(value)
    try:
        return int(datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp())
    except ValueError:
        return None


def infer_asset(payload: dict[str, Any]) -> str:
    tags = payload.get("tags") or []
    tag_text = " ".join(str(t.get("label", "") if isinstance(t, dict) else t) for t in tags)
    text = " ".join(
        str(payload.get(key, "")) for key in ("question", "title", "slug", "description")
    ) + " " + tag_text
    upper = text.upper().replace("-", " ")
    for asset, patterns in ASSET_PATTERNS.items():
        if any(re.search(pattern, upper) for pattern in patterns):
            return asset
    return "OTHER"


class PolymarketProvider(MarketDataProvider):
    """Public, read-only Polymarket provider.

    Gamma is used for market discovery, CLOB for sampled price history/books,
    and Data API trades for reconstructing real 15-minute traded volume. No
    authentication, wallet, or order endpoint is used anywhere in this class.
    """

    def __init__(self, timeout: float = 20.0, retries: int = 4, client: httpx.Client | None = None):
        self.client = client or httpx.Client(
            timeout=timeout,
            headers={"User-Agent": "PolyMA-Lab/1.0"},
            trust_env=False,
        )
        self.retries = retries

    def close(self) -> None:
        self.client.close()

    def _request(self, method: str, url: str, **kwargs: Any) -> Any:
        error: Exception | None = None
        for attempt in range(self.retries):
            try:
                response = self.client.request(method, url, **kwargs)
                if response.status_code == 429 or response.status_code >= 500:
                    retry_after = float(response.headers.get("retry-after", 0) or 0)
                    time.sleep(max(retry_after, min(8.0, 0.5 * (2**attempt))))
                    continue
                response.raise_for_status()
                return response.json()
            except (httpx.HTTPError, ValueError) as exc:
                error = exc
                if attempt + 1 < self.retries:
                    time.sleep(min(8.0, 0.5 * (2**attempt)))
        raise ProviderError(f"Polymarket request failed after {self.retries} attempts: {error}")

    def _normalize_market(self, raw: dict[str, Any]) -> list[Market]:
        tokens = _parse_json_array(raw.get("clobTokenIds"))
        outcomes = _parse_json_array(raw.get("outcomes"))
        if not tokens:
            return []
        condition_id = str(raw.get("conditionId") or raw.get("condition_id") or "")
        market_id = str(raw.get("id") or condition_id)
        asset = infer_asset(raw)
        normalized: list[Market] = []
        for index, token in enumerate(tokens):
            normalized.append(
                Market(
                    market_id=market_id,
                    condition_id=condition_id,
                    question=str(raw.get("question") or raw.get("title") or "Unknown market"),
                    slug=str(raw.get("slug") or ""),
                    asset=asset,
                    token_id=token,
                    complementary_token_id=tokens[1 - index] if len(tokens) == 2 else None,
                    outcome=outcomes[index] if index < len(outcomes) else str(index),
                    active=bool(raw.get("active", False)),
                    closed=bool(raw.get("closed", False)),
                    start_time=_epoch(raw.get("startDate") or raw.get("start_date")),
                    end_time=_epoch(raw.get("endDate") or raw.get("end_date")),
                    metadata=raw,
                )
            )
        return normalized

    def _tag_id(self, slug: str) -> str | None:
        payload = self._request("GET", f"{GAMMA_URL}/tags/slug/{slug}")
        return str(payload.get("id")) if isinstance(payload, dict) and payload.get("id") else None

    def _markets_by_asset_tags(self, assets: set[str], include_closed: bool, limit: int) -> list[Market]:
        rows: list[Market] = []
        statuses = (False, True) if include_closed else (False,)
        per_request = min(100, max(10, limit))
        for asset in sorted(assets):
            slug = ASSET_TAG_SLUGS.get(asset)
            if not slug:
                continue
            tag_id = self._tag_id(slug)
            if not tag_id:
                continue
            for closed in statuses:
                cursor: str | None = None
                while len([row for row in rows if row.asset == asset]) < limit * 2:
                    params: dict[str, Any] = {
                        "tag_id": tag_id,
                        "closed": str(closed).lower(),
                        "limit": per_request,
                    }
                    if cursor:
                        params["after_cursor"] = cursor
                    payload = self._request("GET", f"{GAMMA_URL}/markets/keyset", params=params)
                    if not isinstance(payload, dict):
                        break
                    raw_markets = payload.get("markets", [])
                    for raw in raw_markets:
                        if isinstance(raw, dict):
                            normalized = self._normalize_market(raw)
                            # The official tag is authoritative even if a terse title
                            # does not contain the asset name.
                            rows.extend(
                                Market(**({**item.as_dict(), "asset": asset})) for item in normalized
                            )
                    cursor = payload.get("next_cursor")
                    if not raw_markets or not cursor:
                        break
        return rows

    def get_markets(
        self,
        *,
        assets: tuple[str, ...] = (),
        market_id: str | None = None,
        include_closed: bool = False,
        limit: int = 100,
    ) -> list[Market]:
        if market_id:
            raw = self._request("GET", f"{GAMMA_URL}/markets/{market_id}")
            rows = self._normalize_market(raw) if isinstance(raw, dict) else []
        elif assets:
            rows = self._markets_by_asset_tags({asset.upper() for asset in assets}, include_closed, limit)
        else:
            rows: list[Market] = []
            offset = 0
            page_size = min(500, max(1, limit))
            while len(rows) < limit:
                params = {
                    "limit": page_size,
                    "offset": offset,
                    "order": "volume24hr",
                    "ascending": "false",
                }
                if not include_closed:
                    params.update({"active": "true", "closed": "false"})
                payload = self._request("GET", f"{GAMMA_URL}/markets", params=params)
                if not isinstance(payload, list) or not payload:
                    break
                for raw in payload:
                    if isinstance(raw, dict):
                        rows.extend(self._normalize_market(raw))
                if len(payload) < page_size:
                    break
                offset += page_size
                if offset >= max(limit * 4, 1000):
                    break
        allowed = {asset.upper() for asset in assets}
        if allowed:
            rows = [market for market in rows if market.asset in allowed]
        unique: dict[tuple[str, str], Market] = {(m.condition_id, m.token_id): m for m in rows}
        return list(unique.values())[: limit * 2]

    def get_market(self, market_id: str) -> Market | None:
        rows = self.get_markets(market_id=market_id, include_closed=True, limit=1)
        return rows[0] if rows else None

    def get_price_history(self, token_id: str, start_ts: int, end_ts: int) -> list[PricePoint]:
        payload = self._request(
            "GET",
            f"{CLOB_URL}/prices-history",
            params={"market": token_id, "startTs": start_ts, "endTs": end_ts, "fidelity": 1},
        )
        points: dict[int, PricePoint] = {}
        for raw in payload.get("history", []) if isinstance(payload, dict) else []:
            try:
                point = PricePoint(token_id, int(raw["t"]), float(raw["p"]))
                if 0 <= point.price <= 1:
                    points[point.timestamp] = point
            except (KeyError, TypeError, ValueError):
                logger.warning("malformed_price_point")
        return sorted(points.values(), key=lambda p: p.timestamp)

    def get_trades(self, condition_id: str, token_id: str, start_ts: int, end_ts: int) -> list[Trade]:
        rows: list[Trade] = []
        offset = 0
        while offset <= 10_000:
            payload = self._request(
                "GET",
                f"{DATA_URL}/trades",
                params={
                    "market": condition_id,
                    "start": start_ts,
                    "end": end_ts,
                    "limit": 1000,
                    "offset": offset,
                    "takerOnly": "true",
                },
            )
            if not isinstance(payload, list):
                raise ProviderError("Malformed Data API trades response")
            for raw in payload:
                try:
                    if str(raw.get("asset")) != str(token_id):
                        continue
                    fingerprint = "|".join(
                        str(raw.get(key, ""))
                        for key in ("transactionHash", "asset", "timestamp", "price", "size", "proxyWallet")
                    )
                    trade = Trade(
                        market_id=condition_id,
                        token_id=str(raw["asset"]),
                        timestamp=int(raw["timestamp"]),
                        price=float(raw["price"]),
                        size=float(raw["size"]),
                        trade_id=hashlib.sha256(fingerprint.encode()).hexdigest(),
                    )
                    if start_ts <= trade.timestamp <= end_ts and 0 <= trade.price <= 1 and trade.size >= 0:
                        rows.append(trade)
                except (KeyError, TypeError, ValueError):
                    logger.warning("malformed_trade")
            if len(payload) < 1000:
                break
            offset += 1000
        return sorted({trade.trade_id: trade for trade in rows}.values(), key=lambda t: (t.timestamp, t.trade_id))

    def get_orderbook(self, token_id: str) -> dict:
        payload = self._request("GET", f"{CLOB_URL}/book", params={"token_id": token_id})
        return payload if isinstance(payload, dict) else {}


class RetryingCall:
    """Small injectable retry helper used by failure-recovery tests."""

    def __init__(self, attempts: int = 3):
        self.attempts = attempts

    def run(self, callback: Callable[[], Any]) -> Any:
        last: Exception | None = None
        for attempt in range(self.attempts):
            try:
                return callback()
            except Exception as exc:  # callback controls the exception type
                last = exc
                if attempt + 1 < self.attempts:
                    time.sleep(0.01 * (2**attempt))
        raise ProviderError(str(last))
