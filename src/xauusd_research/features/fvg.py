"""Fair Value Gaps — standard three-candle definition.

A bullish FVG centred on candle `d` exists when candle `d-1`'s high is below
candle `d+1`'s low: the middle candle moved far enough that the two neighbours
never traded through the same prices. The gap runs from `high[d-1]` up to
`low[d+1]`. Bearish mirrors it.

Two things about timing, both of which are lookahead traps:

* An FVG centred on `d` requires candle `d+1`, so it is **not knowable until
  `d+1` closes** — never at `d`, where it is drawn on a chart.
* Price sits above a bullish gap once it forms, so a retracement reaches the
  gap's **upper** edge first. First-touch entry is therefore at `low[d+1]` for
  a bullish gap and `high[d+1]` for a bearish one, not at the far edge.

Which FVG is eligible was left open by FOUNDING_BRIEF.md — it defines the shape,
the size filters, the freshness rules and the entry style, but never where the
gap must have formed. Resolved with the user on 2026-08-25 (WP6 Q4) and recorded
as a preregistration amendment: **only the gap centred on the displacement
candle that confirmed the MSS**. Any-FVG-after-MSS and any-unmitigated-FVG stay
as WP10 comparisons.

Size filters (>= 0.25 ATR, >= 0.50 ATR) and the alternative freshness rules are
also WP10 comparisons; the baseline takes any non-zero gap and treats it as
valid until first touch.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .bias import Bias
from .structure import MSS


@dataclass(frozen=True)
class FVG:
    """A three-candle gap. `index` is the middle (displacement) candle."""

    index: int
    direction: Bias
    bottom: float
    top: float

    def __post_init__(self) -> None:
        if self.top <= self.bottom:
            raise ValueError("an FVG must have a positive height")

    @property
    def confirmed_at(self) -> int:
        """The gap needs its third candle, so it is knowable one bar later."""
        return self.index + 1

    @property
    def size(self) -> float:
        return self.top - self.bottom

    @property
    def first_touch_price(self) -> float:
        """The edge a retracement reaches first — the baseline entry level."""
        return self.top if self.direction is Bias.BULLISH else self.bottom

    @property
    def midpoint(self) -> float:
        """WP10 comparison entry style."""
        return (self.top + self.bottom) / 2.0


def fvg_at(
    high: np.ndarray, low: np.ndarray, index: int, direction: Bias
) -> FVG | None:
    """The gap centred on `index`, if one exists in `direction`."""
    if index < 1 or index + 1 >= len(high):
        return None
    if direction is Bias.BULLISH:
        bottom, top = float(high[index - 1]), float(low[index + 1])
    elif direction is Bias.BEARISH:
        bottom, top = float(high[index + 1]), float(low[index - 1])
    else:
        return None
    if top <= bottom:
        return None
    return FVG(index=index, direction=direction, bottom=bottom, top=top)


def find_all_fvgs(high: np.ndarray, low: np.ndarray) -> list[FVG]:
    """Every three-candle gap in the series — for WP8 tagging and WP10 variants.

    Not used by the baseline, which only ever looks at the displacement candle's
    own gap. Vectorised because it runs over the whole series.
    """
    high = np.asarray(high, dtype=float)
    low = np.asarray(low, dtype=float)
    out: list[FVG] = []
    bull = np.flatnonzero(high[:-2] < low[2:]) + 1
    bear = np.flatnonzero(low[:-2] > high[2:]) + 1
    for i in bull:
        out.append(FVG(int(i), Bias.BULLISH, float(high[i - 1]), float(low[i + 1])))
    for i in bear:
        out.append(FVG(int(i), Bias.BEARISH, float(high[i + 1]), float(low[i - 1])))
    out.sort(key=lambda f: (f.index, f.direction.value))
    return out


@dataclass(frozen=True)
class Setup:
    """A complete baseline setup: sweep -> MSS -> displacement FVG."""

    mss: MSS
    fvg: FVG

    @property
    def direction(self) -> Bias:
        return self.mss.direction

    @property
    def confirmed_at(self) -> int:
        """Knowable only once the FVG's third candle has closed."""
        return self.fvg.confirmed_at

    @property
    def entry_price(self) -> float:
        return self.fvg.first_touch_price

    @property
    def invalidation_extreme(self) -> float:
        """The sweep wick — SL Variant A's reference."""
        return self.mss.sweep.extreme

    @property
    def invalidation_swing(self) -> float:
        """The broken reference swing — SL Variant B's reference (baseline)."""
        return self.mss.reference_swing.price


def build_setups(
    mss_list: list[MSS], high: np.ndarray, low: np.ndarray
) -> tuple[list[Setup], int]:
    """Attach each MSS to its displacement candle's own FVG.

    Returns the completed setups and the number of MSS events that produced no
    gap at all — a real outcome worth counting, not an error.
    """
    setups: list[Setup] = []
    no_gap = 0
    for mss in mss_list:
        gap = fvg_at(high, low, mss.index, mss.direction)
        if gap is None:
            no_gap += 1
            continue
        setups.append(Setup(mss=mss, fvg=gap))
    return setups, no_gap
