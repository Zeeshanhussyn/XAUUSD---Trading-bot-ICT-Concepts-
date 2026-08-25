"""Displacement and market-structure shift (MSS/CHOCH).

Displacement — FOUNDING_BRIEF.md Variant A (baseline):

    candle body >= 1.5 x recent average candle body

with a 20-bar lookback that **excludes the current candle**. Including it would
let a large candle inflate the very average it is being measured against,
shrinking its own ratio — a subtle self-reference that also leaks the current
bar into its own threshold. Variant B (range vs ATR) is a planned WP10
comparison.

MSS/CHOCH — the brief's Variant B, which it names as the core logic: a body
close through a "meaningful swing", with displacement required on the same
candle. The brief never says which swing is meaningful; resolved with the user
on 2026-08-25 (WP6 Q2) and recorded as a preregistration amendment:

    the most recent CONFIRMED opposite-side swing that already existed
    when the sweep candle closed — fixed at that moment, not updated later.

Fixing it at the sweep keeps the sweep and the structure break part of one
event, and gives SL Variant B a stable invalidation level.

One condition follows from the word "break" rather than from a choice: at the
sweep, price must still be on the unbroken side of the reference swing. If the
last confirmed swing high already sits below price, there is nothing there to
break, and treating the next displacement candle as a structure shift would be
meaningless. Those setups are discarded and counted.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..config import (
    BASELINE_DISPLACEMENT_BODY_MULTIPLE,
    BASELINE_DISPLACEMENT_LOOKBACK,
)
from .bias import Bias
from .sweeps import Sweep
from .swings import Swing, SwingSeries, SwingType


def average_body(
    open_: np.ndarray, close: np.ndarray, lookback: int = BASELINE_DISPLACEMENT_LOOKBACK
) -> np.ndarray:
    """Mean absolute candle body over the `lookback` bars BEFORE each bar.

    `result[i]` uses bars `[i-lookback, i)` and is NaN until there are enough.
    The current bar is excluded so a candle never contributes to the threshold
    it is judged against.
    """
    body = np.abs(np.asarray(close, dtype=float) - np.asarray(open_, dtype=float))
    out = np.full(len(body), np.nan)
    if len(body) <= lookback:
        return out
    csum = np.concatenate([[0.0], np.cumsum(body)])
    for i in range(lookback, len(body)):
        out[i] = (csum[i] - csum[i - lookback]) / lookback
    return out


def displacement_ratio(
    open_: np.ndarray, close: np.ndarray, lookback: int = BASELINE_DISPLACEMENT_LOOKBACK
) -> np.ndarray:
    """Each candle's body as a multiple of the preceding average body."""
    body = np.abs(np.asarray(close, dtype=float) - np.asarray(open_, dtype=float))
    avg = average_body(open_, close, lookback)
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(avg > 0, body / avg, np.nan)


def is_displacement(
    ratio: np.ndarray, i: int, multiple: float = BASELINE_DISPLACEMENT_BODY_MULTIPLE
) -> bool:
    r = ratio[i]
    return bool(np.isfinite(r) and r >= multiple)


@dataclass(frozen=True)
class MSS:
    """A confirmed market-structure shift following a sweep."""

    #: Bar whose close broke the reference swing WITH displacement.
    index: int
    direction: Bias
    sweep: Sweep
    reference_swing: Swing
    break_close: float
    displacement_ratio: float

    @property
    def confirmed_at(self) -> int:
        """Known at its own close — the breaking candle needs no future bars."""
        return self.index


@dataclass(frozen=True)
class RejectedSetup:
    """A sweep that never produced an MSS, and why. Counted, not discarded."""

    sweep: Sweep
    reason: str


def reference_swing_for(
    sweep: Sweep, swings: SwingSeries, close: np.ndarray
) -> tuple[Swing | None, str | None]:
    """The swing an MSS must break for this sweep, or a rejection reason."""
    kind = SwingType.HIGH if sweep.direction is Bias.BULLISH else SwingType.LOW
    ref = swings.last(sweep.index, kind)
    if ref is None:
        return None, "no_confirmed_reference_swing"
    if sweep.direction is Bias.BULLISH and close[sweep.index] >= ref.price:
        return None, "price_already_above_reference"
    if sweep.direction is Bias.BEARISH and close[sweep.index] <= ref.price:
        return None, "price_already_below_reference"
    return ref, None


def find_mss(
    sweeps: list[Sweep],
    swings: SwingSeries,
    open_: np.ndarray,
    close: np.ndarray,
    ratio: np.ndarray,
    multiple: float = BASELINE_DISPLACEMENT_BODY_MULTIPLE,
) -> tuple[list[MSS], list[RejectedSetup]]:
    """For each sweep, find the first displacement candle that breaks structure.

    Searched from the bar after the sweep up to and including the sweep's
    expiry bar — the end of the session it happened in.
    """
    found: list[MSS] = []
    rejected: list[RejectedSetup] = []

    for sweep in sweeps:
        ref, reason = reference_swing_for(sweep, swings, close)
        if ref is None:
            rejected.append(RejectedSetup(sweep, reason or "no_reference"))
            continue

        hit = None
        for j in range(sweep.index + 1, sweep.expires_at_index + 1):
            if not is_displacement(ratio, j, multiple):
                continue
            broke = (
                close[j] > ref.price
                if sweep.direction is Bias.BULLISH
                else close[j] < ref.price
            )
            if broke:
                hit = j
                break

        if hit is None:
            rejected.append(RejectedSetup(sweep, "no_mss_before_session_end"))
            continue

        found.append(
            MSS(
                index=hit,
                direction=sweep.direction,
                sweep=sweep,
                reference_swing=ref,
                break_close=float(close[hit]),
                displacement_ratio=float(ratio[hit]),
            )
        )

    # Sweeps are processed in sweep order, but several can be live at once — two
    # levels swept a few bars apart in the same session — and the later sweep can
    # resolve into an MSS first. Sort by the MSS bar so downstream work sees a
    # genuine time order; the sweep bar breaks ties deterministically.
    found.sort(key=lambda m: (m.index, m.sweep.index, m.sweep.level_name))
    return found, rejected


def rejection_counts(rejected: list[RejectedSetup]) -> dict[str, int]:
    out: dict[str, int] = {}
    for r in rejected:
        out[r.reason] = out.get(r.reason, 0) + 1
    return dict(sorted(out.items()))
