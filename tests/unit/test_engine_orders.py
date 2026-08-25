"""Fill-simulation rules, tested one rule at a time with hand-computed answers.

These are the rules that decide every trade in the project. If any of them is
wrong, every downstream result is wrong in a way no summary statistic reveals.
"""

from __future__ import annotations

import pandas as pd
import pytest

from xauusd_research.engine.orders import (
    Bar,
    ExitReason,
    PendingEntry,
    Position,
    Side,
    fill_limit_entry,
    fill_limit_exit,
    fill_stop_exit,
    r_multiple,
    resolve_open_position,
)

TICK = 0.01
T0 = pd.Timestamp("2016-06-15 08:00:00", tz="UTC")


def bar(o, h, l, c) -> Bar:
    return Bar(T0, T0 + pd.Timedelta(minutes=15), o, h, l, c)


def position(side, entry, sl, tp, opened_this_bar=False) -> Position:
    return Position(
        order_id=1,
        side=side,
        entry_price=entry,
        entry_time=T0,
        stop_loss=sl,
        take_profit=tp,
        risk_per_unit=abs(entry - sl),
        planned_entry=entry,
        opened_this_bar=opened_this_bar,
    )


# -- limit entry: one tick THROUGH, never a touch ---------------------------


def test_buy_limit_needs_one_tick_through():
    # Limit 1300. Bar low exactly 1300 = a touch, not a fill.
    assert fill_limit_entry(Side.LONG, 1300.0, bar(1305, 1306, 1300.00, 1304), TICK) is None
    # One tick through fills, and fills at the limit price.
    assert fill_limit_entry(Side.LONG, 1300.0, bar(1305, 1306, 1299.99, 1304), TICK) == 1300.0


def test_sell_limit_needs_one_tick_through():
    assert fill_limit_entry(Side.SHORT, 1300.0, bar(1295, 1300.00, 1294, 1296), TICK) is None
    assert fill_limit_entry(Side.SHORT, 1300.0, bar(1295, 1300.01, 1294, 1296), TICK) == 1300.0


def test_limit_entry_gap_gives_no_bonus():
    # Market gaps far below a 1300 buy limit. We are still filled at 1300,
    # not at the much better 1290 open.
    assert fill_limit_entry(Side.LONG, 1300.0, bar(1290, 1292, 1288, 1291), TICK) == 1300.0


# -- stop loss: triggers on touch, gap taken in full ------------------------


def test_stop_triggers_on_touch_no_tick_needed():
    assert fill_stop_exit(Side.LONG, 1290.0, bar(1300, 1301, 1290.00, 1295), False) == 1290.0
    assert fill_stop_exit(Side.LONG, 1290.0, bar(1300, 1301, 1290.01, 1295), False) is None


def test_stop_gap_at_open_fills_at_open_not_at_stop():
    # Long stopped at 1290, bar opens at 1285 — we take the whole gap.
    assert fill_stop_exit(Side.LONG, 1290.0, bar(1285, 1288, 1284, 1286), True) == 1285.0
    # Short stopped at 1310, bar opens at 1316.
    assert fill_stop_exit(Side.SHORT, 1310.0, bar(1316, 1318, 1315, 1317), True) == 1316.0


def test_stop_gap_ignored_when_position_opened_mid_bar():
    # Same bar, but the position did not exist at the open, so no gap fill:
    # the stop is booked at the stop price.
    assert fill_stop_exit(Side.LONG, 1290.0, bar(1285, 1288, 1284, 1286), False) == 1290.0


# -- take profit: one tick through, never a gap bonus -----------------------


def test_take_profit_needs_one_tick_through():
    assert fill_limit_exit(Side.LONG, 1320.0, bar(1300, 1320.00, 1299, 1319), TICK) is None
    assert fill_limit_exit(Side.LONG, 1320.0, bar(1300, 1320.01, 1299, 1319), TICK) == 1320.0


def test_take_profit_gap_gives_no_bonus():
    # Gaps open to 1330 on a 1320 target — booked at 1320.
    assert fill_limit_exit(Side.LONG, 1320.0, bar(1330, 1332, 1329, 1331), TICK) == 1320.0


# -- ambiguity resolution ---------------------------------------------------


def test_stop_first_when_bar_spans_both_levels():
    # Entry 1300, stop 1290, target 1320. The bar covers both. Stop wins.
    pos = position(Side.LONG, 1300.0, 1290.0, 1320.0)
    reason, price = resolve_open_position(pos, bar(1300, 1325, 1285, 1310), TICK)
    assert reason is ExitReason.STOP_LOSS
    assert price == 1290.0


def test_gap_through_target_beats_stop_first():
    # The bar OPENS at 1330, above the 1320 target, then falls through the
    # 1290 stop. The target was reached before any intrabar move, so booking
    # a loss here would be wrong, not merely conservative.
    pos = position(Side.LONG, 1300.0, 1290.0, 1320.0)
    reason, price = resolve_open_position(pos, bar(1330, 1331, 1285, 1288), TICK)
    assert reason is ExitReason.TAKE_PROFIT
    assert price == 1320.0


def test_gap_through_stop_beats_everything():
    pos = position(Side.LONG, 1300.0, 1290.0, 1320.0)
    reason, price = resolve_open_position(pos, bar(1280, 1325, 1279, 1322), TICK)
    assert reason is ExitReason.STOP_LOSS
    assert price == 1280.0  # the gap, not the stop


def test_position_opened_this_bar_gets_no_gap_phase():
    # Identical bar to the previous test, but the position was opened during
    # this bar, so the open price is irrelevant: stop-first at the stop price.
    pos = position(Side.LONG, 1300.0, 1290.0, 1320.0, opened_this_bar=True)
    reason, price = resolve_open_position(pos, bar(1280, 1325, 1279, 1322), TICK)
    assert reason is ExitReason.STOP_LOSS
    assert price == 1290.0


def test_no_exit_when_bar_touches_neither_level():
    pos = position(Side.LONG, 1300.0, 1290.0, 1320.0)
    assert resolve_open_position(pos, bar(1300, 1310, 1295, 1305), TICK) is None


# -- short side mirrors long side exactly ----------------------------------


def test_short_stop_first_mirrors_long():
    pos = position(Side.SHORT, 1300.0, 1310.0, 1280.0)
    reason, price = resolve_open_position(pos, bar(1300, 1315, 1275, 1290), TICK)
    assert reason is ExitReason.STOP_LOSS
    assert price == 1310.0


def test_short_take_profit():
    pos = position(Side.SHORT, 1300.0, 1310.0, 1280.0)
    reason, price = resolve_open_position(pos, bar(1300, 1302, 1279.99, 1281), TICK)
    assert reason is ExitReason.TAKE_PROFIT
    assert price == 1280.0


# -- R arithmetic -----------------------------------------------------------


def test_r_multiple_is_exact():
    assert r_multiple(Side.LONG, 1300.0, 1320.0, 10.0) == pytest.approx(2.0)
    assert r_multiple(Side.LONG, 1300.0, 1290.0, 10.0) == pytest.approx(-1.0)
    assert r_multiple(Side.SHORT, 1300.0, 1280.0, 10.0) == pytest.approx(2.0)
    assert r_multiple(Side.SHORT, 1300.0, 1310.0, 10.0) == pytest.approx(-1.0)


def test_gap_loss_is_worse_than_minus_one_r():
    # This is the whole point of freezing risk at submission: a gap through the
    # stop must show up as worse than -1R, not be rounded back to -1R.
    assert r_multiple(Side.LONG, 1300.0, 1285.0, 10.0) == pytest.approx(-1.5)


# -- order validation -------------------------------------------------------


def test_order_rejects_stop_on_the_wrong_side():
    with pytest.raises(ValueError):
        PendingEntry(1, Side.LONG, 1300.0, 1310.0, 1320.0, T0, None)
    with pytest.raises(ValueError):
        PendingEntry(1, Side.LONG, 1300.0, 1290.0, 1295.0 - 10, T0, None)


def test_order_computes_risk_and_rr():
    o = PendingEntry(1, Side.LONG, 1300.0, 1290.0, 1320.0, T0, None)
    assert o.risk_per_unit == pytest.approx(10.0)
    assert o.planned_rr == pytest.approx(2.0)


def test_bar_rejects_impossible_ohlc():
    with pytest.raises(ValueError):
        Bar(T0, T0 + pd.Timedelta(minutes=15), 100, 90, 95, 92)  # high < low
