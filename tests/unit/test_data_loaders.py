"""Work Package 4 unit tests: timezone calibration and price-scale correctness.

These encode the empirical finding from 2026-08-25 so a future change to loaders.py can't
silently break the timezone conversion without a test failing.
"""

import sys
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from xauusd_research.data.loaders import RAW_SOURCE_TZ, load_raw_ejtrader  # noqa: E402


def test_raw_source_tz_is_eet_eest():
    assert RAW_SOURCE_TZ == ZoneInfo("Europe/Bucharest")


def test_winter_offset_is_utc_plus_2():
    # A known winter local timestamp: 2013-01-02 00:00 local (EET, UTC+2) -> 2013-01-01 22:00 UTC
    local = pd.Timestamp("2013-01-02 00:00:00").tz_localize(RAW_SOURCE_TZ)
    utc = local.tz_convert("UTC")
    assert utc == pd.Timestamp("2013-01-01 22:00:00", tz="UTC")


def test_summer_offset_is_utc_plus_3():
    # A known summer local timestamp: 2013-07-01 03:00 local (EEST, UTC+3) -> 2013-07-01 00:00 UTC
    local = pd.Timestamp("2013-07-01 03:00:00").tz_localize(RAW_SOURCE_TZ)
    utc = local.tz_convert("UTC")
    assert utc == pd.Timestamp("2013-07-01 00:00:00", tz="UTC")


def test_h1_loads_and_is_utc_indexed():
    df = load_raw_ejtrader("h1")
    assert df.index.tz is not None
    assert str(df.index.tz) == "UTC"
    assert df.index.is_monotonic_increasing
    assert not df.index.duplicated().any()


def test_price_scale_is_plausible_after_correction():
    df = load_raw_ejtrader("d1")
    # XAUUSD 2012-2022 genuinely traded between ~$1045 and ~$2075
    assert df["close"].min() > 900
    assert df["close"].max() < 2200


def test_no_dst_nonexistent_or_ambiguous_rows_in_raw_data():
    # Verified 2026-08-25: zero raw rows fall in a nonexistent (spring-forward) or ambiguous
    # (fall-back) local time, so the loader's ambiguous='raise' never actually fires and
    # nonexistent='shift_forward' never actually silently shifts anything. This test pins that
    # fact so a future data refresh that breaks it is caught immediately.
    raw = pd.read_csv(Path(__file__).resolve().parents[2] / "data" / "raw" /
                       "github_ejtrader_2012_2022" / "XAUUSD_m15.csv")
    raw["Date"] = pd.to_datetime(raw["Date"])
    bad = 0
    for ts in raw["Date"]:
        try:
            ts.tz_localize(RAW_SOURCE_TZ, ambiguous="raise", nonexistent="raise")
        except Exception:
            bad += 1
    assert bad == 0


def test_no_lookahead_in_loader_output_columns():
    # Loader must never produce a column that isn't derivable from bars up to and including
    # that bar's own close — this is a structural guard, not a full causality proof.
    df = load_raw_ejtrader("m15")
    assert set(df.columns) == {"open", "high", "low", "close", "tick_volume"}
