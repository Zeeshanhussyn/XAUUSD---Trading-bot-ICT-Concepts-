"""Time primitives: bar close times, the 17:00-New-York trading day, session windows.

Everything here is pure calendar/timezone logic — no prices, no strategy.

Two facts established empirically in WP5 and relied on throughout:

1. Bar timestamps in this data source are **open times**. A bar labelled T with
   duration D covers [T, T+D) and is only knowable at T+D. `bar_close_time()`
   is the single place that conversion happens.

2. The broker's own daily bars roll at 00:00 EET/EEST, which coincides with
   17:00 New York for 93.4% of days but lands on 18:00 New York for 158 of 2400
   days (6.6%) — the weeks where US and EU daylight-saving switch dates differ.
   Because PREREGISTRATION.md §2 defines the PDH/PDL trading day as 17:00 NY →
   17:00 NY, this module defines the trading day from `America/New_York`
   directly and never from the broker's bar labels.

All public functions take and return timezone-aware UTC pandas Timestamps
unless stated otherwise.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd

UTC = ZoneInfo("UTC")
NY = ZoneInfo("America/New_York")
LONDON = ZoneInfo("Europe/London")

# Duration of one bar, by timeframe key.
TIMEFRAME_DURATION = {
    "m15": timedelta(minutes=15),
    "m30": timedelta(minutes=30),
    "h1": timedelta(hours=1),
    "h4": timedelta(hours=4),
    "d1": timedelta(days=1),
}

# Smallest price increment observed in the data (verified in WP5: 0.01 USD).
TICK_SIZE = 0.01

# Hour (New York local) at which one trading day ends and the next begins.
TRADING_DAY_ROLL_HOUR_NY = 17


def bar_close_time(open_time: pd.Timestamp, timeframe: str) -> pd.Timestamp:
    """Return the instant a bar becomes knowable.

    A bar labelled `open_time` covers [open_time, open_time + duration); the
    engine may not use its OHLC before the returned instant.
    """
    if timeframe not in TIMEFRAME_DURATION:
        raise ValueError(f"unknown timeframe {timeframe!r}")
    return open_time + TIMEFRAME_DURATION[timeframe]


def bar_close_index(open_times: pd.DatetimeIndex, timeframe: str) -> pd.DatetimeIndex:
    """Vectorised `bar_close_time` for a whole index."""
    if timeframe not in TIMEFRAME_DURATION:
        raise ValueError(f"unknown timeframe {timeframe!r}")
    return open_times + pd.Timedelta(TIMEFRAME_DURATION[timeframe])


# --------------------------------------------------------------------------
# Trading day (17:00 New York → 17:00 New York, DST-aware)
# --------------------------------------------------------------------------


def trading_day(ts_utc: pd.Timestamp) -> date:
    """Return the trading day an instant belongs to.

    A trading day labelled D runs from 17:00 NY on D-1 (inclusive) to 17:00 NY
    on D (exclusive) — i.e. the day is named after the calendar date it ENDS on,
    the standard FX/CME convention (the session opening 17:00 NY Sunday is
    Monday's trading day).
    """
    _require_utc(ts_utc)
    local = ts_utc.tz_convert(NY)
    if local.hour >= TRADING_DAY_ROLL_HOUR_NY:
        return (local + pd.Timedelta(days=1)).date()
    return local.date()


def trading_day_bounds(day: date) -> tuple[pd.Timestamp, pd.Timestamp]:
    """Return [start, end) of trading day `day` as UTC timestamps."""
    start = _ny_wall(day - timedelta(days=1), TRADING_DAY_ROLL_HOUR_NY, 0)
    end = _ny_wall(day, TRADING_DAY_ROLL_HOUR_NY, 0)
    return start, end


def trading_day_index(open_times: pd.DatetimeIndex) -> pd.Index:
    """Vectorised `trading_day` for a whole index (returns numpy dates)."""
    local_naive = open_times.tz_convert(NY).tz_localize(None)
    shifted = local_naive - pd.Timedelta(hours=TRADING_DAY_ROLL_HOUR_NY)
    # `shifted` puts 17:00 NY at midnight, so the calendar date of `shifted`
    # is the day the session STARTED on; the trading day is that date + 1.
    return (shifted.normalize() + pd.Timedelta(days=1)).date


# --------------------------------------------------------------------------
# Session windows (PREREGISTRATION.md §2)
# --------------------------------------------------------------------------

# name -> (tz, start_hh, start_mm, end_hh, end_mm)
SESSION_WINDOWS: dict[str, tuple[ZoneInfo, int, int, int, int]] = {
    # Asia range used to build the Asia High/Low liquidity level.
    "asia_a": (LONDON, 0, 0, 5, 0),  # baseline (Variant A)
    "asia_b": (LONDON, 0, 0, 6, 0),  # WP10 ablation (Variant B)
    # Trade-execution windows.
    "london_tight": (LONDON, 7, 0, 10, 0),  # baseline
    "london_wide": (LONDON, 7, 0, 16, 0),  # WP10 ablation
    "ny_tight": (NY, 8, 30, 11, 0),  # baseline
    "ny_wide": (NY, 8, 0, 17, 0),  # WP10 ablation
}

BASELINE_TRADING_SESSIONS = ("london_tight", "ny_tight")
BASELINE_ASIA_WINDOW = "asia_a"


def session_bounds(day: date, session: str) -> tuple[pd.Timestamp, pd.Timestamp]:
    """Return [start, end) of a named session on trading day `day`, in UTC.

    The session's local calendar date equals the trading-day label: for trading
    day D (17:00 NY on D-1 → 17:00 NY on D), the Asia, London and New York
    windows all fall on local calendar date D.
    """
    if session not in SESSION_WINDOWS:
        raise ValueError(f"unknown session {session!r}")
    tz, sh, sm, eh, em = SESSION_WINDOWS[session]
    start = _wall(day, sh, sm, tz)
    end = _wall(day, eh, em, tz)
    day_start, day_end = trading_day_bounds(day)
    if not (day_start <= start < end <= day_end):
        raise AssertionError(
            f"session {session} on {day} resolved to [{start}, {end}) which is "
            f"outside its trading day [{day_start}, {day_end}) — timezone bug"
        )
    return start, end


def in_session(ts_utc: pd.Timestamp, session: str) -> bool:
    """True if `ts_utc` falls inside the named session of its own trading day."""
    start, end = session_bounds(trading_day(ts_utc), session)
    return start <= ts_utc < end


# --------------------------------------------------------------------------
# internals
# --------------------------------------------------------------------------


def _require_utc(ts: pd.Timestamp) -> None:
    if ts.tzinfo is None:
        raise ValueError("timestamp must be timezone-aware (UTC)")


def _wall(day: date, hour: int, minute: int, tz: ZoneInfo) -> pd.Timestamp:
    """Build a UTC timestamp from a local wall-clock time on a calendar date.

    All wall-clock times used by this project (00:00, 05:00, 06:00, 07:00,
    08:00, 08:30, 10:00, 11:00, 16:00, 17:00) exist unambiguously in both
    `Europe/London` and `America/New_York` on every date — daylight-saving
    transitions in those zones happen at 01:00 and 02:00 local respectively.
    This function asserts that rather than assuming it.
    """
    naive = datetime(day.year, day.month, day.day, hour, minute)
    local = naive.replace(tzinfo=tz)
    # Round-trip through UTC: for a nonexistent or ambiguous wall time this
    # does not return the original wall clock.
    round_tripped = local.astimezone(UTC).astimezone(tz).replace(tzinfo=None)
    if round_tripped != naive:
        raise AssertionError(
            f"{naive} is not a valid unambiguous wall-clock time in {tz} "
            f"(round-tripped to {round_tripped})"
        )
    return pd.Timestamp(local).tz_convert("UTC")


def _ny_wall(day: date, hour: int, minute: int) -> pd.Timestamp:
    return _wall(day, hour, minute, NY)
