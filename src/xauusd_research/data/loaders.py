"""Raw data loaders for XAUUSD Phase 1 research.

Empirically calibrated timezone finding (2026-08-25, Work Package 4):
The `ejtraderLabs/historical-data` GitHub source's `Date` column is NOT UTC. It was
cross-correlated against user-downloaded Dukascopy data with an explicit `Etc/UTC` timestamp
(ground truth) at two different times of year:

  - January 2013 (winter): best alignment at raw_time - 2h  (corr 0.99983, MAE $0.43)
  - July 2013 (summer):    best alignment at raw_time - 3h  (corr 0.99996, MAE $0.17)

This is the classic EET/EEST broker-server-time convention (UTC+2 winter / UTC+3 summer,
switching on EU DST dates). We treat the raw `Date` column as local wall-clock time in the
IANA zone `Europe/Bucharest` (an EET/EEST zone with the standard EU DST schedule) and convert
to true UTC via zoneinfo, rather than applying a naive fixed offset. This is essential — every
downstream session/PDH-PDL/DST calculation depends on getting this right.

Price scaling: raw close/open/high/low values are the true USD price x 100 (e.g. 155408.0 means
$1554.08). Confirmed by cross-referencing known XAUUSD price levels.
"""

from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

RAW_SOURCE_TZ = ZoneInfo("Europe/Bucharest")  # EET/EEST, EU DST schedule
PRICE_SCALE = 100.0

REPO_ROOT = Path(__file__).resolve().parents[3]
RAW_DIR = REPO_ROOT / "data" / "raw" / "github_ejtrader_2012_2022"
PROCESSED_DIR = REPO_ROOT / "data" / "processed"

TIMEFRAMES = ["m15", "m30", "h1", "h4", "d1"]


def load_raw_ejtrader(timeframe: str) -> pd.DataFrame:
    """Load one raw ejtraderLabs CSV, fix price scale, convert to true UTC.

    Returns a DataFrame indexed by tz-aware UTC timestamps, columns:
    open, high, low, close, tick_volume. Rows whose local timestamp falls in a
    nonexistent DST "spring forward" gap are dropped (flagged, should be ~0 rows since the
    broker feed already has no gap-hour rows); no ambiguous "fall back" rows were found in
    raw-timestamp duplicate checks, so ambiguous='raise' would fail loudly if that assumption
    ever breaks.
    """
    if timeframe not in TIMEFRAMES:
        raise ValueError(f"unknown timeframe {timeframe!r}, expected one of {TIMEFRAMES}")

    path = RAW_DIR / f"XAUUSD_{timeframe}.csv"
    df = pd.read_csv(path)
    df["Date"] = pd.to_datetime(df["Date"])

    if df["Date"].duplicated().any():
        raise ValueError(
            f"{timeframe}: unexpected duplicate raw timestamps — DST fold assumption may be wrong"
        )
    if not df["Date"].is_monotonic_increasing:
        df = df.sort_values("Date")

    local = df["Date"].dt.tz_localize(
        RAW_SOURCE_TZ, ambiguous="raise", nonexistent="shift_forward"
    )
    df["timestamp_utc"] = local.dt.tz_convert("UTC")

    for col in ["open", "high", "low", "close"]:
        df[col] = df[col] / PRICE_SCALE

    df = df.set_index("timestamp_utc")[["open", "high", "low", "close", "tick_volume"]]
    df = df.sort_index()
    return df


def load_dukascopy_reference(csv_path: Path, side: str) -> pd.DataFrame:
    """Load a user-downloaded Dukascopy CSV (already explicit Etc/UTC), for cross-checks only."""
    df = pd.read_csv(csv_path)
    df.columns = [c.strip() for c in df.columns]
    ts_col = df.columns[0]
    df["timestamp_utc"] = pd.to_datetime(df[ts_col], utc=True)
    df = df.set_index("timestamp_utc")
    df.columns = [c.strip().lower() for c in df.columns]
    df["side"] = side
    return df.sort_index()
