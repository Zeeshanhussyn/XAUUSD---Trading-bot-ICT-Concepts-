"""Work Package 8 — non-blocking analysis tags.

FOUNDING_BRIEF.md, "WORK PACKAGE 8": these attach descriptive information to a
setup, an order block, or a bar for later ablation slicing (WP10) and
reporting. **None of them may filter, block, or otherwise change which trades
are taken or how they are priced** — the brief says so for every one of them
("Analysis tag only" / "Tags must not silently alter trade decisions"), and
nothing here is imported by `engine/backtester.py`, `features/structure.py`,
or `features/fvg.py`. `run_tags_report.py` proves this by construction: it
never touches P/L.

The brief names nine tags but only gives a mechanical definition for two of
them (Liquidity Cluster's ATR proximity bands, Sequential Liquidity Events'
worked example). The rest are "analysis tag only" without saying how to
compute one. Two different kinds of gap followed, and they were closed two
different ways:

* Genuinely open choices — put to the user as an A/B choice 2026-08-25 (WP8
  Q1-4) and recorded as a dated `PREREGISTRATION.md` amendment: the Order
  Block definition (which also fixes Breaker and Mitigation, since both are
  states an order block passes through), the Equal-Highs/Lows tolerance, the
  Premium/Discount reference range, and the Market Regime method.
* Direct, unambiguous extensions of a rule already fixed elsewhere in the
  project — implemented here as Claude's default and logged, not put to a
  vote, because a reasonable person reading the existing rule would build it
  the same way: the previous-WEEK boundary (a mechanical extension of the
  already-approved 17:00-NY trading DAY boundary) and which sweep counts as
  "later" for Sequential Liquidity Events (the brief's own worked example is
  same-day; nothing here introduces a new day/session boundary).

The 1-minute context tag (brief, "1-MINUTE TIMEFRAME") is **not implemented**:
this project never acquired minute-level XAUUSD data in bulk (see
`PREREGISTRATION.md`'s WP3 amendment — free multi-year 5m-or-finer data was
not obtainable), and nothing at that resolution exists in `data/processed/`.
This is a data-availability gap, logged here for restatement in WP15, in the
same spirit as WP7's un-implemented abnormal-spread filter and news blackout.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum

import numpy as np
import pandas as pd

from ..config import (
    EQH_EQL_ATR_MULTIPLE,
    LIQUIDITY_CLUSTER_TIGHT_ATR_MULTIPLE,
    LIQUIDITY_CLUSTER_WIDE_ATR_MULTIPLE,
    OB_SEARCH_LOOKBACK,
    REGIME_ATR_PERCENTILE_WINDOW,
    REGIME_HIGH_VOL_PERCENTILE,
    REGIME_LOW_VOL_PERCENTILE,
    REGIME_TREND_PERCENTILE,
    REGIME_TREND_WINDOW,
)
from ..engine.clock import bar_close_index, trading_day_bounds, trading_day_index
from .bias import Bias
from .fvg import Setup
from .levels import ASIA_HIGH, ASIA_LOW, PDH, PDL, LevelBook
from .sweeps import Sweep
from .swings import Swing, SwingSeries, SwingType
from .structure import MSS

# ==========================================================================
# Order Block / Breaker / Mitigation
# ==========================================================================
#
# WP8 Q1 (confirmed by user 2026-08-25): an Order Block is the last
# opposite-coloured candle immediately before the MSS's displacement leg,
# searched backward from the displacement candle. This ties OB detection
# directly to the setup pipeline already built (WP6) instead of introducing a
# second, unrelated notion of "swing" for OB purposes, and it needs no bar
# past the displacement candle itself to exist -- confirmed_at == mss.index.
#
# Breaker and Mitigation are not separate detectors: they are two outcomes an
# Order Block can reach later, decided by which happens FIRST as price keeps
# moving forward from the OB's confirmation:
#   * touched without a body close through its protective extreme -> MITIGATED
#   * a later candle's body CLOSES through its protective extreme -> BREAKER
#     (the block flips role: a bullish OB that is violated becomes resistance)
# "Body close", not wick, for the violation test -- consistent with how MSS
# itself is defined (a body close through the reference swing), not a new
# convention invented for this module.


@dataclass(frozen=True)
class OrderBlock:
    """The last opposite-coloured candle before an MSS's displacement leg."""

    index: int
    kind: Bias  # BULLISH = acts as support until broken; BEARISH = resistance
    high: float
    low: float
    mss: MSS

    @property
    def confirmed_at(self) -> int:
        """Known once the displacement candle that defines it has closed."""
        return self.mss.index


def find_order_block(
    mss: MSS,
    open_: np.ndarray,
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    max_lookback: int = OB_SEARCH_LOOKBACK,
) -> OrderBlock | None:
    """Search backward from the displacement candle for the nearest opposite-colour candle.

    Returns None if every candle in the lookback window is the same colour as
    the displacement leg -- a real, countable outcome, not an error.
    """
    displacement_bullish = mss.direction is Bias.BULLISH
    lo = max(0, mss.index - max_lookback)
    for i in range(mss.index - 1, lo - 1, -1):
        candle_bullish = close[i] >= open_[i]
        if displacement_bullish and not candle_bullish:
            return OrderBlock(index=i, kind=Bias.BULLISH, high=float(high[i]), low=float(low[i]), mss=mss)
        if not displacement_bullish and candle_bullish:
            return OrderBlock(index=i, kind=Bias.BEARISH, high=float(high[i]), low=float(low[i]), mss=mss)
    return None


@dataclass(frozen=True)
class OrderBlockOutcome:
    """When an order block was first touched and/or violated, within a horizon."""

    order_block: OrderBlock
    first_touch_index: int | None
    violated_index: int | None

    @property
    def status_changes(self) -> list[tuple[int, str]]:
        """[(bar_index, status)], oldest first. Always starts (confirmed_at, "fresh")."""
        events = [(self.order_block.confirmed_at, "fresh")]
        if self.violated_index is not None and (
            self.first_touch_index is None or self.violated_index <= self.first_touch_index
        ):
            events.append((self.violated_index, "breaker"))
        elif self.first_touch_index is not None:
            events.append((self.first_touch_index, "mitigated"))
        return events

    def status_at(self, bar_index: int) -> str:
        """Causal lookup: the status knowable once `bar_index` has closed."""
        status = "fresh"
        for idx, s in self.status_changes:
            if idx <= bar_index:
                status = s
        return status


def evaluate_order_block(
    ob: OrderBlock,
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    horizon: int,
) -> OrderBlockOutcome:
    """Scan forward from `ob`'s confirmation, up to (not including) `horizon`.

    `horizon` bounds how far forward this looks -- callers evaluating a status
    as-of a specific setup's confirmation must pass `horizon <= that bar + 1`
    or risk leaking a later bar into an earlier decision.
    """
    start = ob.confirmed_at + 1
    end = min(horizon, len(close))
    touch_idx: int | None = None
    violate_idx: int | None = None
    for j in range(start, end):
        touched = low[j] <= ob.high and high[j] >= ob.low
        if touch_idx is None and touched:
            touch_idx = j
        violated = close[j] < ob.low if ob.kind is Bias.BULLISH else close[j] > ob.high
        if violate_idx is None and violated:
            violate_idx = j
        if touch_idx is not None and violate_idx is not None:
            break
    return OrderBlockOutcome(order_block=ob, first_touch_index=touch_idx, violated_index=violate_idx)


# ==========================================================================
# Equal Highs / Lows
# ==========================================================================
#
# WP8 Q2 (confirmed 2026-08-25): tolerance is 0.10 x ATR(14), sampled at the
# SECOND swing's own bar (the ATR that existed when the pair actually formed).
# Only ADJACENT confirmed swings of the same kind are compared -- the standard
# "two consecutive swing highs at basically the same level" reading -- not
# every pair, which would double-count long equal-level chains and grow
# combinatorially on a 230k-bar series.


@dataclass(frozen=True)
class EqualLevel:
    kind: SwingType
    first: Swing
    second: Swing
    tolerance: float

    @property
    def confirmed_at(self) -> int:
        """Not knowable until the second swing itself is confirmed."""
        return self.second.confirmed_at


def find_equal_levels(
    swings: SwingSeries,
    atr_values: np.ndarray,
    tolerance_atr_multiple: float = EQH_EQL_ATR_MULTIPLE,
) -> list[EqualLevel]:
    out: list[EqualLevel] = []
    for kind in (SwingType.HIGH, SwingType.LOW):
        same_kind = sorted((s for s in swings.all if s.kind is kind), key=lambda s: s.index)
        for a, b in zip(same_kind, same_kind[1:]):
            atr_at_b = atr_values[b.index] if b.index < len(atr_values) else np.nan
            if not np.isfinite(atr_at_b):
                continue
            tol = tolerance_atr_multiple * float(atr_at_b)
            if abs(a.price - b.price) <= tol:
                out.append(EqualLevel(kind=kind, first=a, second=b, tolerance=tol))
    return out


# ==========================================================================
# Previous Week High / Low
# ==========================================================================
#
# Not put to the user: a direct, mechanical extension of the already-approved
# 17:00-NY trading day. Every trading day belongs to exactly one ISO calendar
# week (the Sunday-evening session already maps to Monday's trading day, so
# the weekend gap never straddles a week boundary), so "week" needs no new
# time-zone or roll-hour decision -- it reuses `trading_day_index` verbatim.
# PWH/PWL is the FULL previous week's high/low, available from the instant
# the current week's first trading day opens.

PWH = "pwh"
PWL = "pwl"


@dataclass(frozen=True)
class WeekLevel:
    pwh: float
    pwl: float
    trading_week: tuple[int, int]  # (iso_year, iso_week)
    available_from: pd.Timestamp
    source_days: int


class WeekLevelBook:
    def __init__(self, table: pd.DataFrame):
        self.table = table

    def for_week(self, week: tuple[int, int]) -> WeekLevel | None:
        if week not in self.table.index:
            return None
        row = self.table.loc[week]
        if pd.isna(row[PWH]):
            return None
        return WeekLevel(
            pwh=float(row[PWH]),
            pwl=float(row[PWL]),
            trading_week=week,
            available_from=row["available_from"],
            source_days=int(row["n_days"]),
        )

    def available_at(self, ts: pd.Timestamp, week: tuple[int, int]) -> WeekLevel | None:
        lvl = self.for_week(week)
        if lvl is None or lvl.available_from > ts:
            return None
        return lvl


def trading_week_of(day: date) -> tuple[int, int]:
    iso = pd.Timestamp(day).isocalendar()
    return (int(iso.year), int(iso.week))


def build_week_levels(m15: pd.DataFrame) -> WeekLevelBook:
    days = trading_day_index(m15.index)
    day_idx = pd.DatetimeIndex(days, name="day")
    per_day = pd.DataFrame(
        {"high": m15["high"].to_numpy(dtype=float), "low": m15["low"].to_numpy(dtype=float)},
        index=day_idx,
    )
    day_agg = per_day.groupby(level=0).agg(day_high=("high", "max"), day_low=("low", "min"))
    day_agg = day_agg.sort_index()

    iso = day_agg.index.isocalendar()
    day_agg["week"] = list(zip(iso["year"].to_numpy(), iso["week"].to_numpy()))

    week_agg = day_agg.groupby("week", sort=True).agg(
        week_high=("day_high", "max"), week_low=("day_low", "min"), n_days=("day_high", "size")
    )
    week_agg = week_agg.sort_index()

    first_day_of_week = day_agg.reset_index().groupby("week")["day"].min().reindex(week_agg.index)

    # `week_agg.index` holds plain (iso_year, iso_week) tuples from the groupby
    # above. A DataFrame with a plain (non-Multi) Index of tuples makes
    # `.loc[(year, week)]` ambiguous -- pandas reads a tuple key as one
    # indexer per axis unless the index is an actual MultiIndex. Build one
    # explicitly so `WeekLevelBook.for_week()` gets an unambiguous full-tuple
    # row lookup.
    weeks = list(week_agg.index)
    table = pd.DataFrame(index=pd.MultiIndex.from_tuples(weeks, names=["iso_year", "iso_week"]))
    table[PWH] = week_agg["week_high"].shift(1).to_numpy()
    table[PWL] = week_agg["week_low"].shift(1).to_numpy()
    table["n_days"] = week_agg["n_days"].shift(1).fillna(0).astype(int).to_numpy()
    table["available_from"] = [trading_day_bounds(d.date())[0] for d in first_day_of_week]
    return WeekLevelBook(table)


# ==========================================================================
# Premium / Discount
# ==========================================================================
#
# WP8 Q3 (confirmed 2026-08-25): the reference range is each setup's OWN two
# already-computed levels -- the level that was swept, and the MSS reference
# swing it broke -- not a new independent range. This adds zero causal risk
# (both prices already exist on the `Setup` by the time it is confirmed).
# ICT convention: the lower half of a range is "discount" (favourable for a
# long), the upper half "premium" (favourable for a short); `favorable` flags
# whether this particular entry landed on its own textbook-favourable side.


@dataclass(frozen=True)
class PremiumDiscount:
    setup: Setup
    range_low: float
    range_high: float
    midpoint: float
    entry_price: float
    zone: str  # "premium" or "discount"
    favorable: bool


def tag_premium_discount(setup: Setup) -> PremiumDiscount:
    a = setup.mss.sweep.level_price
    b = setup.mss.reference_swing.price
    lo, hi = (a, b) if a <= b else (b, a)
    mid = (lo + hi) / 2.0
    price = setup.entry_price
    zone = "premium" if price >= mid else "discount"
    favorable = (zone == "discount") if setup.direction is Bias.BULLISH else (zone == "premium")
    return PremiumDiscount(
        setup=setup, range_low=lo, range_high=hi, midpoint=mid, entry_price=price,
        zone=zone, favorable=favorable,
    )


# ==========================================================================
# Market Regime
# ==========================================================================
#
# WP8 Q4 (confirmed 2026-08-25): two independent, simple, causal axes -- not
# an ML classifier, per the brief's own instruction.
#   * Volatility: ATR(14)'s rolling percentile rank within a trailing window.
#     >= 75th percentile -> high; <= 25th -> low; else normal.
#   * Trend: Kaufman's Efficiency Ratio (net displacement / total path length
#     over a trailing window) -- a standard, decades-old, non-ML measure of
#     how efficiently price moved in one direction -- read as a rolling
#     PERCENTILE of its own trailing distribution, not a fixed textbook
#     cutoff. A fixed 0.6 cutoff was tried first and measured against the
#     development data before being kept: at 15m resolution gold's 480-bar
#     efficiency ratio never once reached 0.6 in 5.8 years (max observed
#     0.30), which would have made "trending" a label that never fires --
#     see `config.REGIME_TREND_PERCENTILE`. Found and corrected before any
#     backtest touched this value, so it carries no overfitting risk.
# Both windows are trailing (pandas `.rolling(window)` at position i uses
# bars [i-window+1, i]), so `regime.volatility[i]` / `regime.trend[i]` never
# see a bar that has not closed yet.


class VolatilityRegime(Enum):
    HIGH = "high_volatility"
    LOW = "low_volatility"
    NORMAL = "normal_volatility"


class TrendRegime(Enum):
    TRENDING = "trending"
    RANGING = "ranging"


@dataclass(frozen=True)
class RegimeSeries:
    volatility: np.ndarray  # dtype=object, VolatilityRegime | None per bar
    trend: np.ndarray  # dtype=object, TrendRegime | None per bar

    def __len__(self) -> int:
        return len(self.volatility)

    def at(self, i: int) -> tuple[VolatilityRegime | None, TrendRegime | None]:
        if i < 0 or i >= len(self.volatility):
            return None, None
        return self.volatility[i], self.trend[i]


def market_regime(
    atr_values: np.ndarray,
    close: np.ndarray,
    percentile_window: int = REGIME_ATR_PERCENTILE_WINDOW,
    trend_window: int = REGIME_TREND_WINDOW,
    high_vol_percentile: float = REGIME_HIGH_VOL_PERCENTILE,
    low_vol_percentile: float = REGIME_LOW_VOL_PERCENTILE,
    trend_percentile: float = REGIME_TREND_PERCENTILE,
) -> RegimeSeries:
    atr_s = pd.Series(np.asarray(atr_values, dtype=float))
    pct_rank = atr_s.rolling(percentile_window, min_periods=percentile_window).rank(pct=True).to_numpy()

    close_s = pd.Series(np.asarray(close, dtype=float))
    diffs = close_s.diff().abs()
    path = diffs.rolling(trend_window, min_periods=trend_window).sum().to_numpy()
    net = (close_s - close_s.shift(trend_window)).abs().to_numpy()
    with np.errstate(divide="ignore", invalid="ignore"):
        er = np.where(path > 0, net / path, np.nan)
    # The efficiency ratio itself is read relative to its OWN trailing
    # history, the same way ATR is -- not against a fixed textbook number.
    er_pct_rank = (
        pd.Series(er).rolling(trend_window, min_periods=trend_window).rank(pct=True).to_numpy()
    )

    n = len(close_s)
    volatility = np.full(n, None, dtype=object)
    trend = np.full(n, None, dtype=object)
    for i in range(n):
        p = pct_rank[i]
        if np.isfinite(p):
            if p >= high_vol_percentile:
                volatility[i] = VolatilityRegime.HIGH
            elif p <= low_vol_percentile:
                volatility[i] = VolatilityRegime.LOW
            else:
                volatility[i] = VolatilityRegime.NORMAL
        ep = er_pct_rank[i]
        if np.isfinite(ep):
            trend[i] = TrendRegime.TRENDING if ep >= trend_percentile else TrendRegime.RANGING
    return RegimeSeries(volatility=volatility, trend=trend)


# ==========================================================================
# Liquidity Cluster
# ==========================================================================
#
# FOUNDING_BRIEF.md gives the mechanics directly: "If PDH/PDL and Asia
# High/Low are near each other: tag as liquidity cluster." and specifies both
# proximity bands to test, <= 0.10 ATR and <= 0.20 ATR, with neither
# automatically weighted higher. All 6 pairs among the day's up-to-4 levels
# are checked (not just PDH-vs-AsiaHigh) since the brief does not restrict
# which pairing counts -- a PDL sitting on top of Asia Low is exactly as much
# a cluster as a PDH sitting on top of Asia High.


@dataclass(frozen=True)
class LiquidityCluster:
    trading_day: date
    level_a: str
    level_b: str
    price_a: float
    price_b: float
    distance: float
    within_tight: bool
    within_wide: bool
    atr_at_reference: float


def find_liquidity_clusters(
    levels: LevelBook,
    m15_index: pd.DatetimeIndex,
    atr_values: np.ndarray,
    tight_multiple: float = LIQUIDITY_CLUSTER_TIGHT_ATR_MULTIPLE,
    wide_multiple: float = LIQUIDITY_CLUSTER_WIDE_ATR_MULTIPLE,
) -> list[LiquidityCluster]:
    close_times = bar_close_index(m15_index, "m15").values
    out: list[LiquidityCluster] = []
    for day_ts, row in levels.table.iterrows():
        d = pd.Timestamp(day_ts).date()
        day_start, _ = trading_day_bounds(d)
        j = int(np.searchsorted(close_times, day_start.to_datetime64(), side="right")) - 1
        if j < 0 or j >= len(atr_values) or not np.isfinite(atr_values[j]):
            continue
        atr_ref = float(atr_values[j])
        present = [(name, row[name]) for name in (PDH, PDL, ASIA_HIGH, ASIA_LOW) if pd.notna(row[name])]
        for k in range(len(present)):
            for m in range(k + 1, len(present)):
                name_a, price_a = present[k]
                name_b, price_b = present[m]
                dist = abs(float(price_a) - float(price_b))
                out.append(
                    LiquidityCluster(
                        trading_day=d, level_a=name_a, level_b=name_b,
                        price_a=float(price_a), price_b=float(price_b), distance=dist,
                        within_tight=dist <= tight_multiple * atr_ref,
                        within_wide=dist <= wide_multiple * atr_ref,
                        atr_at_reference=atr_ref,
                    )
                )
    return out


# ==========================================================================
# Sequential Liquidity Events
# ==========================================================================
#
# FOUNDING_BRIEF.md's own example is same-day ("Asia Low swept first. Later
# PDH/PDL swept.") -- both stay independent candidate setups; only the later
# one gets tagged. Scoped to the trading day already carried on every `Sweep`
# (no new day/session boundary introduced).


@dataclass(frozen=True)
class SequentialTag:
    sweep: Sweep
    is_secondary: bool
    first_sweep_of_day: Sweep | None


def tag_sequential_liquidity_events(sweeps: list[Sweep]) -> dict[tuple[int, str], SequentialTag]:
    by_day: dict[date, list[Sweep]] = {}
    for s in sweeps:
        by_day.setdefault(s.trading_day, []).append(s)

    out: dict[tuple[int, str], SequentialTag] = {}
    for day_sweeps in by_day.values():
        ordered = sorted(day_sweeps, key=lambda s: s.index)
        first = ordered[0]
        for s in ordered:
            is_secondary = s is not first
            out[(s.index, s.level_name)] = SequentialTag(
                sweep=s, is_secondary=is_secondary, first_sweep_of_day=first if is_secondary else None
            )
    return out


# ==========================================================================
# Putting it together: every non-blocking tag attached to one setup
# ==========================================================================


@dataclass(frozen=True)
class SetupTags:
    setup: Setup
    order_block: OrderBlock | None
    order_block_status: str | None  # "fresh" / "mitigated" / "breaker", as of setup.confirmed_at
    premium_discount: PremiumDiscount
    volatility_regime: VolatilityRegime | None
    trend_regime: TrendRegime | None
    is_secondary_liquidity_event: bool
    liquidity_cluster_tight: bool
    liquidity_cluster_wide: bool


def tag_setup(
    setup: Setup,
    open_: np.ndarray,
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    regime: RegimeSeries,
    sequential: dict[tuple[int, str], SequentialTag],
    clusters_by_day: dict[date, list[LiquidityCluster]],
) -> SetupTags:
    """Attach every WP8 tag to a single confirmed setup, causally as-of its own confirmation.

    Nothing here is used by the backtester -- this exists purely for reporting
    and for WP10's later ablation slicing.
    """
    ob = find_order_block(setup.mss, open_, high, low, close)
    ob_status = None
    if ob is not None:
        outcome = evaluate_order_block(ob, high, low, close, horizon=setup.confirmed_at + 1)
        ob_status = outcome.status_at(setup.confirmed_at)

    pd_tag = tag_premium_discount(setup)

    i = setup.confirmed_at
    volatility, trend = regime.at(i)

    key = (setup.mss.sweep.index, setup.mss.sweep.level_name)
    seq = sequential.get(key)
    is_secondary = bool(seq and seq.is_secondary)

    day_clusters = clusters_by_day.get(setup.mss.sweep.trading_day, [])
    tight = any(c.within_tight for c in day_clusters)
    wide = any(c.within_wide for c in day_clusters)

    return SetupTags(
        setup=setup,
        order_block=ob,
        order_block_status=ob_status,
        premium_discount=pd_tag,
        volatility_regime=volatility,
        trend_regime=trend,
        is_secondary_liquidity_event=is_secondary,
        liquidity_cluster_tight=tight,
        liquidity_cluster_wide=wide,
    )


def clusters_by_trading_day(clusters: list[LiquidityCluster]) -> dict[date, list[LiquidityCluster]]:
    out: dict[date, list[LiquidityCluster]] = {}
    for c in clusters:
        out.setdefault(c.trading_day, []).append(c)
    return out
