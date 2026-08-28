from data.aggregator import aggregate_price_points, aggregate_trades, bucket_start
from data.models import PricePoint, Trade


def test_utc_bucket_boundaries() -> None:
    assert bucket_start(900) == 900
    assert bucket_start(1799) == 900
    assert bucket_start(1800) == 1800


def test_trade_candle_ohlcv_and_completion() -> None:
    trades = [
        Trade("m", "t", 905, 0.4, 2.0, "a"),
        Trade("m", "t", 910, 0.7, 3.0, "b"),
        Trade("m", "t", 920, 0.5, 4.0, "c"),
    ]
    rows = aggregate_trades(trades, asset="BTC", as_of=1800)
    assert len(rows) == 1
    row = rows[0]
    assert (row.open, row.high, row.low, row.close) == (0.4, 0.7, 0.4, 0.5)
    assert row.volume == 9.0
    assert row.trade_count == 3
    assert row.is_complete
    assert row.volume_source == "REAL_TRADE_VOLUME"


def test_no_trade_buckets_are_not_fabricated() -> None:
    trades = [Trade("m", "t", 5, 0.4, 1.0, "a"), Trade("m", "t", 1805, 0.5, 1.0, "b")]
    rows = aggregate_trades(trades, asset="BTC", as_of=3000)
    assert [row.timestamp for row in rows] == [0, 1800]


def test_sampled_prices_have_unavailable_volume() -> None:
    rows = aggregate_price_points(
        [PricePoint("t", 10, 0.4), PricePoint("t", 20, 0.6)],
        market_id="m", asset="ETH", as_of=1000,
    )
    assert rows[0].volume is None
    assert rows[0].volume_source == "UNAVAILABLE"
    assert rows[0].price_source == "SAMPLED_PRICE_PROXY"

