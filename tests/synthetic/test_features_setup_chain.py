"""The full setup chain on hand-built bars: sweep -> MSS -> displacement FVG.

One 12-bar London session, with every price chosen so the right answer can be
worked out on paper:

    bar  open    high    low     close   note
    0    1300    1301    1299    1300
    1    1300    1302    1299    1301
    2    1301    1310    1300    1305    swing high at 1310, confirmed at bar 4
    3    1305    1306    1300    1301
    4    1301    1302    1298    1299
    5    1299    1300    1289    1291    SWEEP of PDL 1290 (pierce + reclaim)
    6    1291    1292    1290.5  1291.5
    7    1291.5  1312    1291    1311    displacement, closes above 1310 -> MSS
    8    1311    1313    1309    1312    completes the FVG (1292 -> 1309)
    9..11 quiet

PDL = 1290.00. Reference swing = 1310.00. FVG = [1292.00, 1309.00], first touch
1309.00. A short lookback (4) is used for the displacement average so the
scenario stays readable; the baseline 20 is exercised on real data instead.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from xauusd_research.features.bias import Bias
from xauusd_research.features.fvg import build_setups, find_all_fvgs, fvg_at
from xauusd_research.features.levels import LevelBook
from xauusd_research.features.sessions import SessionMap
from xauusd_research.features.structure import (
    average_body,
    displacement_ratio,
    find_mss,
    is_displacement,
    rejection_counts,
)
from xauusd_research.features.sweeps import find_sweeps, sweeps_live_at
from xauusd_research.features.swings import find_swings

START = pd.Timestamp("2016-06-15 06:00", tz="UTC")  # 07:00 London, session open
TRADING_DAY = pd.Timestamp("2016-06-15")
PDL_PRICE = 1290.0
LOOKBACK = 4

BARS = [
    (1300.0, 1301.0, 1299.0, 1300.0),
    (1300.0, 1302.0, 1299.0, 1301.0),
    (1301.0, 1310.0, 1300.0, 1305.0),
    (1305.0, 1306.0, 1300.0, 1301.0),
    (1301.0, 1302.0, 1298.0, 1299.0),
    (1299.0, 1300.0, 1289.0, 1291.0),
    (1291.0, 1292.0, 1290.5, 1291.5),
    (1291.5, 1312.0, 1291.0, 1311.0),
    (1311.0, 1313.0, 1309.0, 1312.0),
    (1312.0, 1312.5, 1311.0, 1312.0),
    (1312.0, 1312.5, 1311.0, 1312.0),
    (1312.0, 1312.5, 1311.0, 1312.0),
]


def frame(bars=BARS):
    idx = pd.DatetimeIndex(
        [START + pd.Timedelta(minutes=15 * i) for i in range(len(bars))],
        name="timestamp_utc",
    )
    return pd.DataFrame(bars, columns=["open", "high", "low", "close"], index=idx)


def level_book(pdl=PDL_PRICE, available_from=None, **extra):
    row = {
        "pdh": np.nan, "pdl": pdl, "asia_high": np.nan, "asia_low": np.nan,
        "pdh_bars": 0, "pdl_bars": 92, "asia_high_bars": 0, "asia_low_bars": 0,
    }
    row.update(extra)
    when = available_from if available_from is not None else START
    for name in ("pdh", "pdl", "asia_high", "asia_low"):
        row.setdefault(f"{name}_from", when)
        row[f"{name}_from"] = row.get(f"{name}_from", when)
    table = pd.DataFrame([row], index=pd.DatetimeIndex([TRADING_DAY]))
    for name in ("pdh", "pdl", "asia_high", "asia_low"):
        table[f"{name}_from"] = when
    return LevelBook(table)


def session_map(n=len(BARS), session="london_tight", last=None):
    last = n - 1 if last is None else last
    return SessionMap(
        name=np.array([session] * n, dtype=object),
        last_index=np.full(n, last, dtype=int),
        trading_day=np.array([TRADING_DAY] * n),
    )


def arrays(df):
    return (
        df["open"].to_numpy(float), df["high"].to_numpy(float),
        df["low"].to_numpy(float), df["close"].to_numpy(float),
    )


# -- sweep ------------------------------------------------------------------


def test_finds_exactly_one_bullish_sweep_with_the_right_numbers():
    sweeps = find_sweeps(frame(), level_book(), session_map())
    assert len(sweeps) == 1
    s = sweeps[0]
    assert s.index == 5
    assert s.direction is Bias.BULLISH          # sell-side taken -> bullish
    assert s.level_name == "pdl"
    assert s.penetration == pytest.approx(1.0)  # 1290.00 - 1289.00
    assert s.extreme == pytest.approx(1289.0)
    assert s.expires_at_index == 11
    assert s.confirmed_at == s.index            # no future bars needed


def test_pierce_without_reclaim_is_not_a_sweep():
    bars = list(BARS)
    bars[5] = (1299.0, 1300.0, 1289.0, 1289.5)  # closes BELOW the level
    assert find_sweeps(frame(bars), level_book(), session_map()) == []


def test_reclaim_without_pierce_is_not_a_sweep():
    bars = list(BARS)
    bars[5] = (1299.0, 1300.0, 1290.5, 1291.0)  # never gets below 1290
    assert find_sweeps(frame(bars), level_book(), session_map()) == []


def test_closing_exactly_on_the_level_does_not_reclaim_it():
    bars = list(BARS)
    bars[5] = (1299.0, 1300.0, 1289.0, 1290.0)
    assert find_sweeps(frame(bars), level_book(), session_map()) == []


def test_a_sweep_outside_any_session_is_not_tracked():
    smap = SessionMap(
        name=np.array([""] * len(BARS), dtype=object),
        last_index=np.full(len(BARS), -1, dtype=int),
        trading_day=np.array([TRADING_DAY] * len(BARS)),
    )
    assert find_sweeps(frame(), level_book(), smap) == []


def test_a_level_is_ignored_until_it_becomes_available():
    # Asia-style availability: the level only opens after bar 5 has already
    # swept it, so the sweep must not be detected.
    late = START + pd.Timedelta(minutes=15 * 9)
    assert find_sweeps(frame(), level_book(available_from=late), session_map()) == []


def test_buy_side_sweep_is_bearish():
    bars = list(BARS)
    bars[5] = (1299.0, 1311.0, 1298.0, 1300.0)  # pierces a PDH at 1310, closes back under
    book = level_book(pdl=np.nan, pdh=1310.0)
    sweeps = find_sweeps(frame(bars), book, session_map())
    assert len(sweeps) == 1
    assert sweeps[0].direction is Bias.BEARISH
    assert sweeps[0].level_name == "pdh"


def test_sweeps_live_at_respects_both_ends_of_its_life():
    s = find_sweeps(frame(), level_book(), session_map())[0]
    assert sweeps_live_at([s], 5) == []      # not yet — it completes at bar 5
    assert sweeps_live_at([s], 6) == [s]
    assert sweeps_live_at([s], 11) == [s]
    assert sweeps_live_at([s], 12) == []     # session over


# -- displacement -----------------------------------------------------------


def test_average_body_excludes_the_current_candle():
    df = frame()
    o, _, _, c = arrays(df)
    avg = average_body(o, c, lookback=LOOKBACK)
    expected = np.mean([abs(c[i] - o[i]) for i in (3, 4, 5, 6)])
    assert avg[7] == pytest.approx(expected)
    assert np.isnan(avg[LOOKBACK - 1])       # not enough history yet


def test_displacement_ratio_matches_hand_arithmetic():
    df = frame()
    o, _, _, c = arrays(df)
    ratio = displacement_ratio(o, c, lookback=LOOKBACK)
    # bodies of bars 3-6: 4.0, 2.0, 8.0, 0.5 -> mean 3.625; bar 7 body 19.5
    assert ratio[7] == pytest.approx(19.5 / 3.625)
    assert is_displacement(ratio, 7, 1.5)
    assert not is_displacement(ratio, 6, 1.5)


def test_a_bar_cannot_inflate_its_own_threshold():
    # A single enormous candle must not dilute its own ratio.
    o = np.array([100.0] * 10)
    c = np.array([100.5] * 9 + [140.0])
    ratio = displacement_ratio(o, c, lookback=4)
    assert ratio[9] == pytest.approx(40.0 / 0.5)


# -- MSS --------------------------------------------------------------------


def chain(bars=BARS, lookback=LOOKBACK):
    df = frame(bars)
    o, h, l, c = arrays(df)
    sweeps = find_sweeps(df, level_book(), session_map(n=len(bars)))
    swings = find_swings(h, l, n=2)
    ratio = displacement_ratio(o, c, lookback=lookback)
    mss, rejected = find_mss(sweeps, swings, o, c, ratio)
    return df, (o, h, l, c), sweeps, swings, mss, rejected


def test_mss_breaks_the_swing_that_existed_at_the_sweep():
    _, _, _, _, mss, rejected = chain()
    assert rejected == []
    assert len(mss) == 1
    m = mss[0]
    assert m.index == 7
    assert m.direction is Bias.BULLISH
    assert m.reference_swing.index == 2
    assert m.reference_swing.price == pytest.approx(1310.0)
    assert m.break_close == pytest.approx(1311.0)
    assert m.confirmed_at == 7


def test_the_reference_swing_was_already_confirmed_at_the_sweep():
    _, _, sweeps, _, mss, _ = chain()
    assert mss[0].reference_swing.confirmed_at <= sweeps[0].index


def test_a_break_without_displacement_is_not_an_mss():
    bars = list(BARS)
    # Same close, but reached in small steps so no candle displaces.
    bars[7] = (1310.9, 1312.0, 1291.0, 1311.0)
    _, _, _, _, mss, rejected = chain(bars)
    assert mss == []
    assert rejection_counts(rejected) == {"no_mss_before_session_end": 1}


def test_displacement_that_does_not_break_structure_is_not_an_mss():
    bars = list(BARS)
    bars[7] = (1291.5, 1309.0, 1291.0, 1308.0)  # big candle, still under 1310
    _, _, _, _, mss, rejected = chain(bars)
    assert mss == []
    assert rejection_counts(rejected) == {"no_mss_before_session_end": 1}


def test_an_mss_after_the_session_ends_does_not_count():
    df = frame()
    o, h, l, c = arrays(df)
    smap = session_map(last=6)          # session ends before the bar-7 break
    sweeps = find_sweeps(df, level_book(), smap)
    swings = find_swings(h, l, n=2)
    ratio = displacement_ratio(o, c, lookback=LOOKBACK)
    mss, rejected = find_mss(sweeps, swings, o, c, ratio)
    assert mss == []
    assert rejection_counts(rejected) == {"no_mss_before_session_end": 1}


def test_setup_is_rejected_when_there_is_nothing_left_to_break():
    bars = list(BARS)
    bars[5] = (1299.0, 1300.0, 1289.0, 1311.0)  # reclaims straight past 1310
    _, _, _, _, mss, rejected = chain(bars)
    assert mss == []
    assert rejection_counts(rejected) == {"price_already_above_reference": 1}


# -- FVG and the completed setup -------------------------------------------


def test_the_displacement_candle_leaves_the_expected_gap():
    _, (o, h, l, c), _, _, _, _ = chain()
    gap = fvg_at(h, l, 7, Bias.BULLISH)
    assert gap is not None
    assert gap.bottom == pytest.approx(1292.0)   # high of bar 6
    assert gap.top == pytest.approx(1309.0)      # low of bar 8
    assert gap.size == pytest.approx(17.0)


def test_the_gap_is_not_knowable_until_its_third_candle_closes():
    _, (o, h, l, c), _, _, _, _ = chain()
    gap = fvg_at(h, l, 7, Bias.BULLISH)
    assert gap.confirmed_at == 8 == gap.index + 1


def test_first_touch_entry_is_the_near_edge_not_the_far_one():
    _, (o, h, l, c), _, _, mss, _ = chain()
    setups, no_gap = build_setups(mss, h, l)
    assert no_gap == 0 and len(setups) == 1
    s = setups[0]
    # Price is above a bullish gap, so a retracement reaches the TOP first.
    assert s.entry_price == pytest.approx(1309.0)
    assert s.fvg.midpoint == pytest.approx(1300.5)
    assert s.confirmed_at == 8


def test_setup_carries_both_stop_loss_references():
    _, (o, h, l, c), _, _, mss, _ = chain()
    setups, _ = build_setups(mss, h, l)
    s = setups[0]
    assert s.invalidation_extreme == pytest.approx(1289.0)  # SL Variant A: sweep wick
    assert s.invalidation_swing == pytest.approx(1310.0)    # SL Variant B: broken swing


def test_an_mss_with_no_gap_is_counted_not_dropped_silently():
    bars = list(BARS)
    bars[8] = (1311.0, 1313.0, 1291.5, 1312.0)  # bar 8 low overlaps bar 6 high
    _, (o, h, l, c), _, _, mss, _ = chain(bars)
    setups, no_gap = build_setups(mss, h, l)
    assert len(mss) == 1
    assert setups == [] and no_gap == 1


def test_bearish_fvg_is_the_mirror():
    high = np.array([100.0, 100.0, 95.0, 90.0, 90.0])
    low = np.array([99.0, 99.0, 90.0, 85.0, 85.0])
    gap = fvg_at(high, low, 2, Bias.BEARISH)
    assert gap.top == pytest.approx(99.0)    # low of bar 1
    assert gap.bottom == pytest.approx(90.0) # high of bar 3
    assert gap.first_touch_price == pytest.approx(90.0)


def test_zero_height_gap_is_not_a_gap():
    high = np.array([100.0, 100.0, 105.0, 100.0, 100.0])
    low = np.array([99.0, 99.0, 101.0, 100.0, 100.0])
    assert fvg_at(high, low, 2, Bias.BULLISH) is None


def test_find_all_fvgs_agrees_with_the_single_lookup():
    rng = np.random.default_rng(5)
    close = np.cumsum(rng.normal(size=500)) + 1300
    high = close + rng.uniform(0.1, 3.0, size=500)
    low = close - rng.uniform(0.1, 3.0, size=500)
    every = find_all_fvgs(high, low)
    assert every
    for gap in every[:60]:
        assert fvg_at(high, low, gap.index, gap.direction) == gap
