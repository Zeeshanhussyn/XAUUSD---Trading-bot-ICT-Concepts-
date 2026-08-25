"""Fractal swings and their confirmation lag.

The lag is the point. A swing that becomes visible at its own bar rather than
`n` bars later is the single easiest way to make a backtest print a fake edge.
"""

from __future__ import annotations

import numpy as np
import pytest

from xauusd_research.features.swings import SwingType, find_swings


def series(highs, lows):
    return np.array(highs, dtype=float), np.array(lows, dtype=float)


def test_finds_an_obvious_swing_high():
    #                          0    1    2    3    4
    high, low = series([10, 11, 15, 11, 10], [1, 1, 1, 1, 1])
    s = find_swings(high, low, n=2)
    highs = [x for x in s.all if x.kind is SwingType.HIGH]
    assert len(highs) == 1
    assert highs[0].index == 2
    assert highs[0].price == 15.0


def test_swing_is_confirmed_exactly_n_bars_later():
    high, low = series([10, 11, 15, 11, 10], [1, 1, 1, 1, 1])
    s = find_swings(high, low, n=2)
    swing = [x for x in s.all if x.kind is SwingType.HIGH][0]
    assert swing.confirmed_at == swing.index + 2 == 4


def test_swing_is_invisible_until_its_confirmation_bar():
    high, low = series([10, 11, 15, 11, 10], [1, 1, 1, 1, 1])
    s = find_swings(high, low, n=2)
    for i in (0, 1, 2, 3):
        assert s.last(i, SwingType.HIGH) is None, f"swing leaked at bar {i}"
    assert s.last(4, SwingType.HIGH) is not None


def test_n3_lags_more_than_n2():
    high = np.array([10, 11, 12, 20, 12, 11, 10], dtype=float)
    low = np.ones(7)
    assert find_swings(high, low, n=2).all[0].confirmed_at == 5
    assert find_swings(high, low, n=3).all[0].confirmed_at == 6


def test_equal_highs_are_not_a_swing():
    # A tie on either side disqualifies it — equal highs are a WP8 tag, not
    # structure.
    high, low = series([10, 15, 15, 11, 10], [1, 1, 1, 1, 1])
    s = find_swings(high, low, n=2)
    assert [x for x in s.all if x.kind is SwingType.HIGH] == []


def test_edges_of_the_series_can_never_be_swings():
    high = np.array([99, 98, 1, 98, 99], dtype=float)
    low = np.array([1, 2, 50, 2, 1], dtype=float)
    s = find_swings(high, low, n=2)
    assert all(2 <= x.index <= 2 for x in s.all)


def test_finds_swing_lows_symmetrically():
    high, low = series([9, 9, 9, 9, 9], [10, 9, 5, 9, 10])
    s = find_swings(high, low, n=2)
    lows = [x for x in s.all if x.kind is SwingType.LOW]
    assert len(lows) == 1
    assert lows[0].index == 2 and lows[0].price == 5.0


def test_last_returns_the_most_recent_by_bar_not_by_confirmation():
    # Two swing highs; the later one must win once both are confirmed.
    high = np.array([1, 2, 10, 2, 1, 2, 12, 2, 1], dtype=float)
    low = np.full(9, 0.5)
    s = find_swings(high, low, n=2)
    assert s.last(4, SwingType.HIGH).index == 2
    assert s.last(8, SwingType.HIGH).index == 6
    assert s.last(8, SwingType.HIGH).price == 12.0


def test_last_n_is_ordered_oldest_to_newest():
    high = np.array([1, 2, 10, 2, 1, 2, 12, 2, 1], dtype=float)
    low = np.full(9, 0.5)
    s = find_swings(high, low, n=2)
    got = s.last_n(8, SwingType.HIGH, 2)
    assert [x.index for x in got] == [2, 6]


def test_available_at_is_monotonic():
    rng = np.random.default_rng(7)
    high = np.cumsum(rng.normal(size=400)) + 100
    low = high - rng.uniform(0.5, 2.0, size=400)
    s = find_swings(high, low, n=2)
    prev = 0
    for i in range(0, 400, 7):
        now = len(s.available_at(i))
        assert now >= prev
        prev = now
    assert prev == len(s)


def test_no_swing_is_ever_returned_before_its_confirmation_bar():
    rng = np.random.default_rng(11)
    high = np.cumsum(rng.normal(size=800)) + 100
    low = high - rng.uniform(0.5, 2.0, size=800)
    s = find_swings(high, low, n=2)
    for i in range(0, 800, 13):
        for sw in s.available_at(i):
            assert sw.confirmed_at <= i


def test_rejects_bad_inputs():
    with pytest.raises(ValueError):
        find_swings(np.ones(5), np.ones(4), n=2)
    with pytest.raises(ValueError):
        find_swings(np.ones(5), np.ones(5), n=0)
