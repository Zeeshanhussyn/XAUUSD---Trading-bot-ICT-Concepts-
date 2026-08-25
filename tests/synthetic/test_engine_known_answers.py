"""End-to-end engine tests on hand-built bars whose outcome is known by arithmetic.

Every scenario uses the same setup so the numbers stay checkable by eye:

    buy limit 1295, stop 1290, target 1305   ->  risk 5, reward 10, exactly 1:2

so a clean win is +2.000R and a clean loss is -1.000R, and any deviation is a
real effect (a gap, a cost) rather than rounding.

These run before any strategy exists. If the engine cannot reproduce arithmetic
we did on paper, nothing built on top of it means anything.
"""

from __future__ import annotations

import pandas as pd
import pytest
from conftest import flat, make_m15

from xauusd_research.engine.backtester import Backtester, equity_curve, summarise
from xauusd_research.engine.orders import CancelReason, ExitReason, Side

LIMIT, STOP, TARGET = 1295.0, 1290.0, 1305.0


class SubmitAtBar:
    """Submits one preset order at the close of bar `at`, then does nothing."""

    def __init__(self, at=0, side=Side.LONG, limit=LIMIT, stop=STOP, target=TARGET,
                 validity_minutes=None):
        self.at, self.side = at, side
        self.limit, self.stop, self.target = limit, stop, target
        self.validity_minutes = validity_minutes
        self.submitted_at = None

    def on_bar_close(self, ctx):
        if ctx.bar_index != self.at:
            return
        expires = None
        if self.validity_minutes is not None:
            expires = ctx.now + pd.Timedelta(minutes=self.validity_minutes)
        ctx.broker.submit(self.side, self.limit, self.stop, self.target, expires_at=expires)
        self.submitted_at = ctx.now


def run(rows, strategy, **kw):
    bt = Backtester(make_m15(rows), **kw)
    return bt, bt.run(strategy)


# ---------------------------------------------------------------- winners --


def test_clean_winner_is_exactly_plus_two_r():
    rows = [
        flat(1300),                              # 0: submit here
        (1300, 1301, 1294.99, 1296),             # 1: limit 1295 fills (1 tick through)
        (1296, 1305.01, 1295, 1305),             # 2: target 1305 taken
    ]
    _, res = run(rows, SubmitAtBar(at=0))
    assert len(res.trades) == 1
    t = res.trades[0]
    assert t.reason is ExitReason.TAKE_PROFIT
    assert t.entry_price == pytest.approx(1295.0)
    assert t.exit_price == pytest.approx(1305.0)
    assert t.r_multiple == pytest.approx(2.0)


def test_clean_loser_is_exactly_minus_one_r():
    rows = [
        flat(1300),
        (1300, 1301, 1294.99, 1296),
        (1296, 1297, 1290.00, 1291),             # stop touched
    ]
    _, res = run(rows, SubmitAtBar(at=0))
    assert res.trades[0].reason is ExitReason.STOP_LOSS
    assert res.trades[0].r_multiple == pytest.approx(-1.0)


def test_short_side_is_the_exact_mirror():
    rows = [
        flat(1300),
        (1300, 1305.01, 1299, 1304),             # sell limit 1305 fills
        (1304, 1305, 1294.99, 1295),             # target 1295 taken
    ]
    strat = SubmitAtBar(at=0, side=Side.SHORT, limit=1305.0, stop=1310.0, target=1295.0)
    _, res = run(rows, strat)
    assert res.trades[0].reason is ExitReason.TAKE_PROFIT
    assert res.trades[0].r_multiple == pytest.approx(2.0)


# ------------------------------------------------------------- ambiguity --


def test_bar_covering_both_levels_books_the_stop():
    rows = [
        flat(1300),
        (1300, 1301, 1294.99, 1296),
        (1296, 1310, 1289, 1300),                # spans stop AND target
    ]
    _, res = run(rows, SubmitAtBar(at=0))
    assert res.trades[0].reason is ExitReason.STOP_LOSS
    assert res.trades[0].r_multiple == pytest.approx(-1.0)


def test_gap_through_target_is_booked_as_a_win_not_a_loss():
    # Opens at 1306, above the 1305 target, then collapses through the stop.
    # The target was reached before any intrabar movement.
    rows = [
        flat(1300),
        (1300, 1301, 1294.99, 1296),
        (1306, 1307, 1285, 1288),
    ]
    _, res = run(rows, SubmitAtBar(at=0))
    assert res.trades[0].reason is ExitReason.TAKE_PROFIT
    assert res.trades[0].exit_price == pytest.approx(1305.0)   # no gap bonus
    assert res.trades[0].r_multiple == pytest.approx(2.0)


def test_gap_through_stop_is_worse_than_minus_one_r():
    rows = [
        flat(1300),
        (1300, 1301, 1294.99, 1296),
        (1288, 1310, 1287, 1300),                # opens below the 1290 stop
    ]
    _, res = run(rows, SubmitAtBar(at=0))
    t = res.trades[0]
    assert t.reason is ExitReason.STOP_LOSS
    assert t.exit_price == pytest.approx(1288.0)               # the gap, not the stop
    assert t.r_multiple == pytest.approx((1288 - 1295) / 5)    # -1.4R


def test_entry_and_exit_in_the_same_bar_gets_no_gap_phase():
    # Bar 1 fills the entry AND spans the stop. Because the position did not
    # exist at this bar's open, the gap phase must not apply: the stop is
    # booked at 1290, not at the 1291 open.
    rows = [
        flat(1300),
        (1291, 1296, 1289, 1292),
    ]
    _, res = run(rows, SubmitAtBar(at=0))
    assert len(res.trades) == 1
    assert res.trades[0].exit_price == pytest.approx(1290.0)
    assert res.trades[0].r_multiple == pytest.approx(-1.0)


# ------------------------------------------------------------ fill rules --


def test_touching_the_limit_exactly_is_not_a_fill():
    rows = [
        flat(1300),
        (1300, 1301, 1295.00, 1296),             # touches 1295, never through
        flat(1300),
    ]
    _, res = run(rows, SubmitAtBar(at=0))
    assert res.trades == []


def test_entry_gap_gives_no_price_improvement():
    rows = [
        flat(1300),
        (1285, 1287, 1284, 1286),                # gaps far below the 1295 limit
        (1286, 1305.01, 1285, 1305),
    ]
    _, res = run(rows, SubmitAtBar(at=0))
    # Filled at 1295 even though the market opened at 1285.
    assert res.trades[0].entry_price == pytest.approx(1295.0)


# --------------------------------------------------------- causality -----


def test_an_order_cannot_fill_on_the_bar_that_produced_it():
    """The central anti-lookahead guarantee.

    Bar 0 pierces the limit deeply. The strategy submits at bar 0's close.
    A naive loop that ran the strategy before resolving fills would book a
    trade here. Nothing after bar 0 ever touches the level again, so the
    only correct answer is zero trades.
    """
    rows = [
        (1300, 1301, 1280, 1300),                # would have filled, if allowed
        flat(1300),
        flat(1300),
    ]
    bt, res = run(rows, SubmitAtBar(at=0))
    assert res.trades == []
    assert len(bt._pending) == 0                 # cleared at end of data
    assert res.cancelled[-1].reason is CancelReason.END_OF_DATA


def test_strategy_sees_the_bar_only_after_its_fills_are_resolved():
    seen = []

    class Recorder:
        def on_bar_close(self, ctx):
            seen.append((ctx.bar_index, ctx.market.now, ctx.market.bars("m15", 1).close[-1]))

    rows = [(1300 + i, 1301 + i, 1299 + i, 1300.5 + i) for i in range(5)]
    bt, _ = run(rows, Recorder())
    for i, now, close in seen:
        assert now == bt.base.close_time[i]
        assert close == pytest.approx(bt.base.df["close"].iloc[i])


# ------------------------------------------------------------- validity --


def test_order_expires_before_the_bar_that_would_have_filled_it():
    # Submitted at bar 0's close (08:15) with 25 minutes validity -> 08:40.
    # Bar 1 closes 08:30 (live). Bar 2 closes 08:45 (expired).
    rows = [
        flat(1300),
        flat(1300),                              # live, but no touch
        (1300, 1301, 1294.99, 1296),             # would have filled — too late
    ]
    _, res = run(rows, SubmitAtBar(at=0, validity_minutes=25))
    assert res.trades == []
    assert [c.reason for c in res.cancelled] == [CancelReason.EXPIRED]


def test_relaxed_validity_lets_the_second_bar_fill():
    rows = [
        flat(1300),
        flat(1300),
        (1300, 1301, 1294.99, 1296),
        (1296, 1305.01, 1295, 1305),
    ]
    _, res = run(rows, SubmitAtBar(at=0, validity_minutes=25), whole_bar_validity=False)
    assert len(res.trades) == 1
    assert res.trades[0].r_multiple == pytest.approx(2.0)


# ------------------------------------------------- one position at a time --


def test_a_second_order_is_cancelled_when_the_first_fills():
    class TwoOrders:
        def on_bar_close(self, ctx):
            if ctx.bar_index == 0:
                ctx.broker.submit(Side.LONG, LIMIT, STOP, TARGET)
                ctx.broker.submit(Side.LONG, 1294.0, 1289.0, 1304.0)

    rows = [
        flat(1300),
        (1300, 1301, 1290.00, 1292),             # both limits pierced
        (1292, 1305.01, 1291, 1305),
    ]
    _, res = run(rows, TwoOrders())
    assert len(res.trades) == 1                  # never two positions at once
    assert res.trades[0].planned_entry == pytest.approx(LIMIT)   # first submitted wins
    assert any(c.order.limit_price == 1294.0 for c in res.cancelled)


def test_no_new_entry_while_a_position_is_open():
    class AlwaysSubmit:
        def on_bar_close(self, ctx):
            if ctx.broker.is_flat and not ctx.broker.pending:
                ctx.broker.submit(Side.LONG, LIMIT, STOP, TARGET)

    rows = [
        flat(1300),
        (1300, 1301, 1294.99, 1296),             # fills
        (1296, 1297, 1294.00, 1295),             # still open, pierces limit again
        (1295, 1305.01, 1294, 1305),             # target
    ]
    _, res = run(rows, AlwaysSubmit())
    assert len(res.trades) == 1


# ------------------------------------------------------------- lifecycle --


def test_position_open_at_end_of_data_is_not_booked():
    rows = [
        flat(1300),
        (1300, 1301, 1294.99, 1296),
        flat(1296),
    ]
    bt, res = run(rows, SubmitAtBar(at=0))
    assert res.trades == []                      # no invented exit
    assert bt.open_at_end is not None
    assert bt.open_at_end.entry_price == pytest.approx(1295.0)


def test_close_now_exits_at_the_current_bar_close():
    class CloseOnBarTwo:
        def on_bar_close(self, ctx):
            if ctx.bar_index == 0:
                ctx.broker.submit(Side.LONG, LIMIT, STOP, TARGET)
            elif ctx.bar_index == 2 and not ctx.broker.is_flat:
                ctx.broker.close_now()

    rows = [
        flat(1300),
        (1300, 1301, 1294.99, 1296),
        (1296, 1300, 1295, 1299),                # closes 1299
    ]
    _, res = run(rows, CloseOnBarTwo())
    t = res.trades[0]
    assert t.reason is ExitReason.FORCED_CLOSE
    assert t.exit_price == pytest.approx(1299.0)
    assert t.r_multiple == pytest.approx((1299 - 1295) / 5)


# ------------------------------------------------------------ accounting --


def test_equity_curve_is_a_plain_rescaling_of_the_r_sequence():
    class Fake:
        def __init__(self, r):
            self.r_multiple = r
            self.exit_time = pd.Timestamp("2016-06-15", tz="UTC") + pd.Timedelta(days=r)

    trades = [Fake(2.0), Fake(-1.0), Fake(2.0)]
    curve = equity_curve(trades, initial_equity=100_000, risk_pct=0.005)
    # Fixed 0.5% of INITIAL equity = $500 per R, never recomputed.
    assert list(curve["pnl"]) == pytest.approx([-500.0, 1000.0, 1000.0])
    assert curve["equity"].iloc[-1] == pytest.approx(101_500.0)


def test_summary_statistics_are_arithmetically_right():
    class Fake:
        def __init__(self, r):
            self.r_multiple = r

    s = summarise([Fake(2.0), Fake(-1.0), Fake(2.0), Fake(-1.0)])
    assert s["n_trades"] == 4
    assert s["total_r"] == pytest.approx(2.0)
    assert s["expectancy_r"] == pytest.approx(0.5)
    assert s["win_rate"] == pytest.approx(0.5)
    assert s["profit_factor"] == pytest.approx(2.0)


def test_empty_result_is_handled_without_crashing():
    _, res = run([flat(1300)] * 3, SubmitAtBar(at=99))
    assert res.trades == []
    assert summarise(res.trades) == {"n_trades": 0}
    assert res.to_frame().empty
