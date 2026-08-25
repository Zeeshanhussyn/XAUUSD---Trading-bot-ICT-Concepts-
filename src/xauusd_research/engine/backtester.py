"""The event loop: one strictly-ordered forward pass over the base series.

The loop contains no strategy logic. A strategy is any object with an
`on_bar_close(ctx)` method; it receives a `MarketView` that cannot return future
data and a `Broker` whose orders cannot act on the bar the strategy is currently
looking at.

PER-BAR ORDER OF OPERATIONS (bar i)
-----------------------------------
1. Age carried state: an open position is no longer "opened this bar"; pending
   orders that are not live for the whole of bar i are expired.
2. Resolve an already-open position against bar i (gap phase, then stop-first).
3. If flat, resolve pending entries against bar i. Only orders submitted at or
   before bar i-1's close are eligible.
4. If an entry filled during bar i, resolve that new position's exits against
   the same bar — with no gap phase, since the position did not exist at the
   bar's open.
5. Only now advance the market view to bar i and call the strategy. Everything
   the strategy does takes effect from bar i+1 onward.

Step 5 coming last is the structural guarantee: by the time a strategy can see
bar i, every fill that bar i could cause has already been decided from orders
that existed before it. A strategy therefore cannot place an order on the bar
that fills it, no matter what it does.

PENDING-ORDER VALIDITY (engine decision, 2026-08-25)
----------------------------------------------------
An order is eligible to fill during a bar only if it is live for the **whole**
bar (`expires_at >= bar.close_time`). The engine never knows where inside a bar
a price level was touched, so it cannot know whether a touch happened before or
after a mid-bar expiry. Refusing the partial bar is the same
"no-intrabar-path-assumption" principle used for stop/target ambiguity, applied
consistently. With the preregistered 25-minute validity this makes an order
live for exactly one 15m bar; `whole_bar_validity=False` relaxes it to any
overlap (two bars) and is offered as a WP10 ablation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

import numpy as np
import pandas as pd

from .clock import TICK_SIZE
from .costs import CostModel, ZeroCostModel
from .marketview import MarketView
from .orders import (
    Bar,
    CancelReason,
    ExitReason,
    PendingEntry,
    Position,
    Side,
    Trade,
    fill_limit_entry,
    r_multiple,
    resolve_open_position,
)
from .resample import BarSeries


class Strategy(Protocol):
    def on_bar_close(self, ctx: "StrategyContext") -> None: ...


@dataclass
class CancelledOrder:
    order: PendingEntry
    reason: CancelReason
    at: pd.Timestamp


class Broker:
    """The strategy's order interface. Cannot act on the current bar."""

    def __init__(self, engine: "Backtester"):
        self._engine = engine

    @property
    def position(self) -> Position | None:
        return self._engine._position

    @property
    def pending(self) -> tuple[PendingEntry, ...]:
        return tuple(self._engine._pending)

    @property
    def is_flat(self) -> bool:
        return self._engine._position is None

    def submit(
        self,
        side: Side,
        limit_price: float,
        stop_loss: float,
        take_profit: float,
        expires_at: pd.Timestamp | None = None,
        tags: tuple[str, ...] = (),
        meta: dict[str, Any] | None = None,
    ) -> int:
        """Submit a resting limit entry. Eligible to fill from the NEXT bar."""
        e = self._engine
        e._next_order_id += 1
        order = PendingEntry(
            order_id=e._next_order_id,
            side=side,
            limit_price=float(limit_price),
            stop_loss=float(stop_loss),
            take_profit=float(take_profit),
            created_at=e._now,
            expires_at=expires_at,
            tags=tags,
            meta=dict(meta or {}),
        )
        e._pending.append(order)
        e._submitted_at_bar[order.order_id] = e._i
        return order.order_id

    def cancel(self, order_id: int, reason: CancelReason = CancelReason.STRATEGY) -> bool:
        e = self._engine
        for k, o in enumerate(e._pending):
            if o.order_id == order_id:
                e._pending.pop(k)
                e.cancelled.append(CancelledOrder(o, reason, e._now))
                return True
        return False

    def cancel_all(self, reason: CancelReason = CancelReason.STRATEGY) -> int:
        e = self._engine
        n = len(e._pending)
        for o in e._pending:
            e.cancelled.append(CancelledOrder(o, reason, e._now))
        e._pending.clear()
        return n

    def modify_stop(self, new_stop: float) -> None:
        """Move the protective stop on the open position (used by runner variants)."""
        pos = self._engine._position
        if pos is None:
            raise RuntimeError("no open position")
        pos.stop_loss = float(new_stop)

    def close_now(self) -> None:
        """Close the open position at the current bar's close price.

        Causal: the bar has completed and its close is known at this instant.
        """
        self._engine._close_requested = True


@dataclass
class StrategyContext:
    market: MarketView
    broker: Broker
    now: pd.Timestamp
    bar: Bar
    bar_index: int


@dataclass
class BacktestResult:
    trades: list[Trade] = field(default_factory=list)
    cancelled: list[CancelledOrder] = field(default_factory=list)
    n_bars: int = 0
    start: pd.Timestamp | None = None
    end: pd.Timestamp | None = None
    cost_model: str = "zero"

    def to_frame(self) -> pd.DataFrame:
        if not self.trades:
            return pd.DataFrame(
                columns=[
                    "order_id", "side", "entry_time", "entry_price", "planned_entry",
                    "exit_time", "exit_price", "stop_loss", "take_profit",
                    "risk_per_unit", "reason", "r_multiple", "gross_r", "tags",
                ]
            )
        return pd.DataFrame(
            [
                {
                    "order_id": t.order_id,
                    "side": t.side.name,
                    "entry_time": t.entry_time,
                    "entry_price": t.entry_price,
                    "planned_entry": t.planned_entry,
                    "exit_time": t.exit_time,
                    "exit_price": t.exit_price,
                    "stop_loss": t.stop_loss,
                    "take_profit": t.take_profit,
                    "risk_per_unit": t.risk_per_unit,
                    "reason": t.reason.value,
                    "r_multiple": t.r_multiple,
                    "gross_r": t.gross_r,
                    "tags": ",".join(t.tags),
                }
                for t in self.trades
            ]
        )


class Backtester:
    """Single forward pass over `base`, feeding a strategy strictly causally."""

    def __init__(
        self,
        base: BarSeries,
        htf: dict[str, BarSeries] | None = None,
        cost_model: CostModel | None = None,
        tick: float = TICK_SIZE,
        whole_bar_validity: bool = True,
    ):
        self.base = base
        self.market = MarketView(base, htf)
        self.cost_model: CostModel = cost_model or ZeroCostModel()
        self.tick = float(tick)
        self.whole_bar_validity = whole_bar_validity

        self._pending: list[PendingEntry] = []
        self._submitted_at_bar: dict[int, int] = {}
        self._position: Position | None = None
        self._next_order_id = 0
        self._i = -1
        self._now: pd.Timestamp | None = None
        self._close_requested = False

        self.trades: list[Trade] = []
        self.cancelled: list[CancelledOrder] = []

        idx = base.df.index
        self._open = base.df["open"].to_numpy(dtype=float)
        self._high = base.df["high"].to_numpy(dtype=float)
        self._low = base.df["low"].to_numpy(dtype=float)
        self._close = base.df["close"].to_numpy(dtype=float)
        self._open_time = idx
        self._close_time = base.close_time

    # ------------------------------------------------------------------
    def run(self, strategy: Strategy) -> BacktestResult:
        broker = Broker(self)
        n = len(self.base)

        for i in range(n):
            self._i = i
            bar = self._bar(i)
            self._now = bar.close_time

            self._age_state(bar)
            self._resolve_position(bar, opened_this_bar=False)
            if self._position is None:
                self._resolve_entries(bar, i)
            if self._position is not None and self._position.opened_this_bar:
                self._resolve_position(bar, opened_this_bar=True)

            # Only now may the strategy see this bar.
            self.market._advance_to(i)
            self._close_requested = False
            strategy.on_bar_close(
                StrategyContext(self.market, broker, bar.close_time, bar, i)
            )
            if self._close_requested and self._position is not None:
                self._book_exit(self._position, ExitReason.FORCED_CLOSE, bar.close, bar)

        self._finalise()
        return BacktestResult(
            trades=self.trades,
            cancelled=self.cancelled,
            n_bars=n,
            start=self._open_time[0] if n else None,
            end=self._close_time[-1] if n else None,
            cost_model=self.cost_model.name,
        )

    # ------------------------------------------------------------------
    def _bar(self, i: int) -> Bar:
        return Bar(
            open_time=self._open_time[i],
            close_time=self._close_time[i],
            open=float(self._open[i]),
            high=float(self._high[i]),
            low=float(self._low[i]),
            close=float(self._close[i]),
        )

    def _age_state(self, bar: Bar) -> None:
        if self._position is not None:
            self._position.opened_this_bar = False
        if not self._pending:
            return
        survivors = []
        for o in self._pending:
            if o.expires_at is None or self._is_live_for(o, bar):
                survivors.append(o)
            else:
                self.cancelled.append(
                    CancelledOrder(o, CancelReason.EXPIRED, bar.open_time)
                )
        self._pending = survivors

    def _is_live_for(self, order: PendingEntry, bar: Bar) -> bool:
        if order.expires_at is None:
            return True
        if self.whole_bar_validity:
            return order.expires_at >= bar.close_time
        return order.expires_at > bar.open_time

    def _resolve_position(self, bar: Bar, opened_this_bar: bool) -> None:
        pos = self._position
        if pos is None or pos.opened_this_bar != opened_this_bar:
            return
        outcome = resolve_open_position(pos, bar, self.tick)
        if outcome is None:
            return
        reason, trigger = outcome
        self._book_exit(pos, reason, trigger, bar)

    def _resolve_entries(self, bar: Bar, i: int) -> None:
        for o in list(self._pending):
            # An order may not fill on the bar it was submitted on.
            if self._submitted_at_bar.get(o.order_id, -1) >= i:
                continue
            trigger = fill_limit_entry(o.side, o.limit_price, bar, self.tick)
            if trigger is None:
                continue
            fill = self.cost_model.entry_fill(o.side, trigger, bar)
            self._position = Position(
                order_id=o.order_id,
                side=o.side,
                entry_price=fill,
                entry_time=bar.close_time,
                stop_loss=o.stop_loss,
                take_profit=o.take_profit,
                risk_per_unit=o.risk_per_unit,
                planned_entry=o.limit_price,
                opened_this_bar=True,
                tags=o.tags,
                meta=dict(o.meta),
            )
            self._pending.remove(o)
            # No overlapping positions (PREREGISTRATION.md §2, hard rule):
            # every other resting order dies the moment one of them fills.
            for other in self._pending:
                self.cancelled.append(
                    CancelledOrder(other, CancelReason.STRATEGY, bar.close_time)
                )
            self._pending.clear()
            return

    def _book_exit(
        self, pos: Position, reason: ExitReason, trigger: float, bar: Bar
    ) -> None:
        fill = self.cost_model.exit_fill(pos.side, trigger, bar, reason)
        commission = self.cost_model.commission_per_unit(pos.side, pos.entry_price, fill)
        gross = r_multiple(pos.side, pos.entry_price, fill, pos.risk_per_unit)
        net = gross - commission / pos.risk_per_unit
        self.trades.append(
            Trade(
                order_id=pos.order_id,
                side=pos.side,
                planned_entry=pos.planned_entry,
                entry_price=pos.entry_price,
                entry_time=pos.entry_time,
                exit_price=fill,
                exit_time=bar.close_time,
                stop_loss=pos.stop_loss,
                take_profit=pos.take_profit,
                risk_per_unit=pos.risk_per_unit,
                reason=reason,
                r_multiple=net,
                gross_r=gross,
                tags=pos.tags,
                meta=dict(pos.meta),
            )
        )
        self._position = None

    def _finalise(self) -> None:
        """Positions still open at the end of the data are discarded, not booked.

        Booking them at the last close would invent an exit the strategy never
        chose. They are counted instead, so an implausible number of them is
        visible rather than hidden.
        """
        for o in self._pending:
            self.cancelled.append(CancelledOrder(o, CancelReason.END_OF_DATA, self._now))
        self._pending.clear()
        self.open_at_end = self._position
        self._position = None


# --------------------------------------------------------------------------
# Equity accounting — fixed risk on INITIAL equity (user decision, WP5 Q4).
# --------------------------------------------------------------------------


def equity_curve(
    trades: list[Trade], initial_equity: float = 100_000.0, risk_pct: float = 0.005
) -> pd.DataFrame:
    """Non-compounding equity curve: every trade risks `risk_pct` of INITIAL equity.

    Chosen so the equity curve is a faithful rescaling of the R sequence — the
    edge and the compounding effect stay separable, and drawdowns are not
    flattered by a good early run.

    Note that a non-compounding curve keeps subtracting the same cash risk after
    the account would in reality have been wiped out, so `equity` can go
    negative. That is arithmetically correct but not a survivable path; use
    `ruin_point()` to find where the account actually died.
    """
    if not trades:
        return pd.DataFrame(columns=["exit_time", "r_multiple", "pnl", "equity", "drawdown"])
    risk_cash = initial_equity * risk_pct
    rows = []
    equity = initial_equity
    peak = initial_equity
    for t in sorted(trades, key=lambda x: x.exit_time):
        pnl = t.r_multiple * risk_cash
        equity += pnl
        peak = max(peak, equity)
        rows.append(
            {
                "exit_time": t.exit_time,
                "r_multiple": t.r_multiple,
                "pnl": pnl,
                "equity": equity,
                "drawdown": equity - peak,
            }
        )
    return pd.DataFrame(rows)


def ruin_point(curve: pd.DataFrame) -> pd.Timestamp | None:
    """Exit time of the trade at which equity first reached zero, or None.

    Reported alongside any equity curve so a wiped-out account is never quietly
    presented as a merely bad final balance.
    """
    if curve.empty:
        return None
    dead = curve.index[curve["equity"] <= 0]
    return None if len(dead) == 0 else curve.loc[dead[0], "exit_time"]


def summarise(trades: list[Trade]) -> dict[str, float]:
    """Headline statistics. Deliberately plain — no metric decides anything alone."""
    if not trades:
        return {"n_trades": 0}
    r = np.array([t.r_multiple for t in trades], dtype=float)
    wins, losses = r[r > 0], r[r <= 0]
    gross_win, gross_loss = float(wins.sum()), float(-losses.sum())
    return {
        "n_trades": int(len(r)),
        "expectancy_r": float(r.mean()),
        "total_r": float(r.sum()),
        "win_rate": float(len(wins) / len(r)),
        "profit_factor": float(gross_win / gross_loss) if gross_loss > 0 else float("inf"),
        "best_r": float(r.max()),
        "worst_r": float(r.min()),
        "std_r": float(r.std(ddof=1)) if len(r) > 1 else 0.0,
    }
