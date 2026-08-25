"""Engine behaviour on real XAUUSD bars, including genuine market gaps.

The synthetic tests prove the rules are implemented as written. These prove the
rules actually fire on real data — a rule that is correct but unreachable is
worth nothing.

The most useful test here is `test_information_free_entries_do_not_manufacture_edge`.
A lookahead leak does not raise an exception; it shows up as an entry rule that
has no information suddenly making money. Pinning an information-free strategy
to its theoretical breakeven catches that.
"""

from __future__ import annotations

import pandas as pd
import pytest

from xauusd_research.engine.backtester import Backtester, summarise
from xauusd_research.engine.orders import Bar, ExitReason, Position, Side, resolve_open_position
from xauusd_research.engine.resample import base_series

TICK = 0.01


class FixedDistanceLong:
    """Buy 0.50 below the close, 3.00 stop, 6.00 target — a strict 1:2.

    The entry level carries no information about future direction, so with no
    costs the expectancy should sit at breakeven minus whatever the gap rules
    take out. Nothing about it can be profitable unless the engine is cheating.
    """

    def on_bar_close(self, ctx):
        if not ctx.broker.is_flat or ctx.broker.pending:
            return
        close = ctx.market.bars("m15", 1).close[-1]
        limit = round(close - 0.50, 2)
        ctx.broker.submit(
            Side.LONG, limit, round(limit - 3.0, 2), round(limit + 6.0, 2),
            expires_at=ctx.now + pd.Timedelta(minutes=25),
        )


@pytest.fixture(scope="module")
def slice_result(request):
    m15 = pd.read_parquet(
        request.config.rootpath / "data" / "processed" / "XAUUSD_m15.parquet"
    ).iloc[:60000]
    bt = Backtester(base_series(m15))
    return bt.run(FixedDistanceLong())


def test_engine_produces_trades_on_real_data(slice_result):
    assert len(slice_result.trades) > 500


def test_no_win_ever_exceeds_the_target(slice_result):
    """The single hardest guarantee to get right, and the easiest to lose.

    A gap through the target must be booked AT the target. If any trade returns
    more than the planned 2R, the engine is crediting gap improvement to us and
    every reported result is inflated.
    """
    assert max(t.r_multiple for t in slice_result.trades) == pytest.approx(2.0)
    assert not [t for t in slice_result.trades if t.r_multiple > 2.0 + 1e-9]


def test_gap_losses_exist_and_are_worse_than_one_r(slice_result):
    """Losses may exceed 1R — that is what a real overnight gap costs."""
    gap_losses = [t for t in slice_result.trades if t.r_multiple < -1.0 - 1e-9]
    assert gap_losses, "no gap loss found — the gap path is not being exercised"
    for t in gap_losses:
        assert t.reason is ExitReason.STOP_LOSS
        assert t.exit_price < t.stop_loss  # filled beyond the stop, at the open


def test_ordinary_losses_are_exactly_minus_one_r(slice_result):
    ordinary = [t for t in slice_result.trades if t.exit_price == t.stop_loss]
    assert ordinary
    for t in ordinary:
        assert t.r_multiple == pytest.approx(-1.0)


def test_information_free_entries_do_not_manufacture_edge(slice_result):
    """A zero-information 1:2 system must land near its theoretical breakeven.

    Breakeven win rate for 1:2 is 1/3. Real gaps drag it slightly below. A
    materially higher win rate would mean the engine is leaking future data
    into the entry decision.
    """
    s = summarise(slice_result.trades)
    assert 0.28 < s["win_rate"] < 0.36, s
    assert -0.20 < s["expectancy_r"] < 0.05, s


def test_every_exit_happens_at_or_after_its_entry(slice_result):
    for t in slice_result.trades:
        assert t.exit_time >= t.entry_time


def test_trades_never_overlap(slice_result):
    trades = sorted(slice_result.trades, key=lambda t: t.entry_time)
    for a, b in zip(trades, trades[1:]):
        assert b.entry_time >= a.exit_time


# -- the real gap that broke gold on 2013-04-15 ----------------------------


def test_real_crash_gap_is_booked_at_the_open(real_m15):
    """2013-04-15 01:45 UTC: gold opened 16.25 below the previous close.

    A stop sitting inside that gap can only fill at the open. Booking it at the
    stop price would understate the loss by more than 2R.
    """
    ts = pd.Timestamp("2013-04-15 01:45", tz="UTC")
    row = real_m15.loc[ts]
    prev_close = real_m15["close"].shift(1).loc[ts]
    assert row["open"] < prev_close - 16.0  # the gap is real

    bar = Bar(ts, ts + pd.Timedelta(minutes=15), row["open"], row["high"], row["low"], row["close"])
    entry, stop = float(prev_close), float(prev_close) - 6.63
    pos = Position(
        order_id=1, side=Side.LONG, entry_price=entry, entry_time=ts - pd.Timedelta(minutes=15),
        stop_loss=stop, take_profit=entry + 13.26, risk_per_unit=6.63,
        planned_entry=entry, opened_this_bar=False,
    )
    reason, price = resolve_open_position(pos, bar, TICK)
    assert reason is ExitReason.STOP_LOSS
    assert price == pytest.approx(row["open"])       # the gap, not the stop
    assert (price - entry) / 6.63 < -2.0             # materially worse than -1R


def test_gap_rule_fires_across_many_real_gaps(real_m15):
    """Sweep every large real gap-down and confirm the fill is always the open."""
    prev_close = real_m15["close"].shift(1)
    gaps = (real_m15["open"] - prev_close)
    big = gaps[gaps < -3.0].index[:40]
    assert len(big) >= 20

    checked = 0
    for ts in big:
        row = real_m15.loc[ts]
        entry = float(prev_close.loc[ts])
        stop = entry - 1.0                            # stop lies inside the gap
        if row["open"] > stop:
            continue
        bar = Bar(ts, ts + pd.Timedelta(minutes=15), row["open"], row["high"], row["low"], row["close"])
        pos = Position(
            order_id=1, side=Side.LONG, entry_price=entry, entry_time=ts,
            stop_loss=stop, take_profit=entry + 2.0, risk_per_unit=1.0,
            planned_entry=entry, opened_this_bar=False,
        )
        reason, price = resolve_open_position(pos, bar, TICK)
        assert reason is ExitReason.STOP_LOSS
        assert price == pytest.approx(row["open"])
        checked += 1
    assert checked >= 20
