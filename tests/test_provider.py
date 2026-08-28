import pytest

from providers.base import ProviderError
from providers.polymarket import RetryingCall, infer_asset


def test_asset_inference_uses_metadata_text() -> None:
    assert infer_asset({"question": "Will Bitcoin be above $100k?"}) == "BTC"
    assert infer_asset({"slug": "eth-up-or-down"}) == "ETH"
    assert infer_asset({"tags": [{"label": "Solana"}]}) == "SOL"


def test_api_failure_recovery() -> None:
    attempts = 0
    def flaky() -> str:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise RuntimeError("temporary")
        return "ok"
    assert RetryingCall(3).run(flaky) == "ok"
    assert attempts == 3


def test_api_failure_exhaustion() -> None:
    with pytest.raises(ProviderError):
        RetryingCall(2).run(lambda: (_ for _ in ()).throw(RuntimeError("down")))

