"""Higher-timeframe aggregation, cross-validated against the broker's own bars.

The strongest check in this file is `test_matches_native_d1_on_aligned_days`:
on every day where our 17:00-NY boundary happens to coincide with the broker's
own 00:00 EET/EEST boundary, our daily bar rebuilt from m15 must equal the
broker's independently-supplied daily bar exactly. It does — 2242 days, zero
difference on all four prices. That simultaneously validates the WP4 timezone
conversion, the price scaling, the m15 series itself, and this aggregation.
"""

from __future__ import annotations

from collections import Counter

import pandas as pd
import pytest

from xauusd_research.engine.clock import trading_day
from xauusd_research.engine.resample import (
    BarSeries,
    base_series,
    build_d1_ny,
    build_h4_ny,
    load_native_htf,
    ny_session_keys,
)


def test_bar_series_rejects_a_bar_that_closes_before_it_opens():
    idx = pd.DatetimeIndex([pd.Timestamp("2016-06-15 08:00", tz="UTC")])
    df = pd.DataFrame({"open": [1.0], "high": [1.0], "low": [1.0], "close": [1.0]}, index=idx)
    with pytest.raises(ValueError):
        BarSeries("bad", df, idx)  # close_time == open_time


def test_session_keys_offset_always_within_one_day(real_m15):
    _, offset = ny_session_keys(real_m15.index)
    assert offset.min() >= pd.Timedelta(0)
    assert offset.max() < pd.Timedelta(hours=24)


def test_d1_aggregate_equals_its_own_m15_constituents(real_m15):
    d1 = build_d1_ny(real_m15)
    day_label, _ = ny_session_keys(real_m15.index)
    groups = real_m15.groupby(day_label)

    for open_time in d1.df.index[500:520]:
        day = trading_day(open_time + pd.Timedelta(minutes=1))
        chunk = groups.get_group(pd.Timestamp(day))
        row = d1.df.loc[open_time]
        assert row["open"] == pytest.approx(chunk["open"].iloc[0])
        assert row["close"] == pytest.approx(chunk["close"].iloc[-1])
        assert row["high"] == pytest.approx(chunk["high"].max())
        assert row["low"] == pytest.approx(chunk["low"].min())


def test_matches_native_d1_on_aligned_days(real_m15, processed_dir):
    ours = build_d1_ny(real_m15)
    native = load_native_htf("d1", processed_dir)
    common = ours.df.index.intersection(native.df.index)

    assert len(common) > 2000, "expected the two day definitions to coincide most days"
    cols = ["open", "high", "low", "close"]
    diff = (ours.df.loc[common, cols] - native.df.loc[common, cols]).abs()
    assert diff.to_numpy().max() == 0.0


def test_our_d1_covers_more_history_than_the_native_series(real_m15, processed_dir):
    ours = build_d1_ny(real_m15)
    native = load_native_htf("d1", processed_dir)
    # The native daily series starts ~6 months late; that is the reason we
    # rebuild rather than use it as the baseline.
    assert ours.df.index[0] < native.df.index[0]
    assert len(ours) > len(native)


def test_day_boundaries_disagree_on_the_dst_mismatch_weeks(real_m15, processed_dir):
    ours = build_d1_ny(real_m15)
    native = load_native_htf("d1", processed_dir)
    overlap = native.df.index[0]
    ours_after = ours.df.index[ours.df.index >= overlap]
    mismatched = ours_after.difference(native.df.index)
    # ~6.6% of days, concentrated in March (US DST starts before the EU's).
    assert 100 < len(mismatched) < 250
    assert Counter(t.month for t in mismatched).most_common(1)[0][0] == 3


def test_d1_close_time_is_the_next_boundary(real_m15):
    d1 = build_d1_ny(real_m15)
    gaps = (d1.close_time - d1.df.index).unique()
    # 24h normally, 23h/25h across the two DST transitions.
    assert set(gaps) <= {pd.Timedelta(hours=h) for h in (23, 24, 25)}


def test_h4_gives_six_buckets_on_a_normal_trading_day(real_m15):
    day_label, offset = ny_session_keys(real_m15.index)
    bucket = (offset // pd.Timedelta(hours=4)).astype("int64")
    per_day = pd.DataFrame({"d": day_label, "b": bucket}).drop_duplicates().groupby("d").size()
    counts = Counter(per_day)
    assert counts[6] > 2000  # normal days
    assert max(counts) == 6  # never a seventh bucket, even on the 25-hour day


def test_h4_bars_never_straddle_a_trading_day(real_m15):
    h4 = build_h4_ny(real_m15.iloc[:20000])
    for open_time, close_time in zip(h4.df.index, h4.close_time):
        # The bar's own start and its last instant belong to the same day.
        assert trading_day(open_time) == trading_day(close_time - pd.Timedelta(minutes=1))


def test_base_series_close_times_are_open_plus_15m(real_m15):
    base = base_series(real_m15.iloc[:1000])
    assert ((base.close_time - base.df.index) == pd.Timedelta(minutes=15)).all()
