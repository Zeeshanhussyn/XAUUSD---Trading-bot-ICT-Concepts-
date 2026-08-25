"""Transaction costs: spread, commission, slippage (Work Package 7).

THE ONE FACT EVERYTHING HERE RESTS ON
-------------------------------------
The price series is a **BID** series. Measured, not assumed, against the user's
Dukascopy reference files:

    vs Dukascopy ASK (Jan 2013, 525 hourly bars)   -$0.42
    vs Dukascopy BID (Feb 2013, 457 hourly bars)   +$0.03
    vs Dukascopy BID (Jul 2013, 524 hourly bars)   +$0.12

So every price level in this project — every level, stop, target and entry — is
expressed in bid terms, and the rule for costs follows directly:

    **Any leg that transacts at the ASK pays the spread. Legs that transact at
    the bid pay nothing. Stops and market exits additionally pay slippage.**

    long  entry = BUY  at ask -> pays spread
    long  exit  = SELL at bid -> pays nothing
    short entry = SELL at bid -> pays nothing
    short exit  = BUY  at ask -> pays spread

Exactly one leg of every round trip pays the spread, never two and never none.
Getting this backwards would either double the cost or delete it, and nothing in
a summary statistic would reveal which.

Slippage applies only where execution is at market: a stop loss or a forced
close. A limit order fills at its price or does not fill, so take-profits and
limit entries carry none. Slippage is always adverse.

WHAT THESE NUMBERS ARE
----------------------
Labelled assumptions, not the user's broker's facts. The data source has no
bid/ask, so no spread can be measured from it for the backtest period.
FOUNDING_BRIEF.md is explicit: "Do not pretend estimated costs are actual broker
facts." Every report must carry that label.

WHAT CANNOT BE BUILT, AND WHY IT IS NOT FAKED
---------------------------------------------
* **Abnormal-spread filter** (the brief's spread variant B) needs a spread that
  varies bar by bar. We have one assumed constant, so the filter would only ever
  compare a number against itself. Not implemented; recorded as a limitation.
* **News-period slippage** needs point-in-time economic-event timestamps, which
  this sandbox cannot reach. The brief says: "If trustworthy point-in-time data
  cannot be obtained for a particular field: DO NOT fabricate it." Not
  implemented; recorded as a limitation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ..config import (
    COST_STRESS_MULTIPLIER,
    MEASURED_2013_COMMISSION_PER_OZ,
    MEASURED_2013_SPREAD_PER_OZ,
    NORMAL_SLIPPAGE_PER_OZ,
    RAW_ECN_COMMISSION_PER_OZ,
    RAW_ECN_SPREAD_PER_OZ,
    STANDARD_COMMISSION_PER_OZ,
    STANDARD_SPREAD_PER_OZ,
)
from .orders import Bar, ExitReason, Side

#: Exits that execute at market and therefore suffer slippage.
MARKET_EXITS = (ExitReason.STOP_LOSS, ExitReason.FORCED_CLOSE)


class CostModel(Protocol):
    """Adjusts realised fill prices. Never moves a trigger level."""

    name: str

    def entry_fill(self, side: Side, trigger_price: float, bar: Bar) -> float: ...

    def exit_fill(
        self, side: Side, trigger_price: float, bar: Bar, reason: ExitReason
    ) -> float: ...

    def commission_per_unit(self, side: Side, entry: float, exit: float) -> float: ...


class ZeroCostModel:
    """Frictionless. Engine correctness tests only — never a research result."""

    name = "zero"

    def entry_fill(self, side: Side, trigger_price: float, bar: Bar) -> float:
        return trigger_price

    def exit_fill(
        self, side: Side, trigger_price: float, bar: Bar, reason: ExitReason
    ) -> float:
        return trigger_price

    def commission_per_unit(self, side: Side, entry: float, exit: float) -> float:
        return 0.0


@dataclass(frozen=True)
class SpreadCommissionModel:
    """Constant spread on the ask leg, commission per round trip, adverse slippage.

    All figures are USD per ounce, matching the price units of the series.
    """

    name: str
    spread: float
    commission: float
    slippage: float = NORMAL_SLIPPAGE_PER_OZ
    #: Human-readable provenance, reproduced in every report that uses it.
    basis: str = "labelled assumption — not the user's broker's actual terms"

    def __post_init__(self) -> None:
        for field in ("spread", "commission", "slippage"):
            if getattr(self, field) < 0:
                raise ValueError(f"{field} cannot be negative")

    # -- fills --------------------------------------------------------------

    def entry_fill(self, side: Side, trigger_price: float, bar: Bar) -> float:
        """A long buys at the ask and pays the spread; a short sells at the bid."""
        if side is Side.LONG:
            return trigger_price + self.spread
        return trigger_price

    def exit_fill(
        self, side: Side, trigger_price: float, bar: Bar, reason: ExitReason
    ) -> float:
        """A long sells at the bid; a short buys at the ask and pays the spread.

        Stops and forced closes execute at market and give up `slippage` on top,
        always in the losing direction.
        """
        slip = self.slippage if reason in MARKET_EXITS else 0.0
        if side is Side.LONG:
            return trigger_price - slip
        return trigger_price + self.spread + slip

    def commission_per_unit(self, side: Side, entry: float, exit: float) -> float:
        return self.commission

    # -- round-trip view ----------------------------------------------------

    def round_trip_cost(self, reason: ExitReason = ExitReason.TAKE_PROFIT) -> float:
        """Total cost of one round trip in USD per ounce.

        Identical for long and short, which is the point: exactly one leg pays
        the spread either way.
        """
        slip = self.slippage if reason in MARKET_EXITS else 0.0
        return self.spread + self.commission + slip

    def cost_in_r(self, risk_per_unit: float, reason: ExitReason) -> float:
        """The same cost expressed as a fraction of one R."""
        if risk_per_unit <= 0:
            raise ValueError("risk_per_unit must be positive")
        return self.round_trip_cost(reason) / risk_per_unit


def stressed(model: SpreadCommissionModel, factor: float = COST_STRESS_MULTIPLIER):
    """Scale every cost component — the brief's mandatory 2x total-cost stress."""
    return SpreadCommissionModel(
        name=f"{model.name}_x{factor:g}",
        spread=model.spread * factor,
        commission=model.commission * factor,
        slippage=model.slippage * factor,
        basis=f"{model.basis}; all components scaled x{factor:g} as a stress test",
    )


# --------------------------------------------------------------------------
# The pre-registered profiles (values confirmed by the user 2026-08-25)
# --------------------------------------------------------------------------

STANDARD_ACCOUNT = SpreadCommissionModel(
    name="standard",
    spread=STANDARD_SPREAD_PER_OZ,
    commission=STANDARD_COMMISSION_PER_OZ,
    basis="typical retail standard-account XAUUSD terms — labelled assumption",
)

RAW_ECN_ACCOUNT = SpreadCommissionModel(
    name="raw_ecn",
    spread=RAW_ECN_SPREAD_PER_OZ,
    commission=RAW_ECN_COMMISSION_PER_OZ,
    basis="typical raw/ECN XAUUSD terms (~$7 per 100oz lot round trip) — labelled assumption",
)

MEASURED_2013_ERA = SpreadCommissionModel(
    name="measured_2013",
    spread=MEASURED_2013_SPREAD_PER_OZ,
    commission=MEASURED_2013_COMMISSION_PER_OZ,
    basis=(
        "implied Dukascopy spread measured from the user's own reference files, "
        "Jan 2013 (median $0.41/oz over 525 hourly bars) — a wide-spread era, "
        "kept as a scenario rather than the baseline"
    ),
)

#: Reported side by side. The baseline for WP9 is STANDARD_ACCOUNT.
COST_PROFILES = (STANDARD_ACCOUNT, RAW_ECN_ACCOUNT, MEASURED_2013_ERA)
