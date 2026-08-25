"""Cost arithmetic, checked against hand-computed numbers.

The rule under test: the series is a BID series, so exactly one leg of every
round trip transacts at the ask and pays the spread — the buy leg. Long pays it
going in, short pays it coming out. Never both, never neither.
"""

from __future__ import annotations

import pandas as pd
import pytest

from xauusd_research.engine.costs import (
    MEASURED_2013_ERA,
    RAW_ECN_ACCOUNT,
    STANDARD_ACCOUNT,
    SpreadCommissionModel,
    ZeroCostModel,
    stressed,
)
from xauusd_research.engine.orders import Bar, ExitReason, Side, r_multiple

T0 = pd.Timestamp("2016-06-15 08:00", tz="UTC")
BAR = Bar(T0, T0 + pd.Timedelta(minutes=15), 1300.0, 1310.0, 1290.0, 1305.0)

M = SpreadCommissionModel(name="test", spread=0.30, commission=0.07, slippage=0.10)


# -- which leg pays the spread ---------------------------------------------


def test_long_pays_the_spread_going_in():
    assert M.entry_fill(Side.LONG, 1300.0, BAR) == pytest.approx(1300.30)


def test_short_pays_nothing_going_in():
    # A short sells at the bid, which is what the series already quotes.
    assert M.entry_fill(Side.SHORT, 1300.0, BAR) == pytest.approx(1300.00)


def test_long_pays_nothing_coming_out():
    assert M.exit_fill(Side.LONG, 1320.0, BAR, ExitReason.TAKE_PROFIT) == pytest.approx(1320.0)


def test_short_pays_the_spread_coming_out():
    assert M.exit_fill(Side.SHORT, 1280.0, BAR, ExitReason.TAKE_PROFIT) == pytest.approx(1280.30)


def test_the_spread_is_paid_exactly_once_either_way():
    long_cost = (M.entry_fill(Side.LONG, 1300.0, BAR) - 1300.0) + (
        1320.0 - M.exit_fill(Side.LONG, 1320.0, BAR, ExitReason.TAKE_PROFIT)
    )
    short_cost = (1300.0 - M.entry_fill(Side.SHORT, 1300.0, BAR)) + (
        M.exit_fill(Side.SHORT, 1280.0, BAR, ExitReason.TAKE_PROFIT) - 1280.0
    )
    assert long_cost == pytest.approx(0.30)
    assert short_cost == pytest.approx(0.30)


# -- slippage ---------------------------------------------------------------


def test_slippage_hits_stops_but_not_targets():
    assert M.exit_fill(Side.LONG, 1290.0, BAR, ExitReason.STOP_LOSS) == pytest.approx(1289.90)
    assert M.exit_fill(Side.LONG, 1320.0, BAR, ExitReason.TAKE_PROFIT) == pytest.approx(1320.00)


def test_slippage_hits_forced_closes_too():
    assert M.exit_fill(Side.LONG, 1305.0, BAR, ExitReason.FORCED_CLOSE) == pytest.approx(1304.90)


def test_slippage_is_always_adverse_on_both_sides():
    # Long sells lower; short buys higher. Never the reverse.
    assert M.exit_fill(Side.LONG, 1290.0, BAR, ExitReason.STOP_LOSS) < 1290.0
    assert M.exit_fill(Side.SHORT, 1310.0, BAR, ExitReason.STOP_LOSS) > 1310.0


def test_short_stop_pays_both_spread_and_slippage():
    assert M.exit_fill(Side.SHORT, 1310.0, BAR, ExitReason.STOP_LOSS) == pytest.approx(1310.40)


# -- round-trip totals ------------------------------------------------------


def test_round_trip_cost_adds_up():
    assert M.round_trip_cost(ExitReason.TAKE_PROFIT) == pytest.approx(0.37)  # 0.30 + 0.07
    assert M.round_trip_cost(ExitReason.STOP_LOSS) == pytest.approx(0.47)    # + 0.10 slip


def test_cost_in_r_scales_with_stop_distance():
    # A $3 stop takes proportionally more cost damage than a $10 stop.
    assert M.cost_in_r(3.0, ExitReason.STOP_LOSS) == pytest.approx(0.47 / 3.0)
    assert M.cost_in_r(10.0, ExitReason.STOP_LOSS) == pytest.approx(0.047)


def test_a_loser_ends_up_worse_than_minus_one_r_after_costs():
    """The whole reason risk is frozen at submission: costs must show up."""
    entry = M.entry_fill(Side.LONG, 1300.0, BAR)          # 1300.30
    exit_ = M.exit_fill(Side.LONG, 1297.0, BAR, ExitReason.STOP_LOSS)  # 1296.90
    risk = 3.0                                             # planned |1300 - 1297|
    gross = r_multiple(Side.LONG, entry, exit_, risk)
    net = gross - M.commission_per_unit(Side.LONG, entry, exit_) / risk
    assert net < -1.0
    assert net == pytest.approx(((1296.90 - 1300.30) / 3.0) - (0.07 / 3.0))


def test_a_winner_ends_up_below_its_planned_two_r():
    entry = M.entry_fill(Side.LONG, 1300.0, BAR)
    exit_ = M.exit_fill(Side.LONG, 1306.0, BAR, ExitReason.TAKE_PROFIT)
    risk = 3.0
    net = r_multiple(Side.LONG, entry, exit_, risk) - 0.07 / risk
    assert 1.0 < net < 2.0


# -- stress -----------------------------------------------------------------


def test_stress_doubles_every_component():
    s = stressed(M, 2.0)
    assert (s.spread, s.commission, s.slippage) == pytest.approx((0.60, 0.14, 0.20))
    assert s.round_trip_cost(ExitReason.STOP_LOSS) == pytest.approx(2 * 0.47)
    assert "x2" in s.name


def test_stress_keeps_the_provenance_label():
    assert "stress" in stressed(M).basis


# -- the pre-registered profiles -------------------------------------------


def test_profiles_have_the_confirmed_values():
    assert (STANDARD_ACCOUNT.spread, STANDARD_ACCOUNT.commission) == (0.30, 0.0)
    assert (RAW_ECN_ACCOUNT.spread, RAW_ECN_ACCOUNT.commission) == (0.15, 0.07)
    assert MEASURED_2013_ERA.spread == 0.42


def test_raw_ecn_is_cheaper_than_standard_overall():
    tp = ExitReason.TAKE_PROFIT
    assert RAW_ECN_ACCOUNT.round_trip_cost(tp) < STANDARD_ACCOUNT.round_trip_cost(tp)


def test_every_profile_is_labelled_as_an_assumption(caplog):
    for m in (STANDARD_ACCOUNT, RAW_ECN_ACCOUNT, MEASURED_2013_ERA):
        assert "assumption" in m.basis or "measured" in m.basis


def test_negative_costs_are_rejected():
    with pytest.raises(ValueError):
        SpreadCommissionModel(name="bad", spread=-0.1, commission=0.0)


def test_zero_cost_model_really_is_free():
    z = ZeroCostModel()
    assert z.entry_fill(Side.LONG, 1300.0, BAR) == 1300.0
    assert z.exit_fill(Side.SHORT, 1300.0, BAR, ExitReason.STOP_LOSS) == 1300.0
    assert z.commission_per_unit(Side.LONG, 1300.0, 1310.0) == 0.0
