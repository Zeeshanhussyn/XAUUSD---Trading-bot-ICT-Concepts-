"""Work Package 8 — non-blocking analysis tags.

Every detector here is fed hand-built inputs with an obvious right answer, and
every one of the tags is checked to be exactly what its docstring promises:
descriptive only, never touching entry price, stop, or which setups exist.
"""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import pytest

from xauusd_research.config import EQH_EQL_ATR_MULTIPLE
from xauusd_research.features.bias import Bias
from xauusd_research.features.fvg import FVG, Setup
from xauusd_research.features.levels import ASIA_HIGH, ASIA_LOW, PDH, PDL, LevelBook
from xauusd_research.features.structure import MSS
from xauusd_research.features.sweeps import Sweep
from xauusd_research.features.swings import Swing, SwingType
from xauusd_research.features.tags import (
    EqualLevel,
    TrendRegime,
    VolatilityRegime,
    build_week_levels,
    clusters_by_trading_day,
    evaluate_order_block,
    find_equal_levels,
    find_liquidity_clusters,
    find_order_block,
    market_regime,
    tag_premium_discount,
    tag_sequential_liquidity_events,
    tag_setup,
    trading_week_of,
)


# --------------------------------------------------------------------------
# helpers to build minimal, valid instances of upstream dataclasses
# --------------------------------------------------------------------------


def make_sweep(index=0, level_name=PDL, level_price=100.0, direction=Bias.BULLISH,
                extreme=99.5, session="london_tight", trading_day_=date(2020, 1, 8),
                expires_at_index=50) -> Sweep:
    return Sweep(
        index=index, level_name=level_name, level_price=level_price, direction=direction,
        penetration=abs(level_price - extreme), extreme=extreme, session=session,
        trading_day=trading_day_, expires_at_index=expires_at_index,
    )


def make_swing(index=0, price=99.0, kind=SwingType.LOW, confirmed_at=2) -> Swing:
    return Swing(index=index, price=price, kind=kind, confirmed_at=confirmed_at)


def make_mss(index=5, direction=Bias.BULLISH, sweep=None, reference_swing=None,
             break_close=101.0, displacement_ratio=2.0) -> MSS:
    sweep = sweep or make_sweep()
    reference_swing = reference_swing or make_swing()
    return MSS(
        index=index, direction=direction, sweep=sweep, reference_swing=reference_swing,
        break_close=break_close, displacement_ratio=displacement_ratio,
    )


# --------------------------------------------------------------------------
# Order Block
# --------------------------------------------------------------------------


def test_order_block_is_the_last_opposite_colour_candle_before_displacement():
    #        0     1     2     3     4 (down) 5 (displacement, bullish)
    open_ = [10.0, 10.0, 10.0, 10.0, 10.2, 10.0]
    close = [10.5, 10.2, 10.3, 10.4, 9.8, 12.0]  # idx4 closes below its open
    high = [11, 11, 11, 11, 11, 13]
    low = [9, 9, 9, 9, 9, 9.5]
    mss = make_mss(index=5, direction=Bias.BULLISH)
    ob = find_order_block(mss, np.array(open_), np.array(high), np.array(low), np.array(close))
    assert ob is not None
    assert ob.index == 4
    assert ob.kind is Bias.BULLISH
    assert ob.confirmed_at == mss.index == 5


def test_order_block_skips_same_colour_candles_searching_backward():
    #        0     1     2 (down)  3     4 (displacement, bullish)
    open_ = [10.0, 10.0, 10.5, 10.0, 9.5]
    close = [10.5, 10.6, 10.0, 10.3, 12.0]  # idx3 is up, idx2 is the nearest down candle
    high = [11, 11, 11, 11, 13]
    low = [9, 9, 9, 9, 9.5]
    mss = make_mss(index=4, direction=Bias.BULLISH)
    ob = find_order_block(mss, np.array(open_), np.array(high), np.array(low), np.array(close))
    assert ob is not None
    assert ob.index == 2


def test_no_order_block_when_every_candle_in_lookback_is_the_same_colour():
    open_ = [10.0] * 5
    close = [10.5] * 4 + [12.0]  # everything before displacement is also up-close
    high = [11] * 4 + [13]
    low = [9] * 5
    mss = make_mss(index=4, direction=Bias.BULLISH)
    ob = find_order_block(
        mss, np.array(open_), np.array(high), np.array(low), np.array(close), max_lookback=4
    )
    assert ob is None


# --------------------------------------------------------------------------
# Breaker / Mitigation outcomes
# --------------------------------------------------------------------------


def test_order_block_stays_fresh_until_touched():
    open_ = np.array([10.0, 9.2, 9.0, 20.0, 20.0, 20.0])
    high = np.array([10.5, 9.2, 12.2, 21.0, 21.0, 21.0])
    low = np.array([9.5, 8.8, 8.9, 19.0, 19.0, 19.0])
    close = np.array([10.3, 8.9, 12.0, 20.0, 20.0, 20.0])
    mss = make_mss(index=2, direction=Bias.BULLISH)
    ob = find_order_block(mss, open_, high, low, close)
    assert ob is not None and ob.index == 1
    outcome = evaluate_order_block(ob, high, low, close, horizon=6)
    assert outcome.status_at(4) == "fresh"


def test_order_block_becomes_mitigated_on_first_touch_without_violation():
    # OB at idx1 (low=8.8, high=9.2). Price returns and touches it at idx3
    # (low 9.0 <= 9.2) but the close (9.1) never breaks the OB's low (8.8).
    open_ = np.array([10.0, 9.2, 9.0, 9.4, 20.0])
    high = np.array([10.5, 9.2, 12.2, 9.5, 21.0])
    low = np.array([9.5, 8.8, 8.9, 9.0, 19.0])
    close = np.array([10.3, 8.9, 12.0, 9.1, 20.0])
    mss = make_mss(index=2, direction=Bias.BULLISH)
    ob = find_order_block(mss, open_, high, low, close)
    assert ob is not None and ob.index == 1
    outcome = evaluate_order_block(ob, high, low, close, horizon=5)
    assert outcome.first_touch_index == 3
    assert outcome.violated_index is None
    assert outcome.status_at(3) == "mitigated"
    # Causal: status before the touch bar closed must still read "fresh".
    assert outcome.status_at(2) == "fresh"


def test_order_block_becomes_breaker_when_body_closes_through_it():
    # OB at idx1 (bullish, low=8.8). idx3 closes at 8.5, below the OB low ->
    # violated -> flips to a breaker (now resistance).
    open_ = np.array([10.0, 9.2, 9.5, 8.9, 8.6])
    high = np.array([10.5, 9.2, 12.0, 8.9, 8.6])
    low = np.array([9.5, 8.8, 9.4, 8.3, 8.0])
    close = np.array([10.3, 8.9, 12.0, 8.5, 8.2])
    mss = make_mss(index=2, direction=Bias.BULLISH)
    ob = find_order_block(mss, open_, high, low, close)
    assert ob is not None and ob.index == 1
    outcome = evaluate_order_block(ob, high, low, close, horizon=5)
    assert outcome.violated_index == 3
    assert outcome.status_at(3) == "breaker"
    assert outcome.status_at(2) == "fresh"


def test_evaluate_order_block_never_looks_past_its_horizon():
    # A violation exists at idx4, but horizon=4 must not see it.
    open_ = np.array([10.0, 9.2, 9.5, 12.0, 12.0])
    high = np.array([10.5, 9.2, 12.2, 12.0, 12.0])
    low = np.array([9.5, 8.8, 9.4, 9.4, 8.0])
    close = np.array([10.3, 8.9, 12.0, 12.0, 8.0])
    mss = make_mss(index=2, direction=Bias.BULLISH)
    ob = find_order_block(mss, open_, high, low, close)
    assert ob is not None and ob.index == 1
    outcome = evaluate_order_block(ob, high, low, close, horizon=4)
    assert outcome.violated_index is None
    assert outcome.status_at(4) == "fresh"


# --------------------------------------------------------------------------
# Equal Highs / Lows
# --------------------------------------------------------------------------


def test_finds_equal_highs_within_tolerance():
    a = make_swing(index=0, price=100.00, kind=SwingType.HIGH, confirmed_at=2)
    b = make_swing(index=10, price=100.05, kind=SwingType.HIGH, confirmed_at=12)
    swings = _fake_swing_series([a, b])
    atr_values = np.full(20, 1.0)  # tolerance = 0.10 x 1.0 = 0.10, |diff| = 0.05
    out = find_equal_levels(swings, atr_values)
    assert len(out) == 1
    assert out[0].kind is SwingType.HIGH
    assert out[0].confirmed_at == b.confirmed_at


def test_rejects_highs_outside_tolerance():
    a = make_swing(index=0, price=100.00, kind=SwingType.HIGH, confirmed_at=2)
    b = make_swing(index=10, price=101.00, kind=SwingType.HIGH, confirmed_at=12)
    swings = _fake_swing_series([a, b])
    atr_values = np.full(20, 1.0)  # tolerance 0.10, |diff| = 1.00 -> not equal
    assert find_equal_levels(swings, atr_values) == []


def _fake_swing_series(swings):
    class _Fake:
        def __init__(self, all_):
            self.all = all_
    return _Fake(swings)


# --------------------------------------------------------------------------
# Previous Week High / Low
# --------------------------------------------------------------------------


def test_previous_week_levels_use_the_full_prior_week():
    # Two trading weeks of daily bars, Mon-Fri, 17:00-NY roll. Week 1 high=110,
    # low=90; week 2 should see PWH=110, PWL=90 from its first trading day.
    idx = []
    rows = []
    # Week 1: Mon 2024-01-01 .. Fri 2024-01-05, one bar per day at 18:00 UTC
    # (safely inside the trading day that starts 17:00 NY the day before).
    week1_days = pd.date_range("2024-01-01", "2024-01-05", freq="D")
    week1_highs = [100, 105, 110, 102, 101]
    week1_lows = [95, 96, 97, 90, 94]
    for d, h, low_ in zip(week1_days, week1_highs, week1_lows):
        idx.append(pd.Timestamp(d.date()) + pd.Timedelta(hours=18))
        rows.append((h - 2, h, low_, (h + low_) / 2))
    week2_days = pd.date_range("2024-01-08", "2024-01-09", freq="D")
    for d in week2_days:
        idx.append(pd.Timestamp(d.date()) + pd.Timedelta(hours=18))
        rows.append((100, 103, 99, 101))

    m15 = pd.DataFrame(rows, columns=["open", "high", "low", "close"],
                        index=pd.DatetimeIndex(idx, tz="UTC"))
    book = build_week_levels(m15)

    week2 = trading_week_of(date(2024, 1, 8))
    lvl = book.for_week(week2)
    assert lvl is not None
    assert lvl.pwh == 110
    assert lvl.pwl == 90

    week1 = trading_week_of(date(2024, 1, 2))
    assert book.for_week(week1) is None  # no prior week in this tiny fixture


def test_previous_week_level_not_available_before_the_new_week_opens():
    week1_days = pd.date_range("2024-01-01", "2024-01-05", freq="D")
    idx = [pd.Timestamp(d.date()) + pd.Timedelta(hours=18) for d in week1_days]
    idx += [pd.Timestamp("2024-01-08") + pd.Timedelta(hours=18)]
    rows = [(100, 105, 95, 101)] * 5 + [(100, 103, 99, 101)]
    m15 = pd.DataFrame(rows, columns=["open", "high", "low", "close"],
                        index=pd.DatetimeIndex(idx, tz="UTC"))
    book = build_week_levels(m15)
    week2 = trading_week_of(date(2024, 1, 8))
    lvl = book.for_week(week2)
    assert lvl is not None
    too_early = lvl.available_from - pd.Timedelta(minutes=1)
    assert book.available_at(too_early, week2) is None
    assert book.available_at(lvl.available_from, week2) is not None


# --------------------------------------------------------------------------
# Premium / Discount
# --------------------------------------------------------------------------


def test_bullish_setup_entering_below_midpoint_is_favourable_discount():
    sweep = make_sweep(level_price=100.0, direction=Bias.BULLISH)
    ref_swing = make_swing(price=110.0, kind=SwingType.HIGH)
    mss = make_mss(direction=Bias.BULLISH, sweep=sweep, reference_swing=ref_swing)
    fvg = FVG(index=mss.index, direction=Bias.BULLISH, bottom=102.0, top=103.0)
    setup = Setup(mss=mss, fvg=fvg)
    tag = tag_premium_discount(setup)
    assert tag.range_low == 100.0 and tag.range_high == 110.0
    assert tag.midpoint == 105.0
    assert tag.entry_price == fvg.first_touch_price == 103.0
    assert tag.zone == "discount"
    assert tag.favorable is True


def test_bearish_setup_entering_above_midpoint_is_favourable_premium():
    sweep = make_sweep(level_price=110.0, direction=Bias.BEARISH)
    ref_swing = make_swing(price=100.0, kind=SwingType.LOW)
    mss = make_mss(direction=Bias.BEARISH, sweep=sweep, reference_swing=ref_swing)
    fvg = FVG(index=mss.index, direction=Bias.BEARISH, bottom=107.0, top=108.0)
    setup = Setup(mss=mss, fvg=fvg)
    tag = tag_premium_discount(setup)
    assert tag.zone == "premium"
    assert tag.favorable is True


def test_bullish_setup_entering_above_midpoint_is_unfavourable_premium():
    sweep = make_sweep(level_price=100.0, direction=Bias.BULLISH)
    ref_swing = make_swing(price=110.0, kind=SwingType.HIGH)
    mss = make_mss(direction=Bias.BULLISH, sweep=sweep, reference_swing=ref_swing)
    fvg = FVG(index=mss.index, direction=Bias.BULLISH, bottom=106.0, top=107.0)
    setup = Setup(mss=mss, fvg=fvg)
    tag = tag_premium_discount(setup)
    assert tag.zone == "premium"
    assert tag.favorable is False


# --------------------------------------------------------------------------
# Market Regime
# --------------------------------------------------------------------------


def test_regime_needs_a_full_window_before_producing_a_label():
    close = np.linspace(100, 200, 50)
    atr_values = np.full(50, 1.0)
    regime = market_regime(atr_values, close, percentile_window=10, trend_window=10)

    # Volatility: a rolling rank over `percentile_window` observations is
    # first valid once that many bars have closed (index 9 = the 10th bar).
    for i in range(9):
        vol, _ = regime.at(i)
        assert vol is None, f"volatility leaked at bar {i}"
    vol, _ = regime.at(9)
    assert vol is not None

    # Trend is a rolling percentile of the efficiency ratio, and the ratio
    # itself needs a full trend_window before its first value exists -- so
    # the percentile-of-ratio needs TWO trend_window's worth of bars before
    # anything is valid: 2*10 - 1 = 19, not 9.
    for i in range(19):
        _, trend = regime.at(i)
        assert trend is None, f"trend leaked at bar {i}"
    _, trend = regime.at(19)
    assert trend is not None


def test_a_clean_break_out_of_chop_is_tagged_trending():
    # Trend reads as a PERCENTILE of the efficiency ratio against its own
    # trailing history (see config.REGIME_TREND_PERCENTILE) -- a fixed
    # absolute cutoff was tried first and measured to never fire once on
    # 5.8 years of real gold data (see PREREGISTRATION.md / CHANGELOG.md,
    # WP8). So the synthetic case that should read "trending" is a clean
    # directional break relative to noisy recent history, not a bare
    # monotonic line in isolation.
    rng = np.random.default_rng(1)
    choppy = 100 + np.cumsum(rng.choice([-1.0, 1.0], size=60))
    ramp = choppy[-1] + np.arange(1, 21) * 3.0
    close = np.concatenate([choppy, ramp])
    atr_values = np.full(len(close), 1.0)
    regime = market_regime(atr_values, close, percentile_window=10, trend_window=10)
    _, trend = regime.at(65)  # well inside the break, still close to the choppy contrast
    assert trend is TrendRegime.TRENDING


def test_choppy_series_is_mostly_tagged_ranging():
    # A single bar's percentile is noisy over a short window (a pure random
    # walk still throws occasional short bursts that outrank their own
    # recent history) -- the reliable claim is that RANGING dominates over a
    # longer stretch, matching the ~75th-percentile cutoff by construction.
    rng = np.random.default_rng(0)
    close = 100 + np.cumsum(rng.choice([-1.0, 1.0], size=200))  # no net drift bias
    atr_values = np.full(len(close), 1.0)
    regime = market_regime(atr_values, close, percentile_window=10, trend_window=10)
    labels = [regime.at(i)[1] for i in range(len(close))]
    labels = [t for t in labels if t is not None]
    ranging_share = sum(1 for t in labels if t is TrendRegime.RANGING) / len(labels)
    assert ranging_share > 0.6


def test_high_volatility_percentile_when_current_atr_is_the_local_maximum():
    # Strictly increasing ATR -> the current bar is always the max of its own
    # trailing window -> top percentile every time a window completes.
    atr_values = np.linspace(1, 10, 60)
    close = np.arange(60, dtype=float)
    regime = market_regime(atr_values, close, percentile_window=20, trend_window=5)
    vol, _ = regime.at(59)
    assert vol is VolatilityRegime.HIGH


def test_low_volatility_percentile_when_current_atr_is_the_local_minimum():
    # Strictly decreasing ATR -> the current bar is always the min of its own
    # trailing window -> bottom percentile every time a window completes.
    atr_values = np.linspace(10, 1, 60)
    close = np.arange(60, dtype=float)
    regime = market_regime(atr_values, close, percentile_window=20, trend_window=5)
    vol, _ = regime.at(59)
    assert vol is VolatilityRegime.LOW


# --------------------------------------------------------------------------
# Liquidity Cluster
# --------------------------------------------------------------------------


def _level_book_for_one_day(day, pdh, pdl, asia_high, asia_low):
    idx = pd.DatetimeIndex([pd.Timestamp(day)])
    table = pd.DataFrame(index=idx)
    table[PDH] = [pdh]
    table[PDL] = [pdl]
    table[ASIA_HIGH] = [asia_high]
    table[ASIA_LOW] = [asia_low]
    for name in (PDH, PDL, ASIA_HIGH, ASIA_LOW):
        table[f"{name}_from"] = idx
        table[f"{name}_bars"] = [96]
    return LevelBook(table)


def test_liquidity_cluster_flags_close_levels_but_not_far_ones():
    day = pd.Timestamp("2024-01-08")
    levels = _level_book_for_one_day(day, pdh=110.05, pdl=90.0, asia_high=110.00, asia_low=80.0)
    m15_index = pd.date_range(day - pd.Timedelta(days=1, hours=6), periods=200, freq="15min", tz="UTC")
    atr_values = np.full(len(m15_index), 1.0)  # tight=0.10, wide=0.20
    clusters = find_liquidity_clusters(levels, m15_index, atr_values)
    by_pair = {(c.level_a, c.level_b): c for c in clusters}
    close_pair = by_pair[(PDH, ASIA_HIGH)]
    assert close_pair.distance == pytest.approx(0.05)
    assert close_pair.within_tight and close_pair.within_wide

    far_pair = by_pair[(PDL, ASIA_LOW)]
    assert far_pair.distance == 10.0
    assert not far_pair.within_tight and not far_pair.within_wide


def test_clusters_by_trading_day_groups_correctly():
    day = date(2024, 1, 8)
    from xauusd_research.features.tags import LiquidityCluster
    a = LiquidityCluster(day, PDH, ASIA_HIGH, 110.0, 110.0, 0.0, True, True, 1.0)
    b = LiquidityCluster(date(2024, 1, 9), PDL, ASIA_LOW, 90.0, 90.0, 0.0, True, True, 1.0)
    grouped = clusters_by_trading_day([a, b])
    assert grouped[day] == [a]
    assert grouped[date(2024, 1, 9)] == [b]


# --------------------------------------------------------------------------
# Sequential Liquidity Events
# --------------------------------------------------------------------------


def test_second_sweep_of_the_day_is_tagged_secondary():
    day = date(2024, 1, 8)
    first = make_sweep(index=5, level_name=ASIA_LOW, trading_day_=day)
    second = make_sweep(index=20, level_name=PDH, trading_day_=day)
    tags = tag_sequential_liquidity_events([second, first])  # deliberately out of order
    assert tags[(first.index, first.level_name)].is_secondary is False
    tag2 = tags[(second.index, second.level_name)]
    assert tag2.is_secondary is True
    assert tag2.first_sweep_of_day is first


def test_sweeps_on_different_days_are_each_first():
    first = make_sweep(index=5, level_name=PDL, trading_day_=date(2024, 1, 8))
    other_day = make_sweep(index=3, level_name=PDL, trading_day_=date(2024, 1, 9))
    tags = tag_sequential_liquidity_events([first, other_day])
    assert tags[(first.index, first.level_name)].is_secondary is False
    assert tags[(other_day.index, other_day.level_name)].is_secondary is False


# --------------------------------------------------------------------------
# tag_setup: everything together, and the non-interference guarantee
# --------------------------------------------------------------------------


def test_tag_setup_does_not_alter_the_setup_it_tags():
    sweep = make_sweep(level_price=100.0, direction=Bias.BULLISH, trading_day_=date(2024, 1, 8))
    ref_swing = make_swing(price=110.0, kind=SwingType.HIGH)
    mss = make_mss(index=5, direction=Bias.BULLISH, sweep=sweep, reference_swing=ref_swing)
    fvg = FVG(index=mss.index, direction=Bias.BULLISH, bottom=102.0, top=103.0)
    setup = Setup(mss=mss, fvg=fvg)

    open_ = np.array([10.0] * 4 + [9.5, 12.0, 12.0])
    close = np.array([10.5, 10.2, 9.8, 9.6, 10.5, 12.5, 12.5])
    high = np.array([11, 11, 11, 11, 11, 13, 13])
    low = np.array([9, 9, 9, 9, 9, 9.5, 9.5])
    atr_values = np.full(7, 1.0)
    regime = market_regime(atr_values, close, percentile_window=5, trend_window=5)

    before = (setup.entry_price, setup.invalidation_extreme, setup.invalidation_swing, setup.direction)
    tagged = tag_setup(setup, open_, high, low, close, regime, sequential={}, clusters_by_day={})
    after = (setup.entry_price, setup.invalidation_extreme, setup.invalidation_swing, setup.direction)

    assert before == after  # tagging never mutates or re-derives the setup's own trade fields
    assert tagged.setup is setup
    assert tagged.premium_discount.setup is setup
