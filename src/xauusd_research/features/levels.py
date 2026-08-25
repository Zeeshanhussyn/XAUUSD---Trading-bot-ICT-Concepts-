"""The two executable liquidity levels: PDH/PDL and Asia High/Low.

FOUNDING_BRIEF.md, "LIQUIDITY SOURCES": these two are the only executable
sources. They are tracked separately and never merged into one metric.

Availability is the whole point of this module. A level is not usable the
moment it exists on a chart — it is usable once the window that produced it has
finished:

* **PDH/PDL** — the high and low of the *previous* trading day (17:00 NY →
  17:00 NY). Known the instant the new trading day begins, since the day that
  produced it has closed. The brief is explicit: "Do NOT use broker-server
  midnight as PDH/PDL definition."
* **Asia High/Low** — the high and low of 00:00–05:00 London (Variant A
  baseline; 00:00–06:00 is the Variant B comparison). Not usable until the Asia
  window has *ended*, i.e. from 05:00 London onward. Using it earlier would be a
  five-hour lookahead on every single trading day.

"Previous trading day" means the previous day that actually has bars, so
weekends and holidays are skipped rather than producing an empty level. The
number of bars behind each level is carried along, because a half-day holiday
produces a genuinely narrow range and that should be visible as a tag (WP8)
rather than silently treated as a normal day.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import pandas as pd

from ..engine.clock import LONDON, SESSION_WINDOWS, session_bounds, trading_day_bounds
from ..engine.resample import ny_session_keys

PDH = "pdh"
PDL = "pdl"
ASIA_HIGH = "asia_high"
ASIA_LOW = "asia_low"

#: Levels above price are buy-side liquidity; sweeping them is a bearish signal.
BUY_SIDE_LEVELS = (PDH, ASIA_HIGH)
#: Levels below price are sell-side liquidity; sweeping them is a bullish signal.
SELL_SIDE_LEVELS = (PDL, ASIA_LOW)


@dataclass(frozen=True)
class Level:
    name: str
    price: float
    trading_day: date
    available_from: pd.Timestamp
    source_bars: int

    @property
    def is_buy_side(self) -> bool:
        return self.name in BUY_SIDE_LEVELS


class LevelBook:
    """Per-trading-day liquidity levels, with the instant each becomes usable."""

    def __init__(self, table: pd.DataFrame):
        self.table = table

    def __len__(self) -> int:
        return len(self.table)

    def for_day(self, day: date) -> list[Level]:
        key = pd.Timestamp(day)
        if key not in self.table.index:
            return []
        row = self.table.loc[key]
        out: list[Level] = []
        for name in (PDH, PDL, ASIA_HIGH, ASIA_LOW):
            price = row[name]
            if pd.isna(price):
                continue
            out.append(
                Level(
                    name=name,
                    price=float(price),
                    trading_day=day,
                    available_from=row[f"{name}_from"],
                    source_bars=int(row[f"{name}_bars"]),
                )
            )
        return out

    def available_at(self, ts: pd.Timestamp, day: date) -> list[Level]:
        """Levels of trading day `day` that are usable at instant `ts`."""
        return [lv for lv in self.for_day(day) if lv.available_from <= ts]


def build_levels(m15: pd.DataFrame, asia_window: str = "asia_a") -> LevelBook:
    """Compute PDH/PDL and Asia High/Low for every trading day in `m15`."""
    if asia_window not in SESSION_WINDOWS:
        raise ValueError(f"unknown asia window {asia_window!r}")
    _, _, _, asia_end_hour, _ = SESSION_WINDOWS[asia_window]

    day_label, _ = ny_session_keys(m15.index)
    per_day = m15.groupby(day_label).agg(
        day_high=("high", "max"), day_low=("low", "min"), bars=("high", "size")
    )
    per_day = per_day.sort_index()

    # --- PDH / PDL: previous trading day that actually has bars ---
    prev_high = per_day["day_high"].shift(1)
    prev_low = per_day["day_low"].shift(1)
    prev_bars = per_day["bars"].shift(1)

    # --- Asia range: 00:00 -> asia_end on the London calendar date ---
    london = m15.index.tz_convert(LONDON)
    in_asia = london.hour < asia_end_hour
    asia_bars = m15[in_asia]
    asia_dates = pd.DatetimeIndex(london[in_asia].normalize().tz_localize(None))
    asia = asia_bars.groupby(asia_dates).agg(
        asia_high=("high", "max"), asia_low=("low", "min"), bars=("high", "size")
    )
    # The Asia window of London date D belongs to trading day D.
    asia = asia.reindex(per_day.index)

    table = pd.DataFrame(index=per_day.index)
    table[PDH] = prev_high
    table[PDL] = prev_low
    table[f"{PDH}_bars"] = prev_bars.fillna(0).astype(int)
    table[f"{PDL}_bars"] = prev_bars.fillna(0).astype(int)
    table[ASIA_HIGH] = asia["asia_high"]
    table[ASIA_LOW] = asia["asia_low"]
    table[f"{ASIA_HIGH}_bars"] = asia["bars"].fillna(0).astype(int)
    table[f"{ASIA_LOW}_bars"] = asia["bars"].fillna(0).astype(int)

    day_starts, asia_ends = [], []
    for ts in table.index:
        d = ts.date()
        day_starts.append(trading_day_bounds(d)[0])
        asia_ends.append(session_bounds(d, asia_window)[1])
    # PDH/PDL are known the instant the new trading day opens; the Asia levels
    # only once the Asia window has closed.
    table[f"{PDH}_from"] = day_starts
    table[f"{PDL}_from"] = day_starts
    table[f"{ASIA_HIGH}_from"] = asia_ends
    table[f"{ASIA_LOW}_from"] = asia_ends

    return LevelBook(table)
