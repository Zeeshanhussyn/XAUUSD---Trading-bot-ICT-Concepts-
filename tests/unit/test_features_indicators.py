"""ATR — the standard Wilder definition, and no partial averages standing in for full ones."""

from __future__ import annotations

import numpy as np
import pytest

from xauusd_research.features.indicators import atr, true_range


def test_true_range_has_no_value_on_the_first_bar():
    tr = true_range([10, 11], [9, 10], [9.5, 10.5])
    assert np.isnan(tr[0])          # there is no previous close
    assert np.isfinite(tr[1])


def test_true_range_takes_the_largest_of_the_three_measures():
    # Bar 1: high-low = 2, |high-prevclose| = 4, |low-prevclose| = 2  -> 4
    tr = true_range([100, 104], [100, 102], [100, 103])
    assert tr[1] == pytest.approx(4.0)


def test_true_range_covers_a_gap_down():
    # Gapping below the previous close: |low - prev_close| dominates.
    tr = true_range([100, 96], [100, 94], [100, 95])
    assert tr[1] == pytest.approx(6.0)


def test_atr_is_nan_until_the_window_is_full():
    n = 20
    high = np.arange(n, dtype=float) + 10
    low = high - 1
    close = high - 0.5
    a = atr(high, low, close, period=14)
    assert np.all(np.isnan(a[:14]))
    assert np.isfinite(a[14])


def test_atr_seeds_with_the_simple_mean_then_smooths():
    rng = np.random.default_rng(2)
    close = np.cumsum(rng.normal(size=60)) + 100
    high = close + 1.0
    low = close - 1.0
    period = 14
    a = atr(high, low, close, period)
    tr = true_range(high, low, close)
    assert a[period] == pytest.approx(np.mean(tr[1 : period + 1]))
    # Wilder smoothing, one step.
    expected = (a[period] * (period - 1) + tr[period + 1]) / period
    assert a[period + 1] == pytest.approx(expected)


def test_atr_of_a_constant_range_series_equals_that_range():
    n = 50
    close = np.full(n, 100.0)
    high = close + 1.0
    low = close - 1.0
    a = atr(high, low, close, period=14)
    assert a[-1] == pytest.approx(2.0)


def test_atr_uses_no_future_bars():
    """Truncating the series must not change any earlier ATR value."""
    rng = np.random.default_rng(9)
    close = np.cumsum(rng.normal(size=400)) + 1300
    high = close + rng.uniform(0.2, 2.0, size=400)
    low = close - rng.uniform(0.2, 2.0, size=400)
    full = atr(high, low, close)
    short = atr(high[:200], low[:200], close[:200])
    np.testing.assert_allclose(full[:200], short, equal_nan=True)


def test_atr_is_positive_and_finite_on_real_data(real_m15):
    m15 = real_m15.iloc[:5000]
    a = atr(m15["high"].to_numpy(float), m15["low"].to_numpy(float), m15["close"].to_numpy(float))
    valid = a[np.isfinite(a)]
    assert len(valid) > 4900
    assert (valid > 0).all()


def test_bad_period_is_rejected():
    with pytest.raises(ValueError):
        atr([1, 2, 3], [1, 2, 3], [1, 2, 3], period=0)
