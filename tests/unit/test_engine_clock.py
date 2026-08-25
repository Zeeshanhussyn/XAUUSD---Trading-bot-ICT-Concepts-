"""Trading-day and session-window arithmetic, including daylight-saving edges."""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from xauusd_research.engine.clock import (
    TICK_SIZE,
    bar_close_index,
    bar_close_time,
    in_session,
    session_bounds,
    trading_day,
    trading_day_bounds,
    trading_day_index,
)


def utc(s: str) -> pd.Timestamp:
    return pd.Timestamp(s, tz="UTC")


# -- bar labels are OPEN times ---------------------------------------------


def test_bar_close_time_is_open_plus_duration():
    t = utc("2016-06-15 08:00")
    assert bar_close_time(t, "m15") == utc("2016-06-15 08:15")
    assert bar_close_time(t, "h1") == utc("2016-06-15 09:00")
    assert bar_close_time(t, "h4") == utc("2016-06-15 12:00")
    assert bar_close_time(t, "d1") == utc("2016-06-16 08:00")


def test_bar_close_index_matches_scalar():
    idx = pd.DatetimeIndex([utc("2016-06-15 08:00"), utc("2016-06-15 08:15")])
    out = bar_close_index(idx, "m15")
    assert list(out) == [bar_close_time(t, "m15") for t in idx]


def test_tick_size_matches_the_data():
    # Verified empirically in WP5: smallest observed increment is 0.01 USD.
    assert TICK_SIZE == 0.01


# -- the 17:00 New York trading day ----------------------------------------


def test_trading_day_rolls_at_17_new_york_summer():
    # June: New York is EDT (UTC-4), so 17:00 NY = 21:00 UTC.
    assert trading_day(utc("2016-06-15 20:59")) == date(2016, 6, 15)
    assert trading_day(utc("2016-06-15 21:00")) == date(2016, 6, 16)


def test_trading_day_rolls_at_17_new_york_winter():
    # January: New York is EST (UTC-5), so 17:00 NY = 22:00 UTC.
    assert trading_day(utc("2016-01-13 21:59")) == date(2016, 1, 13)
    assert trading_day(utc("2016-01-13 22:00")) == date(2016, 1, 14)


def test_trading_day_during_us_eu_dst_mismatch_window():
    # 2016: US switched to EDT on 03-13, the EU only on 03-27. In between, the
    # broker's own 00:00 EET day boundary sits at 18:00 NY, but ours must stay
    # pinned to 17:00 NY = 21:00 UTC.
    assert trading_day(utc("2016-03-16 20:59")) == date(2016, 3, 16)
    assert trading_day(utc("2016-03-16 21:00")) == date(2016, 3, 17)


def test_trading_day_bounds_round_trip():
    for day in (date(2016, 6, 16), date(2016, 1, 14), date(2016, 3, 17)):
        start, end = trading_day_bounds(day)
        assert end - start == pd.Timedelta(hours=24)
        assert trading_day(start) == day
        assert trading_day(end - pd.Timedelta(minutes=1)) == day
        assert trading_day(end) == day + pd.Timedelta(days=1).to_pytimedelta()


def test_trading_day_spans_23_hours_on_spring_forward():
    # US spring-forward is 2016-03-13 02:00. The trading day CONTAINING it runs
    # 17:00 NY 03-12 -> 17:00 NY 03-13, i.e. trading day 2016-03-13, and loses
    # an hour. The following day is back to a normal 24.
    start, end = trading_day_bounds(date(2016, 3, 13))
    assert end - start == pd.Timedelta(hours=23)
    start, end = trading_day_bounds(date(2016, 3, 14))
    assert end - start == pd.Timedelta(hours=24)


def test_trading_day_spans_25_hours_on_fall_back():
    # Fall-back 2016-11-06 02:00 falls inside trading day 2016-11-06.
    start, end = trading_day_bounds(date(2016, 11, 6))
    assert end - start == pd.Timedelta(hours=25)
    start, end = trading_day_bounds(date(2016, 11, 7))
    assert end - start == pd.Timedelta(hours=24)


def test_vectorised_trading_day_matches_scalar():
    idx = pd.date_range("2016-03-10", "2016-03-20", freq="37min", tz="UTC")
    vec = trading_day_index(idx)
    for ts, got in zip(idx[::17], vec[::17]):
        assert got == trading_day(ts)


# -- session windows --------------------------------------------------------


def test_london_tight_session_summer_and_winter():
    # BST (UTC+1) in June, GMT (UTC+0) in January.
    s, e = session_bounds(date(2016, 6, 15), "london_tight")
    assert (s, e) == (utc("2016-06-15 06:00"), utc("2016-06-15 09:00"))
    s, e = session_bounds(date(2016, 1, 13), "london_tight")
    assert (s, e) == (utc("2016-01-13 07:00"), utc("2016-01-13 10:00"))


def test_new_york_tight_session_summer_and_winter():
    # EDT (UTC-4) in June, EST (UTC-5) in January.
    s, e = session_bounds(date(2016, 6, 15), "ny_tight")
    assert (s, e) == (utc("2016-06-15 12:30"), utc("2016-06-15 15:00"))
    s, e = session_bounds(date(2016, 1, 13), "ny_tight")
    assert (s, e) == (utc("2016-01-13 13:30"), utc("2016-01-13 16:00"))


def test_asia_variants_differ_by_exactly_one_hour():
    a_s, a_e = session_bounds(date(2016, 6, 15), "asia_a")
    b_s, b_e = session_bounds(date(2016, 6, 15), "asia_b")
    assert a_s == b_s
    assert b_e - a_e == pd.Timedelta(hours=1)


def test_every_session_lies_inside_its_trading_day():
    # session_bounds asserts this internally; sweep a year to be sure the
    # assertion never fires, including across both DST transitions.
    for day in pd.date_range("2016-01-04", "2016-12-30", freq="D").date:
        lo, hi = trading_day_bounds(day)
        for name in ("asia_a", "asia_b", "london_tight", "london_wide", "ny_tight", "ny_wide"):
            s, e = session_bounds(day, name)
            assert lo <= s < e <= hi


def test_in_session_boundaries_are_half_open():
    assert in_session(utc("2016-06-15 06:00"), "london_tight")
    assert in_session(utc("2016-06-15 08:59"), "london_tight")
    assert not in_session(utc("2016-06-15 09:00"), "london_tight")
    assert not in_session(utc("2016-06-15 05:59"), "london_tight")


def test_unknown_session_and_timeframe_raise():
    with pytest.raises(ValueError):
        session_bounds(date(2016, 6, 15), "tokyo")
    with pytest.raises(ValueError):
        bar_close_time(utc("2016-06-15 08:00"), "m5")
