from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class LiveTradingDisabledError(RuntimeError):
    pass


class ExecutionProvider(ABC):
    @abstractmethod
    def get_balance(self) -> float: ...

    @abstractmethod
    def get_positions(self) -> list[dict[str, Any]]: ...

    def submit_order(self, *args: Any, **kwargs: Any) -> None:
        raise LiveTradingDisabledError("Live trading is permanently disabled in PolyMA Lab")

    def cancel_order(self, *args: Any, **kwargs: Any) -> None:
        raise LiveTradingDisabledError("Live trading is permanently disabled in PolyMA Lab")


class DisabledLiveExecutionProvider(ExecutionProvider):
    def get_balance(self) -> float:
        raise LiveTradingDisabledError("No live account is configured")

    def get_positions(self) -> list[dict[str, Any]]:
        raise LiveTradingDisabledError("No live account is configured")

