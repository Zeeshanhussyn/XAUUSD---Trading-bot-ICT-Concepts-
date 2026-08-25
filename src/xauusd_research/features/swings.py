"""Fractal swing highs and lows, with explicit confirmation lag.

This is the highest lookahead risk in the whole project, because a fractal is
defined using bars that come *after* it. A swing high at bar `i` with N=2 needs
bars `i+1` and `i+2` to have closed before anyone can know it is a swing — yet
it is drawn on a chart at bar `i`, which is exactly how backtests silently cheat.

Every `Swing` therefore carries two indices:

    index          where the swing high/low actually sits (its price bar)
    confirmed_at   the bar whose close first makes it knowable  (= index + n)

Nothing in this project may use a swing before `confirmed_at`. `SwingSeries`
enforces that: its only lookup method takes the current bar index and refuses to
return anything confirmed later.

Definition (FOUNDING_BRIEF.md, "SWING DEFINITIONS"): fractal N=2 baseline, N=3
as a planned WP10 comparison.

Ties are not swings. A bar whose high merely *equals* a neighbour's high is not
a fractal high — strict inequality is required on both sides. Equal highs are a
real ICT concept but the brief classes them as an analysis tag (WP8), not as
structure, so they are deliberately not folded in here.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import numpy as np


class SwingType(Enum):
    HIGH = "high"
    LOW = "low"


@dataclass(frozen=True)
class Swing:
    index: int
    price: float
    kind: SwingType
    confirmed_at: int

    def __post_init__(self) -> None:
        if self.confirmed_at <= self.index:
            raise ValueError("a fractal swing cannot be confirmed at or before its own bar")


class SwingSeries:
    """All swings in a series, queryable only in a strictly causal way."""

    def __init__(self, swings: list[Swing], n: int):
        self.n = n
        self.all = sorted(swings, key=lambda s: (s.confirmed_at, s.index))
        self._confirmed_at = np.array([s.confirmed_at for s in self.all], dtype=int)

    def __len__(self) -> int:
        return len(self.all)

    def available_at(self, bar_index: int) -> list[Swing]:
        """Every swing knowable once bar `bar_index` has closed."""
        cut = int(np.searchsorted(self._confirmed_at, bar_index, side="right"))
        return self.all[:cut]

    def last(self, bar_index: int, kind: SwingType) -> Swing | None:
        """Most recent confirmed swing of `kind` — by its own bar, not its confirmation.

        Ordering matters: among swings already confirmed, the "most recent" one
        is the one sitting furthest right on the chart, which is not always the
        one confirmed last.
        """
        candidates = [s for s in self.available_at(bar_index) if s.kind is kind]
        return max(candidates, key=lambda s: s.index) if candidates else None

    def last_n(self, bar_index: int, kind: SwingType, count: int) -> list[Swing]:
        """The `count` most recent confirmed swings of `kind`, oldest → newest."""
        candidates = [s for s in self.available_at(bar_index) if s.kind is kind]
        candidates.sort(key=lambda s: s.index)
        return candidates[-count:]


def find_swings(high: np.ndarray, low: np.ndarray, n: int = 2) -> SwingSeries:
    """Detect fractal swing highs and lows with `n` bars either side.

    A bar is a swing high if its high is strictly greater than the highs of the
    `n` bars before it and the `n` bars after it. Swing lows mirror this.

    The first and last `n` bars can never be swings — there is not enough room
    around them — and are skipped rather than treated as a special case.
    """
    if n < 1:
        raise ValueError("n must be >= 1")
    high = np.asarray(high, dtype=float)
    low = np.asarray(low, dtype=float)
    if high.shape != low.shape:
        raise ValueError("high and low must be the same length")

    swings: list[Swing] = []
    for i in range(n, len(high) - n):
        left, right = slice(i - n, i), slice(i + 1, i + 1 + n)
        if high[i] > high[left].max() and high[i] > high[right].max():
            swings.append(Swing(i, float(high[i]), SwingType.HIGH, i + n))
        if low[i] < low[left].min() and low[i] < low[right].min():
            swings.append(Swing(i, float(low[i]), SwingType.LOW, i + n))
    return SwingSeries(swings, n)
