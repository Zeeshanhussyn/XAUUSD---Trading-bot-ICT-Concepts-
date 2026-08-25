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

# --- Stop loss -------------------------------------------------------------
#
# CO-PRIMARY baselines (WP7 amendment, 2026-08-25). Both are run and both are
# reported, always side by side. Variant B alone is mechanically unsound for an
# FVG entry: the eligible gap is created by the candle that broke the reference
# swing, so 24% of setups place the entry at or beyond that stop.

#: Beyond the sweep wick. Median stop ~$3.85; every setup produces a valid order.
SL_VARIANT_A = "sweep_extreme"
#: Beyond the swing the MSS broke. Median stop ~$0.81; 24% of setups unexecutable.
SL_VARIANT_B = "mss_invalidation_swing"
#: Neither is "the" baseline. Selecting one after seeing results is forbidden.
CO_PRIMARY_SL_VARIANTS: Final[tuple[str, ...]] = (SL_VARIANT_A, SL_VARIANT_B)

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

# --- Transaction costs (WP7) ----------------------------------------------
#
# LABELLED ASSUMPTIONS, NOT BROKER FACTS. The data source carries no bid/ask,
# so no spread can be measured from it. FOUNDING_BRIEF.md: "Do not pretend
# estimated costs are actual broker facts."
#
# What IS measured, from the user's Dukascopy reference files:
#   * the price series is a BID series (it sits $0.42 below Dukascopy ASK in
#     Jan 2013 and within $0.12 of Dukascopy BID in Feb and Jul 2013), and
#   * the implied Jan-2013 spread was ~$0.41/oz median, ~$0.40 inside the
#     London and New York windows — no better in our trading hours than
#     anywhere else in the day.
#
# The 2013 figure comes from a wide-spread era and an ECN-style broker, so it
# is kept as its own scenario rather than used as the baseline. Values below
# confirmed by the user 2026-08-25.

#: Standard retail account: wider spread, no separate commission. USD per ounce.
STANDARD_SPREAD_PER_OZ: Final[float] = 0.30
STANDARD_COMMISSION_PER_OZ: Final[float] = 0.0

#: Raw/ECN account: tighter spread plus an explicit round-trip commission.
#: $0.07/oz is ~$7 per 100oz standard lot, round trip.
RAW_ECN_SPREAD_PER_OZ: Final[float] = 0.15
RAW_ECN_COMMISSION_PER_OZ: Final[float] = 0.07

#: The 2013-era spread actually measured, kept as a third labelled scenario.
MEASURED_2013_SPREAD_PER_OZ: Final[float] = 0.42
MEASURED_2013_COMMISSION_PER_OZ: Final[float] = 0.0

#: Slippage on stop and market exits only — a limit order fills at its price
#: or not at all, so limits carry none. Always against us.
NORMAL_SLIPPAGE_PER_OZ: Final[float] = 0.10

#: Mandatory stress multiplier applied to the whole transaction cost (WP11).
COST_STRESS_MULTIPLIER: Final[float] = 2.0

# --- Sessions --------------------------------------------------------------

#: Session keys defined in `engine.clock.SESSION_WINDOWS`.
BASELINE_TRADING_SESSIONS: Final[tuple[str, ...]] = ("london_tight", "ny_tight")
BASELINE_ASIA_WINDOW: Final[str] = "asia_a"
