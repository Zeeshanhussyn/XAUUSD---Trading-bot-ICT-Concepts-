"""Lookahead traps for the market view.

These tests exist to fail loudly if the causal cursor is ever broken. A backtest
that leaks future data does not crash and does not look wrong — it just prints a
better number. These are the only things standing between us and that.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from conftest import flat, make_m15

from xauusd_research.engine.clock import bar_close_index
from xauusd_research.engine.marketview import LookaheadError, MarketView
from xauusd_research.engine.resample import BarSeries


def build(n: int = 20) -> BarSeries:
    return make_m15([(100 + i, 101 + i, 99 + i, 100.5 + i) for i in range(n)])


def test_view_raises_before_it_is_advanced():
    mv = MarketView(build())
    with pytest.raises(LookaheadError):
        mv.now
    with pytest.raises(LookaheadError):
        mv.bars("m15", 3)


def test_window_always_ends_at_now():
    base = build()
    mv = MarketView(base)
    for i in range(len(base)):
        mv._advance_to(i)
        w = mv.bars("m15", 5)
        assert w.close_time[-1] == mv.now
        assert w.open_time[-1] == base.df.index[i]


def test_window_never_contains_a_future_bar():
    base = build()
    mv = MarketView(base)
    for i in range(len(base)):
        mv._advance_to(i)
        w = mv.bars("m15", 50)
        assert (w.close_time <= mv.now).all()
        # And the newest close it can see is exactly bar i's close — never i+1.
        assert w.close_time[-1] == base.close_time[i]


def test_window_is_short_near_the_start_rather_than_padded():
    base = build()
    mv = MarketView(base)
    mv._advance_to(2)
    w = mv.bars("m15", 10)
    assert len(w) == 3  # bars 0,1,2 — not 10, and nothing borrowed from ahead


def test_returned_arrays_are_read_only():
    base = build()
    mv = MarketView(base)
    mv._advance_to(5)
    w = mv.bars("m15", 3)
    with pytest.raises(ValueError):
        w.close[0] = 12345.0


def test_higher_timeframe_bar_is_invisible_until_it_closes():
    base = make_m15([flat(100 + i) for i in range(8)])  # 08:00 .. 09:45
    # One "h1" bar spanning 08:00-09:00: knowable only from 09:00 onwards,
    # which is the CLOSE of the m15 bar opening at 08:45 (index 3).
    htf_df = pd.DataFrame(
        {"open": [100.0], "high": [110.0], "low": [90.0], "close": [105.0]},
        index=pd.DatetimeIndex([base.df.index[0]], name="timestamp_utc"),
    )
    htf = BarSeries("h1", htf_df, bar_close_index(htf_df.index, "h1"))
    mv = MarketView(base, {"h1": htf})

    for i in range(3):  # m15 bars closing 08:15, 08:30, 08:45
        mv._advance_to(i)
        assert mv.bars("h1", 1).empty, f"h1 leaked at i={i}"

    mv._advance_to(3)  # closes exactly 09:00 — the h1 bar completes now
    w = mv.bars("h1", 1)
    assert len(w) == 1
    assert w.close[-1] == 105.0
    assert w.close_time[-1] == mv.now


def test_unknown_timeframe_and_bad_n_raise():
    mv = MarketView(build())
    mv._advance_to(3)
    with pytest.raises(ValueError):
        mv.bars("h4", 2)
    with pytest.raises(ValueError):
        mv.bars("m15", 0)


def test_causality_holds_on_real_data(real_m15):
    """Sweep real bars with real HTF series and assert nothing ever leaks."""
    from xauusd_research.engine.resample import base_series, build_d1_ny, build_h4_ny

    m15 = real_m15.iloc[:6000]
    base = base_series(m15)
    mv = MarketView(base, {"d1": build_d1_ny(m15), "h4": build_h4_ny(m15)})

    for i in range(0, len(base), 7):
        mv._advance_to(i)
        now = mv.now
        for tf in ("m15", "d1", "h4"):
            w = mv.bars(tf, 30)
            if len(w):
                assert w.close_time[-1] <= now
                assert np.all(np.diff(w.close_time.values.astype("int64")) > 0)
