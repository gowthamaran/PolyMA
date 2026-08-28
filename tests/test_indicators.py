from strategy.indicators import sma, volume_ratio


def test_sma_windows() -> None:
    values = list(range(1, 26))
    assert sma(values, 7) == 22.0
    assert sma(values, 25) == 13.0
    assert sma(values[:6], 7) is None


def test_volume_average_and_ratio() -> None:
    average, ratio = volume_ratio(30.0, [10.0] * 20, 20)
    assert average == 10.0
    assert ratio == 3.0


def test_volume_missing_and_zero_are_not_invented() -> None:
    assert volume_ratio(None, [10.0] * 20, 20) == (None, None)
    assert volume_ratio(1.0, [0.0] * 20, 20) == (0.0, None)
    assert volume_ratio(2.0, [10.0] * 19 + [None], 20) == (None, None)

