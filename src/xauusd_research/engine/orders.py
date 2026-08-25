"""Order/position model and the conservative fill simulator.

Every rule below is either fixed by PREREGISTRATION.md §2 or was confirmed by
the user on 2026-08-25 (WP5 question Q2 = "conservative / pessimistic"). None of
it is a guess, and none of it may be quietly relaxed later to improve a result.

FILL RULES
----------
Entry (limit order):
  * Fills only if price trades at least **one tick THROUGH** the level
    (PREREGISTRATION.md §2, "Entry fill realism" — a hard rule from the brief).
    Touching the level exactly is not a fill.
  * If the bar OPENS through the level, the fill is still booked at the limit
    price — the gap improvement is not credited to us.

Stop loss (stop order):
  * Triggers on **touch** — no tick-through required. The pessimistic choice.
  * If the bar OPENS at or beyond the stop, the fill is booked at the **bar
    open**, i.e. the full gap loss is taken.

Take profit (limit order):
  * Requires one tick through, same as any limit.
  * If the bar OPENS beyond the target, the fill is still booked at the target
    price — again no gap bonus.

AMBIGUITY WITHIN A BAR
----------------------
A 15-minute bar tells us its high and its low but not the order they occurred
in, and there is no finer data available. Resolution:

  1. **Gap phase.** Evaluate levels against the bar's OPEN first. A level the
     bar opened beyond was reached before any intrabar movement, so it is
     unambiguous and resolves immediately. Stop and target sit on opposite
     sides of entry, so at most one can gap.
  2. **Intrabar phase.** If neither gapped, and both stop and target lie inside
     [low, high], the **stop is taken** (PREREGISTRATION.md §2: "Ambiguous
     SL/TP order -> stop-first").

Running the gap phase first matters. Without it, a bar that opened straight
through the target and only later traded down to the stop would be booked as a
loss — that is not conservative, it is simply wrong.

A position opened *during* the current bar gets no gap phase for its own exits:
it did not exist at the bar's open. Its exits are resolved by the stop-first
rule against the whole bar range, which is the conservative reading of an
unknown intrabar path.

R-MULTIPLES
-----------
`risk_per_unit` is frozen at submission as |planned entry - stop loss|. Realised
R is therefore degraded by costs and by gap fills rather than being pinned to
exactly -1.00 on every loser.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import pandas as pd


class Side(Enum):
    LONG = 1
    SHORT = -1

    @property
    def sign(self) -> int:
        return self.value


class ExitReason(Enum):
    STOP_LOSS = "stop_loss"
    TAKE_PROFIT = "take_profit"
    FORCED_CLOSE = "forced_close"


class CancelReason(Enum):
    EXPIRED = "expired"
    STRATEGY = "strategy"
    END_OF_DATA = "end_of_data"


@dataclass(frozen=True)
class Bar:
    """One completed price bar. `open_time` labels its start, `close_time` its end."""

    open_time: pd.Timestamp
    close_time: pd.Timestamp
    open: float
    high: float
    low: float
    close: float

    def __post_init__(self) -> None:
        if not (self.low <= self.open <= self.high and self.low <= self.close <= self.high):
            raise ValueError(f"inconsistent OHLC at {self.open_time}")


@dataclass
class PendingEntry:
    """A resting limit entry with its stop and target already defined."""

    order_id: int
    side: Side
    limit_price: float
    stop_loss: float
    take_profit: float
    created_at: pd.Timestamp
    expires_at: pd.Timestamp | None
    tags: tuple[str, ...] = ()
    meta: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        s = self.side.sign
        if s * (self.limit_price - self.stop_loss) <= 0:
            raise ValueError("stop loss must be on the losing side of entry")
        if s * (self.take_profit - self.limit_price) <= 0:
            raise ValueError("take profit must be on the winning side of entry")

    @property
    def risk_per_unit(self) -> float:
        return abs(self.limit_price - self.stop_loss)

    @property
    def planned_rr(self) -> float:
        return abs(self.take_profit - self.limit_price) / self.risk_per_unit


@dataclass
class Position:
    """An open position. Immutable except for the stop, which a strategy may trail."""

    order_id: int
    side: Side
    entry_price: float
    entry_time: pd.Timestamp
    stop_loss: float
    take_profit: float
    risk_per_unit: float
    planned_entry: float
    opened_this_bar: bool
    tags: tuple[str, ...] = ()
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Trade:
    """A completed round trip."""

    order_id: int
    side: Side
    planned_entry: float
    entry_price: float
    entry_time: pd.Timestamp
    exit_price: float
    exit_time: pd.Timestamp
    stop_loss: float
    take_profit: float
    risk_per_unit: float
    reason: ExitReason
    r_multiple: float
    gross_r: float
    tags: tuple[str, ...] = ()
    meta: dict[str, Any] = field(default_factory=dict)


# --------------------------------------------------------------------------
# Pure fill functions — no state, directly unit-testable
# --------------------------------------------------------------------------


def fill_limit_entry(side: Side, limit: float, bar: Bar, tick: float) -> float | None:
    """Price a resting limit entry fills at during `bar`, or None."""
    if side is Side.LONG:
        traded_through = bar.low <= limit - tick
    else:
        traded_through = bar.high >= limit + tick
    return limit if traded_through else None


def fill_stop_exit(
    side: Side, stop: float, bar: Bar, allow_open_gap: bool
) -> float | None:
    """Price a protective stop fills at during `bar`, or None.

    Triggers on touch. If `allow_open_gap` and the bar opened at or beyond the
    stop, the fill is the bar open — the whole gap is taken as loss.
    """
    if side is Side.LONG:
        if allow_open_gap and bar.open <= stop:
            return bar.open
        return stop if bar.low <= stop else None
    if allow_open_gap and bar.open >= stop:
        return bar.open
    return stop if bar.high >= stop else None


def fill_limit_exit(side: Side, target: float, bar: Bar, tick: float) -> float | None:
    """Price a take-profit limit fills at during `bar`, or None.

    Requires one tick through, like any limit. A gap beyond the target still
    fills at the target — no gap bonus, in either direction.
    """
    if side is Side.LONG:
        traded_through = bar.high >= target + tick
    else:
        traded_through = bar.low <= target - tick
    return target if traded_through else None


def resolve_open_position(
    position: Position, bar: Bar, tick: float
) -> tuple[ExitReason, float] | None:
    """Decide whether `position` exits during `bar`, and at what trigger price.

    Returns the *trigger* price. Converting that into a realised fill price
    (spread, slippage, commission) is the cost model's job, in WP7.
    """
    allow_gap = not position.opened_this_bar

    # 1. Gap phase — a level the bar opened beyond was reached before any
    #    intrabar movement, so it is unambiguous. Stop and target sit on
    #    opposite sides of entry, so at most one of these can be true.
    if allow_gap:
        if position.side is Side.LONG:
            stop_gapped = bar.open <= position.stop_loss
            target_gapped = bar.open >= position.take_profit + tick
        else:
            stop_gapped = bar.open >= position.stop_loss
            target_gapped = bar.open <= position.take_profit - tick
        if stop_gapped:
            # Whole gap taken as loss.
            return ExitReason.STOP_LOSS, bar.open
        if target_gapped:
            # No gap bonus — booked at the target.
            return ExitReason.TAKE_PROFIT, position.take_profit

    # 2. Intrabar phase — stop-first on ambiguity.
    stop_price = fill_stop_exit(position.side, position.stop_loss, bar, False)
    if stop_price is not None:
        return ExitReason.STOP_LOSS, stop_price

    target_price = fill_limit_exit(position.side, position.take_profit, bar, tick)
    if target_price is not None:
        return ExitReason.TAKE_PROFIT, target_price

    return None


def r_multiple(
    side: Side, entry_price: float, exit_price: float, risk_per_unit: float
) -> float:
    """Realised R, using the risk frozen at submission time."""
    if risk_per_unit <= 0:
        raise ValueError("risk_per_unit must be positive")
    return side.sign * (exit_price - entry_price) / risk_per_unit
