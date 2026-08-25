"""Shared test helpers: build tiny synthetic bar series with exact, known prices."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from xauusd_research.engine.clock import bar_close_index  # noqa: E402
from xauusd_research.engine.resample import BarSeries  # noqa: E402

# A Wednesday, mid-London-session, well away from any DST transition.
DEFAULT_START = pd.Timestamp("2016-06-15 08:00:00", tz="UTC")


def make_m15(rows: list[tuple[float, float, float, float]], start=DEFAULT_START) -> BarSeries:
    """Build an m15 `BarSeries` from a list of (open, high, low, close) tuples."""
    idx = pd.DatetimeIndex(
        [start + pd.Timedelta(minutes=15 * i) for i in range(len(rows))],
        name="timestamp_utc",
    )
    df = pd.DataFrame(rows, columns=["open", "high", "low", "close"], index=idx)
    df["tick_volume"] = 100
    return BarSeries("m15", df, bar_close_index(idx, "m15"))


def flat(price: float) -> tuple[float, float, float, float]:
    """A do-nothing bar that cannot trigger anything."""
    return (price, price, price, price)


@pytest.fixture(scope="session")
def processed_dir() -> Path:
    return REPO_ROOT / "data" / "processed"


@pytest.fixture(scope="session")
def real_m15(processed_dir) -> pd.DataFrame:
    path = processed_dir / "XAUUSD_m15.parquet"
    if not path.exists():
        pytest.skip("processed m15 parquet not built (run scripts/run_data_integrity.py)")
    return pd.read_parquet(path)
