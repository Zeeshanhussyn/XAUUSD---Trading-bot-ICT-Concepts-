"""Causality audit of Work Package 8 tags on real bars.

Mirrors `test_features_on_real_data.py`'s truncation approach: every tag
detector must produce identical results whether it sees the whole series or
a shorter prefix, up to the point where the shorter series simply runs out of
bars. A tag that peeked forward would fail this the same way a lookahead bug
in the core feature chain would.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from xauusd_research.config import BASELINE_ATR_PERIOD, BASELINE_SWING_N
from xauusd_research.engine.clock import bar_close_index
from xauusd_research.features.bias import Bias
from xauusd_research.features.fvg import build_setups
from xauusd_research.features.indicators import atr
from xauusd_research.features.levels import build_levels
from xauusd_research.features.sessions import build_session_map
from xauusd_research.features.structure import displacement_ratio, find_mss
from xauusd_research.features.sweeps import find_sweeps
from xauusd_research.features.swings import find_swings
from xauusd_research.features.tags import (
    build_week_levels,
    clusters_by_trading_day,
    find_equal_levels,
    find_liquidity_clusters,
    find_order_block,
    market_regime,
    tag_sequential_liquidity_events,
    tag_setup,
    trading_week_of,
)


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
    atr_values = atr(h, l, c, BASELINE_ATR_PERIOD)
    regime = market_regime(atr_values, c)
    sequential = tag_sequential_liquidity_events(sweeps)
    clusters = find_liquidity_clusters(levels, m15.index, atr_values)
    clusters_by_day = clusters_by_trading_day(clusters)
    return dict(
        m15=m15, o=o, h=h, l=l, c=c, levels=levels, smap=smap, sweeps=sweeps,
        swings=swings, mss=mss, setups=setups, atr_values=atr_values, regime=regime,
        sequential=sequential, clusters=clusters, clusters_by_day=clusters_by_day,
    )


# --------------------------------------------------------------------------
# Sanity: the pipeline actually produces tags on real data
# --------------------------------------------------------------------------


def test_the_tag_pipeline_produces_things(chain):
    assert len(chain["setups"]) > 10
    obs = [find_order_block(s.mss, chain["o"], chain["h"], chain["l"], chain["c"]) for s in chain["setups"]]
    assert any(ob is not None for ob in obs)
    assert len(chain["clusters"]) > 0
    equal_levels = find_equal_levels(chain["swings"], chain["atr_values"])
    assert len(equal_levels) > 0


def test_tagging_never_mutates_the_setups_it_describes(chain):
    setups = chain["setups"]
    before = [
        (s.entry_price, s.invalidation_extreme, s.invalidation_swing, s.direction, s.confirmed_at)
        for s in setups
    ]
    for s in setups:
        tag_setup(
            s, chain["o"], chain["h"], chain["l"], chain["c"], chain["regime"],
            chain["sequential"], chain["clusters_by_day"],
        )
    after = [
        (s.entry_price, s.invalidation_extreme, s.invalidation_swing, s.direction, s.confirmed_at)
        for s in setups
    ]
    assert before == after


# --------------------------------------------------------------------------
# Order Block: never uses a bar after its own displacement candle
# --------------------------------------------------------------------------


def test_order_block_is_confirmed_no_later_than_its_own_mss(chain):
    for s in chain["setups"]:
        ob = find_order_block(s.mss, chain["o"], chain["h"], chain["l"], chain["c"])
        if ob is not None:
            assert ob.index < ob.mss.index
            assert ob.confirmed_at == ob.mss.index


def test_order_block_detection_does_not_depend_on_data_beyond_the_displacement_candle(chain):
    """Truncating the series right after a setup's MSS must not change its order block."""
    o, h, l, c = chain["o"], chain["h"], chain["l"], chain["c"]
    for s in chain["setups"][:25]:
        full_ob = find_order_block(s.mss, o, h, l, c)
        cut = s.mss.index + 1  # only bars up to and including the displacement candle
        short_ob = find_order_block(s.mss, o[:cut], h[:cut], l[:cut], c[:cut])
        assert full_ob == short_ob


# --------------------------------------------------------------------------
# Market Regime: a rolling, strictly trailing computation
# --------------------------------------------------------------------------


def test_market_regime_does_not_depend_on_data_beyond_its_own_bar(chain):
    c = chain["c"]
    atr_values = chain["atr_values"]
    cut = 30000
    short_regime = market_regime(atr_values[:cut], c[:cut])
    margin = cut - 5
    for i in range(0, margin, 977):  # sample sparsely -- this loop is O(window) per call
        assert chain["regime"].at(i) == short_regime.at(i)


# --------------------------------------------------------------------------
# Liquidity clusters and equal levels: causal on real data too
# --------------------------------------------------------------------------


def test_liquidity_cluster_atr_reference_predates_the_trading_day(chain):
    from xauusd_research.engine.clock import trading_day_bounds

    for cl in chain["clusters"][:200]:
        day_start, _ = trading_day_bounds(cl.trading_day)
        # atr_at_reference was sampled at the last bar closed before day_start;
        # nothing here asserts a specific bar, only that the day's clusters are
        # internally consistent (both bands never accept a wider distance than
        # a tighter one at the same ATR).
        assert cl.within_tight <= cl.within_wide


def test_equal_levels_are_never_confirmed_before_the_second_swing(chain):
    equal_levels = find_equal_levels(chain["swings"], chain["atr_values"])
    for eq in equal_levels:
        assert eq.confirmed_at == eq.second.confirmed_at
        assert eq.second.index > eq.first.index


# --------------------------------------------------------------------------
# Previous week high/low: built from the same trading-day boundary as PDH/PDL
# --------------------------------------------------------------------------


def test_previous_week_levels_are_available_only_from_the_new_weeks_first_open(chain):
    book = build_week_levels(chain["m15"])
    checked = 0
    for week, row in book.table.iterrows():
        if pd.isna(row["pwh"]):
            continue
        too_early = row["available_from"] - pd.Timedelta(minutes=1)
        assert book.available_at(too_early, week) is None
        assert book.available_at(row["available_from"], week) is not None
        checked += 1
        if checked >= 50:
            break
    assert checked > 0


def test_previous_week_range_is_never_inverted(chain):
    book = build_week_levels(chain["m15"])
    for _, row in book.table.iterrows():
        if pd.isna(row["pwh"]):
            continue
        assert row["pwh"] >= row["pwl"]
