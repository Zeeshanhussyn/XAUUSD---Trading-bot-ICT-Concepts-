"""Causality audit of the whole feature chain on real bars.

The synthetic tests prove each rule is implemented as written. These re-derive
the invariants directly from real detected objects, so a leak that only appears
on messy data — a holiday, a DST week, a session with missing bars — still gets
caught.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from xauusd_research.config import BASELINE_SWING_N
from xauusd_research.engine.clock import bar_close_index, session_bounds
from xauusd_research.features.bias import Bias
from xauusd_research.features.fvg import build_setups
from xauusd_research.features.levels import build_levels
from xauusd_research.features.sessions import build_session_map
from xauusd_research.features.structure import displacement_ratio, find_mss
from xauusd_research.features.sweeps import find_sweeps
from xauusd_research.features.swings import find_swings


@pytest.fixture(scope="module")
def chain(request):
    m15 = pd.read_parquet(
        request.config.rootpath / "data" / "processed" / "XAUUSD_m15.parquet"
    ).iloc[:60000]
    o, h, l, c = (m15[x].to_numpy(dtype=float) for x in ("open", "high", "low", "close"))
    levels = build_levels(m15)
    smap = build_session_map(m15.index)
    sweeps = find_sweeps(m15, levels, smap)
    swings = find_swings(h, l, BASELINE_SWING_N)
    ratio = displacement_ratio(o, c)
    mss, rejected = find_mss(sweeps, swings, o, c, ratio)
    setups, no_gap = build_setups(mss, h, l)
    return dict(
        m15=m15, o=o, h=h, l=l, c=c, levels=levels, smap=smap, sweeps=sweeps,
        swings=swings, ratio=ratio, mss=mss, rejected=rejected, setups=setups,
        no_gap=no_gap, close_time=bar_close_index(m15.index, "m15"),
    )


def test_the_chain_actually_produces_things(chain):
    assert len(chain["sweeps"]) > 500
    assert len(chain["mss"]) > 30
    assert len(chain["setups"]) > 10


# -- sweeps -----------------------------------------------------------------


def test_every_sweep_used_a_level_that_was_already_available(chain):
    levels, close_time = chain["levels"], chain["close_time"]
    for s in chain["sweeps"]:
        match = [lv for lv in levels.for_day(s.trading_day) if lv.name == s.level_name]
        assert match, f"level {s.level_name} missing for {s.trading_day}"
        assert match[0].available_from <= close_time[s.index]


def test_no_asia_level_is_ever_used_before_its_window_closes(chain):
    close_time = chain["close_time"]
    asia = [s for s in chain["sweeps"] if s.level_name.startswith("asia")]
    assert asia
    for s in asia:
        _, window_end = session_bounds(s.trading_day, "asia_a")
        assert close_time[s.index] >= window_end


def test_every_sweep_really_pierced_and_reclaimed(chain):
    h, l, c = chain["h"], chain["l"], chain["c"]
    for s in chain["sweeps"]:
        if s.direction is Bias.BULLISH:
            assert l[s.index] < s.level_price          # pierced below
            assert c[s.index] > s.level_price          # closed back above
            assert s.extreme == pytest.approx(l[s.index])
        else:
            assert h[s.index] > s.level_price
            assert c[s.index] < s.level_price
            assert s.extreme == pytest.approx(h[s.index])
        assert s.penetration > 0


def test_every_sweep_sits_inside_a_tracked_session(chain):
    smap = chain["smap"]
    for s in chain["sweeps"]:
        assert smap.name[s.index] == s.session
        assert s.expires_at_index == smap.last_index[s.index]
        assert s.expires_at_index >= s.index


# -- MSS --------------------------------------------------------------------


def test_reference_swings_were_confirmed_before_their_sweep(chain):
    """The core lookahead trap: a swing must not be used before it is knowable."""
    for m in chain["mss"]:
        assert m.reference_swing.confirmed_at <= m.sweep.index
        assert m.reference_swing.index < m.sweep.index


def test_every_mss_lies_after_its_sweep_and_inside_the_session(chain):
    for m in chain["mss"]:
        assert m.sweep.index < m.index <= m.sweep.expires_at_index


def test_every_mss_broke_its_reference_with_a_real_displacement(chain):
    c, ratio = chain["c"], chain["ratio"]
    for m in chain["mss"]:
        assert ratio[m.index] >= 1.5
        if m.direction is Bias.BULLISH:
            assert c[m.index] > m.reference_swing.price
            assert c[m.sweep.index] < m.reference_swing.price   # something to break
        else:
            assert c[m.index] < m.reference_swing.price
            assert c[m.sweep.index] > m.reference_swing.price


def test_reference_swing_price_matches_the_underlying_bar(chain):
    h, l = chain["h"], chain["l"]
    for m in chain["mss"]:
        ref = m.reference_swing
        actual = h[ref.index] if m.direction is Bias.BULLISH else l[ref.index]
        assert ref.price == pytest.approx(actual)


# -- FVG and setups ---------------------------------------------------------


def test_every_gap_matches_the_raw_bars_that_formed_it(chain):
    h, l = chain["h"], chain["l"]
    for s in chain["setups"]:
        g, d = s.fvg, s.fvg.index
        if s.direction is Bias.BULLISH:
            assert g.bottom == pytest.approx(h[d - 1])
            assert g.top == pytest.approx(l[d + 1])
        else:
            assert g.bottom == pytest.approx(h[d + 1])
            assert g.top == pytest.approx(l[d - 1])
        assert g.size > 0


def test_a_setup_is_never_knowable_before_its_gap_completes(chain):
    for s in chain["setups"]:
        assert s.fvg.index == s.mss.index          # displacement candle's own gap
        assert s.confirmed_at == s.mss.index + 1   # one bar of lag, always
        assert s.confirmed_at > s.mss.sweep.index


def test_entry_is_the_edge_price_reaches_first(chain):
    for s in chain["setups"]:
        if s.direction is Bias.BULLISH:
            assert s.entry_price == s.fvg.top
        else:
            assert s.entry_price == s.fvg.bottom
        assert s.fvg.bottom <= s.entry_price <= s.fvg.top


def test_stop_references_sit_on_the_losing_side_of_entry(chain):
    """Both SL variants must be able to produce a valid order."""
    for s in chain["setups"]:
        if s.direction is Bias.BULLISH:
            assert s.invalidation_extreme < s.entry_price
        else:
            assert s.invalidation_extreme > s.entry_price


def test_setups_are_in_chronological_order(chain):
    idx = [s.confirmed_at for s in chain["setups"]]
    assert idx == sorted(idx)


def test_nothing_is_lost_without_being_counted(chain):
    """Every sweep ends up either as an MSS or in the rejection tally."""
    assert len(chain["mss"]) + len(chain["rejected"]) == len(chain["sweeps"])
    assert len(chain["setups"]) + chain["no_gap"] == len(chain["mss"])


def test_detected_objects_do_not_depend_on_data_beyond_them(chain, request):
    """Truncating the series must not change anything already detected.

    If any detector peeked forward, results computed on a longer series would
    differ from the same results computed on a shorter one.
    """
    m15 = chain["m15"]
    cut = 30000
    short = m15.iloc[:cut]
    o, h, l, c = (short[x].to_numpy(dtype=float) for x in ("open", "high", "low", "close"))
    sweeps = find_sweeps(short, build_levels(short), build_session_map(short.index))
    swings = find_swings(h, l, BASELINE_SWING_N)
    mss, _ = find_mss(sweeps, swings, o, c, displacement_ratio(o, c))
    setups, _ = build_setups(mss, h, l)

    # Compare against the full run, ignoring the tail where the short series
    # simply ran out of bars.
    margin = cut - 20
    full = [s for s in chain["setups"] if s.confirmed_at < margin]
    short_setups = [s for s in setups if s.confirmed_at < margin]
    assert [(s.mss.index, s.entry_price) for s in full] == [
        (s.mss.index, s.entry_price) for s in short_setups
    ]


def test_bullish_and_bearish_setups_both_occur(chain):
    kinds = {s.direction for s in chain["setups"]}
    assert kinds == {Bias.BULLISH, Bias.BEARISH}


def test_all_four_liquidity_sources_are_exercised(chain):
    names = {s.level_name for s in chain["sweeps"]}
    assert names == {"pdh", "pdl", "asia_high", "asia_low"}
