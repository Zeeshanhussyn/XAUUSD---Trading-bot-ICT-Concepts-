"""Higher-timeframe bar construction from the 15-minute base series.

Per the user's WP5 decision (2026-08-25, Q1 = "build both, compare in ablation"):

- **Baseline**: D1 and H4 are aggregated from the m15 series with the daily
  boundary anchored at **17:00 New York** (DST-aware), exactly matching the
  PDH/PDL trading-day definition in PREREGISTRATION.md §2.
- **WP10 ablation**: the broker's own native D1/H4 bars (00:00 EET/EEST
  boundary) are loadable via `load_native_htf()` so the difference can be
  measured rather than assumed.

Why the baseline is not the broker's own bars:

- The broker's day boundary lands on 18:00 NY instead of 17:00 NY on 158 of
  2400 days (6.6%) — the weeks where US and EU DST switch dates differ.
- The broker's native D1 starts 2012-11-13 and H4 starts 2012-10-26, whereas
  m15 starts 2012-05-15; using native bars would silently discard ~6 months
  of the development period.

Bucketing is done on the **New York wall clock**, not on absolute elapsed time.
Consequently the 4H bucket spanning 01:00-05:00 NY contains 3 real hours on the
spring-forward date and 5 real hours on the fall-back date. That is the correct
behaviour for a session-anchored aggregation and is asserted in the tests.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .clock import NY, TRADING_DAY_ROLL_HOUR_NY, bar_close_index

OHLC_AGG = {
    "open": "first",
    "high": "max",
    "low": "min",
    "close": "last",
    "tick_volume": "sum",
}

# Wall-clock start of each 4H bucket, as hours offset from 17:00 NY.
H4_BUCKET_HOURS = (0, 4, 8, 12, 16, 20)


@dataclass(frozen=True)
class BarSeries:
    """An OHLC series plus the instant each bar becomes knowable.

    `df` is indexed by bar OPEN time (UTC). `close_time[i]` is the instant
    `df.iloc[i]` may first be used — never before. Nothing in the engine reads
    `df` without consulting `close_time`.
    """

    name: str
    df: pd.DataFrame
    close_time: pd.DatetimeIndex

    def __post_init__(self) -> None:
        if len(self.df) != len(self.close_time):
            raise ValueError("df and close_time length mismatch")
        if not self.df.index.is_monotonic_increasing:
            raise ValueError(f"{self.name}: open times are not sorted")
        if not pd.Index(self.close_time).is_monotonic_increasing:
            raise ValueError(f"{self.name}: close times are not sorted")
        if (self.close_time <= self.df.index).any():
            raise ValueError(f"{self.name}: a bar closes at or before it opens")

    def __len__(self) -> int:
        return len(self.df)


def ny_session_keys(index: pd.DatetimeIndex) -> tuple[pd.DatetimeIndex, pd.TimedeltaIndex]:
    """Map UTC timestamps to (trading-day label, wall-clock offset into that day).

    The offset is measured on the New York wall clock from 17:00, so it always
    lies in [0h, 24h) even on daylight-saving transition dates.
    """
    local_naive = index.tz_convert(NY).tz_localize(None)
    shifted = local_naive - pd.Timedelta(hours=TRADING_DAY_ROLL_HOUR_NY)
    session_start = shifted.normalize()
    trading_day_label = session_start + pd.Timedelta(days=1)
    offset = shifted - session_start
    return trading_day_label, offset


def _to_utc(day_label: pd.Timestamp, hours_from_roll: int) -> pd.Timestamp:
    """Nominal UTC instant of `17:00 NY on (day_label - 1) + hours_from_roll`."""
    wall = (
        day_label
        - pd.Timedelta(days=1)
        + pd.Timedelta(hours=TRADING_DAY_ROLL_HOUR_NY + hours_from_roll)
    )
    return pd.Timestamp(wall.to_pydatetime().replace(tzinfo=NY)).tz_convert("UTC")


def build_d1_ny(m15: pd.DataFrame) -> BarSeries:
    """Aggregate m15 bars into daily bars on the 17:00-NY trading day."""
    day_label, _ = ny_session_keys(m15.index)
    grouped = m15.groupby(day_label, sort=True).agg(OHLC_AGG)
    labels = pd.DatetimeIndex(grouped.index)

    open_time = pd.DatetimeIndex([_to_utc(d, 0) for d in labels])
    close_time = pd.DatetimeIndex([_to_utc(d, 24) for d in labels])
    grouped.index = open_time
    grouped.index.name = "timestamp_utc"
    return BarSeries("d1_ny", grouped, close_time)


def build_h4_ny(m15: pd.DataFrame) -> BarSeries:
    """Aggregate m15 bars into 4H bars anchored to the 17:00-NY trading day."""
    day_label, offset = ny_session_keys(m15.index)
    bucket = (offset // pd.Timedelta(hours=4)).astype("int64")

    grouped = m15.groupby([day_label, bucket], sort=True).agg(OHLC_AGG)
    days = pd.DatetimeIndex([k[0] for k in grouped.index])
    buckets = np.array([k[1] for k in grouped.index], dtype=int)

    open_time = pd.DatetimeIndex([_to_utc(d, int(b) * 4) for d, b in zip(days, buckets)])
    close_time = pd.DatetimeIndex(
        [_to_utc(d, (int(b) + 1) * 4) for d, b in zip(days, buckets)]
    )
    grouped.index = open_time
    grouped.index.name = "timestamp_utc"
    return BarSeries("h4_ny", grouped, close_time)


def base_series(m15: pd.DataFrame) -> BarSeries:
    """Wrap the raw m15 frame as a `BarSeries` with correct close times."""
    return BarSeries("m15", m15, bar_close_index(m15.index, "m15"))


def load_native_htf(timeframe: str, processed_dir) -> BarSeries:
    """Load the broker's own D1/H4 bars — for the WP10 ablation only.

    These use the broker's 00:00 EET/EEST day boundary, which differs from the
    preregistered 17:00-NY boundary on 6.6% of days. Never the baseline.
    """
    from pathlib import Path

    path = Path(processed_dir) / f"XAUUSD_{timeframe}.parquet"
    df = pd.read_parquet(path)
    return BarSeries(f"{timeframe}_native", df, bar_close_index(df.index, timeframe))
