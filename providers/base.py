from __future__ import annotations

from abc import ABC, abstractmethod

from data.models import Market, PricePoint, Trade


class ProviderError(RuntimeError):
    """A recoverable upstream data error."""


class MarketDataProvider(ABC):
    @abstractmethod
    def get_markets(
        self,
        *,
        assets: tuple[str, ...] = (),
        market_id: str | None = None,
        include_closed: bool = False,
        limit: int = 100,
    ) -> list[Market]: ...

    @abstractmethod
    def get_market(self, market_id: str) -> Market | None: ...

    @abstractmethod
    def get_price_history(self, token_id: str, start_ts: int, end_ts: int) -> list[PricePoint]: ...

    @abstractmethod
    def get_trades(self, condition_id: str, token_id: str, start_ts: int, end_ts: int) -> list[Trade]: ...

    @abstractmethod
    def get_orderbook(self, token_id: str) -> dict: ...

