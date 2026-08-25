"""Strict liquidity sweeps of PDH/PDL and Asia High/Low.

FOUNDING_BRIEF.md, "LIQUIDITY SWEEP", STRICT variant:

    price penetrates beyond relevant liquidity,
    wick/penetration occurs,
    same candle closes back inside/reclaims the level.

So a single 15m candle must both pierce the level and close back on the origin
side of it. The LOOSER variant (reclaim within the next 1-2 candles) is a
planned WP10 comparison and is not implemented here.

Penetration is any penetration — the brief sets no minimum depth, so one tick
through counts. That is the literal reading, and inventing a minimum would be
adding a parameter nobody asked for. The depth of each sweep is recorded, so if
it later turns out to matter it can be examined rather than guessed at.

Two things scope a sweep, both from the user's WP6 Q3 answer:

* it must occur inside a tracked trading session, and
* it stays live only until that session ends.

A sweep of buy-side liquidity (PDH, Asia High) is a **bearish** signal — price
reached up for stops and rejected. A sweep of sell-side liquidity (PDL, Asia
Low) is **bullish**. The four sources are kept separate throughout, per the
brief's "Do not combine them into one hidden metric".
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd

from .bias import Bias
from .levels import Level, LevelBook
from .sessions import SessionMap


@dataclass(frozen=True)
class Sweep:
    #: Bar whose close completed the sweep. Knowable at that bar's close.
    index: int
    level_name: str
    level_price: float
    direction: Bias
    #: How far beyond the level the wick reached, in price units.
    penetration: float
    #: The wick extreme — the invalidation point for the setup that follows.
    extreme: float
    session: str
    trading_day: date
    #: Last bar index at which this sweep is still live (its session's last bar).
    expires_at_index: int

    @property
    def confirmed_at(self) -> int:
        """Known at its own bar's close — a sweep needs no future bars."""
        return self.index


def find_sweeps(
    m15: pd.DataFrame,
    levels: LevelBook,
    session_map: SessionMap,
) -> list[Sweep]:
    """Detect every strict sweep, in bar order."""
    high = m15["high"].to_numpy(dtype=float)
    low = m15["low"].to_numpy(dtype=float)
    close = m15["close"].to_numpy(dtype=float)
    close_times = m15.index + pd.Timedelta(minutes=15)

    out: list[Sweep] = []
    cached_day: date | None = None
    cached_levels: list[Level] = []

    for i in range(len(m15)):
        session = session_map.name[i]
        if not session:
            continue  # outside every tracked session -> not a candidate

        day = pd.Timestamp(session_map.trading_day[i]).date()
        if day != cached_day:
            cached_day, cached_levels = day, levels.for_day(day)

        now = close_times[i]
        for lv in cached_levels:
            if lv.available_from > now:
                continue  # the window that produced this level has not closed yet
            if lv.is_buy_side:
                pierced = high[i] > lv.price
                reclaimed = close[i] < lv.price
                penetration, extreme, direction = (
                    high[i] - lv.price, high[i], Bias.BEARISH
                )
            else:
                pierced = low[i] < lv.price
                reclaimed = close[i] > lv.price
                penetration, extreme, direction = (
                    lv.price - low[i], low[i], Bias.BULLISH
                )
            if not (pierced and reclaimed):
                continue
            out.append(
                Sweep(
                    index=i,
                    level_name=lv.name,
                    level_price=lv.price,
                    direction=direction,
                    penetration=float(penetration),
                    extreme=float(extreme),
                    session=str(session),
                    trading_day=day,
                    expires_at_index=int(session_map.last_index[i]),
                )
            )
    return out


def sweeps_live_at(sweeps: list[Sweep], bar_index: int) -> list[Sweep]:
    """Sweeps already completed and not yet expired at `bar_index`."""
    return [s for s in sweeps if s.index < bar_index <= s.expires_at_index]


def summarise_sweeps(sweeps: list[Sweep]) -> dict[str, int]:
    """Counts per liquidity source and per session — never a single merged total."""
    out: dict[str, int] = {}
    for s in sweeps:
        out[f"{s.level_name}"] = out.get(f"{s.level_name}", 0) + 1
        out[f"{s.session}"] = out.get(f"{s.session}", 0) + 1
        key = f"{s.level_name}@{s.session}"
        out[key] = out.get(key, 0) + 1
    out["total"] = len(sweeps)
    return dict(sorted(out.items()))


def penetration_stats(sweeps: list[Sweep]) -> dict[str, float]:
    """Distribution of how far sweeps actually penetrated, in USD."""
    if not sweeps:
        return {}
    p = np.array([s.penetration for s in sweeps], dtype=float)
    return {
        "n": float(len(p)),
        "median": float(np.median(p)),
        "p10": float(np.percentile(p, 10)),
        "p90": float(np.percentile(p, 90)),
        "max": float(p.max()),
        "under_10_cents": float((p < 0.10).mean()),
    }
