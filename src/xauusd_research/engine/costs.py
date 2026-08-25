"""Transaction-cost interface. The concrete models are Work Package 7.

Defined here so the engine is built around costs from the start rather than
having them bolted on afterwards. Two rules the engine enforces and every cost
model must respect:

1. **Costs never move a trigger level.** A stop at 1800 triggers when the market
   touches 1800, whatever the spread is. Costs change the price you *get*, not
   the price that *fires* the order.

2. **R is measured against planned risk**, fixed when the order is submitted as
   |planned entry - stop loss|. So costs make a losing trade worse than -1R
   instead of silently disappearing. This is what makes the mandatory 2x
   cost-stress test in WP11 meaningful.
"""

from __future__ import annotations

from typing import Protocol

from .orders import Bar, ExitReason, Side


class CostModel(Protocol):
    """Adjusts realised fill prices. Implementations arrive in WP7."""

    name: str

    def entry_fill(self, side: Side, trigger_price: float, bar: Bar) -> float:
        """Realised entry price given the level the order fired at."""
        ...

    def exit_fill(
        self, side: Side, trigger_price: float, bar: Bar, reason: ExitReason
    ) -> float:
        """Realised exit price given the level the order fired at."""
        ...

    def commission_per_unit(self, side: Side, entry: float, exit: float) -> float:
        """Round-trip commission expressed per unit of the instrument."""
        ...


class ZeroCostModel:
    """Frictionless baseline — used by the engine's own correctness tests only.

    Never used for a research result: PREREGISTRATION.md requires realistic
    costs in every reported backtest.
    """

    name = "zero"

    def entry_fill(self, side: Side, trigger_price: float, bar: Bar) -> float:
        return trigger_price

    def exit_fill(
        self, side: Side, trigger_price: float, bar: Bar, reason: ExitReason
    ) -> float:
        return trigger_price

    def commission_per_unit(self, side: Side, entry: float, exit: float) -> float:
        return 0.0
