"""PDH/PDL, Asia High/Low, and HTF bias — availability is what these test.

A level that exists is not a level you may use. PDH/PDL become usable when the
day that produced them ends; the Asia range only once the Asia window closes.
Using the Asia high at 02:00 London would be a lookahead of several hours on
every single trading day of the backtest.
"""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import pytest

from xauusd_research.engine.clock import LONDON, session_bounds, trading_day_bounds
from xauusd_research.features.bias import (
    Bias,
    bias_by_bar,
    htf_gate_flexible,
    htf_gate_strict,
    project_to_base,
    structural_bias,
)
from xauusd_research.features.levels import (
    ASIA_HIGH,
    ASIA_LOW,
    PDH,
    PDL,
    build_levels,
)
from xauusd_research.features.swings import find_swings


@pytest.fixture(scope="module")
def book(real_m15):
    return build_levels(real_m15.iloc[:40000])


# -- levels -----------------------------------------------------------------


def test_pdh_pdl_equal_the_previous_trading_days_range(real_m15, book):
    from xauusd_research.engine.resample import ny_session_keys

    m15 = real_m15.iloc[:40000]
    day_label, _ = ny_session_keys(m15.index)
    per_day = m15.groupby(day_label).agg(h=("high", "max"), l=("low", "min")).sort_index()

    days = list(book.table.index)
    for k in range(200, 215):
        today, yesterday = days[k], days[k - 1]
        levels = {lv.name: lv.price for lv in book.for_day(today.date())}
        assert levels[PDH] == pytest.approx(per_day.loc[yesterday, "h"])
        assert levels[PDL] == pytest.approx(per_day.loc[yesterday, "l"])


def test_pdh_pdl_are_usable_from_the_start_of_the_trading_day(book):
    day = list(book.table.index)[200].date()
    start, _ = trading_day_bounds(day)
    for lv in book.for_day(day):
        if lv.name in (PDH, PDL):
            assert lv.available_from == start


def test_asia_levels_are_not_usable_until_the_asia_window_closes(book):
    day = list(book.table.index)[200].date()
    asia_end = session_bounds(day, "asia_a")[1]
    asia = [lv for lv in book.for_day(day) if lv.name in (ASIA_HIGH, ASIA_LOW)]
    assert asia
    for lv in asia:
        assert lv.available_from == asia_end
        # One minute before the window closes, the level must not be offered.
        assert lv not in book.available_at(asia_end - pd.Timedelta(minutes=1), day)
        assert lv in book.available_at(asia_end, day)


def test_asia_range_only_covers_midnight_to_five_london(real_m15, book):
    m15 = real_m15.iloc[:40000]
    day = list(book.table.index)[200].date()
    start, end = session_bounds(day, "asia_a")
    window = m15[(m15.index >= start) & (m15.index < end)]
    assert len(window) > 0
    levels = {lv.name: lv.price for lv in book.for_day(day)}
    assert levels[ASIA_HIGH] == pytest.approx(window["high"].max())
    assert levels[ASIA_LOW] == pytest.approx(window["low"].min())


def test_asia_window_is_five_london_hours_in_both_dst_states(book):
    for day in (date(2013, 1, 16), date(2013, 7, 17)):
        start, end = session_bounds(day, "asia_a")
        assert end - start == pd.Timedelta(hours=5)
        assert start.tz_convert(LONDON).hour == 0
        assert end.tz_convert(LONDON).hour == 5


def test_variant_b_asia_window_is_one_hour_longer(real_m15):
    m15 = real_m15.iloc[:40000]
    a = build_levels(m15, asia_window="asia_a")
    b = build_levels(m15, asia_window="asia_b")
    day = list(a.table.index)[200].date()
    ha = {lv.name: lv.price for lv in a.for_day(day)}[ASIA_HIGH]
    hb = {lv.name: lv.price for lv in b.for_day(day)}[ASIA_HIGH]
    # A longer window can only widen the range, never narrow it.
    assert hb >= ha


def test_first_day_has_no_previous_day_levels(book):
    first = list(book.table.index)[0].date()
    names = {lv.name for lv in book.for_day(first)}
    assert PDH not in names and PDL not in names


def test_holiday_thin_days_are_flagged_by_bar_count(book):
    counts = [lv.source_bars for d in book.table.index for lv in book.for_day(d.date())]
    assert min(counts) < 88   # short days exist and are visible
    assert max(counts) >= 88  # normal days too


# -- bias -------------------------------------------------------------------


def make_swing_series(highs, lows):
    return find_swings(np.array(highs, float), np.array(lows, float), n=2)


def test_bias_needs_higher_high_AND_higher_low():
    # HH but LL -> expanding range, correctly neutral.
    high = [1, 2, 10, 2, 1, 2, 12, 2, 1]
    low = [9, 8, 5, 8, 9, 8, 3, 8, 9]
    s = make_swing_series(high, low)
    assert structural_bias(s, 8) is Bias.NEUTRAL


def test_bullish_needs_both_conditions():
    high = [1, 2, 10, 2, 1, 2, 12, 2, 1]
    low = [9, 8, 5, 8, 9, 8, 6, 8, 9]  # higher low as well
    s = make_swing_series(high, low)
    assert structural_bias(s, 8) is Bias.BULLISH


def test_bearish_is_the_mirror():
    high = [1, 2, 12, 2, 1, 2, 10, 2, 1]
    low = [9, 8, 6, 8, 9, 8, 5, 8, 9]
    s = make_swing_series(high, low)
    assert structural_bias(s, 8) is Bias.BEARISH


def test_bias_is_neutral_until_two_swings_of_each_kind_exist():
    high = [1, 2, 10, 2, 1, 2, 12, 2, 1]
    low = [9, 8, 5, 8, 9, 8, 6, 8, 9]
    s = make_swing_series(high, low)
    assert structural_bias(s, 4) is Bias.NEUTRAL  # only one of each confirmed


def test_bias_by_bar_matches_the_direct_computation():
    rng = np.random.default_rng(3)
    high = np.cumsum(rng.normal(size=300)) + 100
    low = high - rng.uniform(0.5, 2.0, size=300)
    s = find_swings(high, low, n=2)
    track = bias_by_bar(s, 300)
    for i in (10, 50, 130, 299):
        assert track[i] is structural_bias(s, i)


def test_projection_uses_only_closed_htf_bars():
    htf = [Bias.BULLISH, Bias.BEARISH, Bias.NEUTRAL]
    # No HTF bar closed yet -> neutral, not "the first one".
    assert project_to_base(htf, np.array([0, 1, 2, 3])) == [
        Bias.NEUTRAL, Bias.BULLISH, Bias.BEARISH, Bias.NEUTRAL
    ]


# -- the gate ---------------------------------------------------------------


def test_neutral_daily_always_blocks():
    for h4 in (Bias.BULLISH, Bias.BEARISH, Bias.NEUTRAL):
        assert htf_gate_flexible(Bias.NEUTRAL, h4) is Bias.NEUTRAL


def test_opposing_4h_blocks_but_neutral_4h_allows():
    assert htf_gate_flexible(Bias.BULLISH, Bias.BEARISH) is Bias.NEUTRAL
    assert htf_gate_flexible(Bias.BULLISH, Bias.NEUTRAL) is Bias.BULLISH
    assert htf_gate_flexible(Bias.BULLISH, Bias.BULLISH) is Bias.BULLISH
    assert htf_gate_flexible(Bias.BEARISH, Bias.NEUTRAL) is Bias.BEARISH


def test_strict_gate_requires_agreement():
    assert htf_gate_strict(Bias.BULLISH, Bias.NEUTRAL) is Bias.NEUTRAL
    assert htf_gate_strict(Bias.BULLISH, Bias.BULLISH) is Bias.BULLISH
    assert htf_gate_strict(Bias.BEARISH, Bias.BULLISH) is Bias.NEUTRAL


def test_strict_is_never_more_permissive_than_flexible():
    for d in Bias:
        for h in Bias:
            if htf_gate_strict(d, h) is not Bias.NEUTRAL:
                assert htf_gate_flexible(d, h) is htf_gate_strict(d, h)
