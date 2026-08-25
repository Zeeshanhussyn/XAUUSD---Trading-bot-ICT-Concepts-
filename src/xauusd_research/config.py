"""Preregistered baseline parameters, in one place.

Every value here is traceable to a line of `PREREGISTRATION.md` §2. Nothing is
tuned, and nothing may be changed to improve a result: a change after Work
Package 9 has run is an amendment that must be dated in `PREREGISTRATION.md`,
logged in `RESEARCH_DECISIONS.md`, and called out in the final report.

Work Package 6 extends this file as each feature is implemented.
"""

from __future__ import annotations

from typing import Final

# --- Order lifecycle -------------------------------------------------------

#: Maximum life of a resting limit entry, in real minutes.
#: Amended 2026-08-25 from 25 to 50 minutes — see PREREGISTRATION.md amendment.
#: Under the engine's whole-bar validity rule this is 3 fifteen-minute bars.
#: WP10 ablations: 25 minutes, and current-session-only.
BASELINE_PENDING_VALIDITY_MINUTES: Final[int] = 50

#: WP10 ablation value, kept here so the comparison is defined up front.
ABLATION_PENDING_VALIDITY_MINUTES: Final[int] = 25

# --- Structure -------------------------------------------------------------

#: Fractal swing definition: N bars either side. WP10 ablation: N=3.
BASELINE_SWING_N: Final[int] = 2

#: Displacement Variant A: body >= this multiple of the preceding average body.
BASELINE_DISPLACEMENT_BODY_MULTIPLE: Final[float] = 1.5

#: Lookback for the average body used by displacement Variant A (causal,
#: current candle excluded).
BASELINE_DISPLACEMENT_LOOKBACK: Final[int] = 20

#: ATR period used for the stop buffer and for displacement Variant B.
BASELINE_ATR_PERIOD: Final[int] = 14

#: Stop-loss buffer as a multiple of ATR(14) on the 15m series.
BASELINE_SL_BUFFER_ATR_MULTIPLE: Final[float] = 0.1

# --- Targets and risk ------------------------------------------------------

#: Fixed reward-to-risk of the BENCHMARK exit model (Model 1, full close).
BASELINE_TARGET_RR: Final[float] = 2.0

#: Research cap on trades per day, plus the separate "first N" comparison.
BASELINE_MAX_TRADES_PER_DAY: Final[int] = 5
COMPARISON_MAX_TRADES_PER_DAY: Final[int] = 2

#: Risk-per-trade levels for the equity-curve sensitivity. Reported in that
#: order; 0.50% is the eventual demo default, 1.00% is research sensitivity.
RISK_PER_TRADE_LEVELS: Final[tuple[float, ...]] = (0.0025, 0.005, 0.01)

#: Starting equity used for every equity-curve illustration.
INITIAL_EQUITY: Final[float] = 100_000.0

# --- Sessions --------------------------------------------------------------

#: Session keys defined in `engine.clock.SESSION_WINDOWS`.
BASELINE_TRADING_SESSIONS: Final[tuple[str, ...]] = ("london_tight", "ny_tight")
BASELINE_ASIA_WINDOW: Final[str] = "asia_a"
