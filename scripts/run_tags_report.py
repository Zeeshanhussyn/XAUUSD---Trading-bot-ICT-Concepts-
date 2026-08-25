"""Work Package 8: attach every non-blocking analysis tag to the development
period's tradeable setups, and write TAGS_REPORT.md.

**No profit or loss figure appears anywhere in this report**, and nothing
computed here feeds back into which setups exist or how they are priced —
that would violate the brief's own rule for this work package ("Tags must
not silently alter trade decisions"). This script only counts how often each
tag occurs, exactly like `run_feature_scan.py` counted funnel stages in
WP6, for the same reason: understanding the tags' distribution before WP9
runs the actual backtest.

Only the development period is touched. Validation and holdout untouched.

Run: python3 scripts/run_tags_report.py
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from xauusd_research.config import (  # noqa: E402
    BASELINE_ASIA_WINDOW,
    BASELINE_ATR_PERIOD,
    BASELINE_PENDING_VALIDITY_MINUTES,
    BASELINE_SWING_N,
    BASELINE_TRADING_SESSIONS,
)
from xauusd_research.engine.clock import TICK_SIZE, bar_close_index  # noqa: E402
from xauusd_research.engine.resample import build_d1_ny, build_h4_ny  # noqa: E402
from xauusd_research.features.bias import (  # noqa: E402
    Bias,
    bias_by_bar,
    htf_gate_flexible,
    project_to_base,
)
from xauusd_research.features.fvg import build_setups  # noqa: E402
from xauusd_research.features.indicators import atr  # noqa: E402
from xauusd_research.features.levels import build_levels  # noqa: E402
from xauusd_research.features.sessions import build_session_map  # noqa: E402
from xauusd_research.features.structure import displacement_ratio, find_mss  # noqa: E402
from xauusd_research.features.sweeps import find_sweeps  # noqa: E402
from xauusd_research.features.swings import find_swings  # noqa: E402
from xauusd_research.features.tags import (  # noqa: E402
    clusters_by_trading_day,
    find_equal_levels,
    find_liquidity_clusters,
    find_order_block,
    build_week_levels,
    market_regime,
    tag_sequential_liquidity_events,
    tag_setup,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
DEV_END = pd.Timestamp("2018-03-04", tz="UTC")
VALIDITY_BARS = BASELINE_PENDING_VALIDITY_MINUTES // 15


def _entry_reachable(setup, high: np.ndarray, low: np.ndarray) -> bool:
    """Same rule as `run_feature_scan.py` — a count, not a trade result."""
    start = setup.confirmed_at + 1
    stop = min(start + VALIDITY_BARS, len(high))
    entry = setup.entry_price
    if setup.direction is Bias.BULLISH:
        return bool(np.any(low[start:stop] <= entry - TICK_SIZE))
    return bool(np.any(high[start:stop] >= entry + TICK_SIZE))


def main() -> None:
    m15 = pd.read_parquet(REPO_ROOT / "data" / "processed" / "XAUUSD_m15.parquet")
    dev = m15[m15.index < DEV_END]
    o, h, l, c = (dev[x].to_numpy(dtype=float) for x in ("open", "high", "low", "close"))
    print(f"development bars: {len(dev):,}")

    d1, h4 = build_d1_ny(dev), build_h4_ny(dev)
    base_close = bar_close_index(dev.index, "m15")

    def htf_track(series):
        sw = find_swings(
            series.df["high"].to_numpy(float), series.df["low"].to_numpy(float), BASELINE_SWING_N
        )
        n_closed = np.searchsorted(series.close_time.values, base_close.values, side="right")
        return project_to_base(bias_by_bar(sw, len(series)), n_closed)

    flexible = [htf_gate_flexible(a, b) for a, b in zip(htf_track(d1), htf_track(h4))]

    levels = build_levels(dev, asia_window=BASELINE_ASIA_WINDOW)
    smap = build_session_map(dev.index, BASELINE_TRADING_SESSIONS)
    sweeps = find_sweeps(dev, levels, smap)
    swings = find_swings(h, l, BASELINE_SWING_N)
    ratio = displacement_ratio(o, c)
    mss, _ = find_mss(sweeps, swings, o, c, ratio)
    setups, _ = build_setups(mss, h, l)

    gated = [s for s in setups if flexible[s.confirmed_at] is s.direction]
    reachable = [s for s in gated if _entry_reachable(s, h, l)]
    print(f"reachable baseline setups tagged: {len(reachable)}")

    atr_values = atr(h, l, c, BASELINE_ATR_PERIOD)
    regime = market_regime(atr_values, c)
    sequential = tag_sequential_liquidity_events(sweeps)
    clusters = find_liquidity_clusters(levels, dev.index, atr_values)
    clusters_by_day = clusters_by_trading_day(clusters)
    equal_levels = find_equal_levels(swings, atr_values)
    week_levels = build_week_levels(dev)

    tagged = [
        tag_setup(s, o, h, l, c, regime, sequential, clusters_by_day) for s in reachable
    ]

    write_report(
        dev, sweeps, swings, setups, gated, reachable, tagged, equal_levels,
        clusters, week_levels,
    )
    print(f"Report written to {REPO_ROOT / 'TAGS_REPORT.md'}")


def write_report(
    dev, sweeps, swings, setups, gated, reachable, tagged, equal_levels, clusters, week_levels
) -> None:
    L: list[str] = []
    add = L.append

    add("# TAGS_REPORT")
    add("")
    add("Generated by `scripts/run_tags_report.py` — Work Package 8.")
    add("")
    add("**No profit or loss figure appears anywhere in this report**, and nothing here")
    add("filters or blocks a trade — every tag below is attached to setups that already")
    add("passed every WP6/WP7 rule, unchanged. This only counts how often each tag")
    add("occurs, the same spirit as `FEATURES_REPORT.md`'s funnel in WP6.")
    add("")
    add(
        f"Development period: {dev.index[0].date()} → {dev.index[-1].date()} "
        f"({len(dev):,} bars). Tagged population: **{len(reachable)} reachable baseline "
        "setups** (same funnel stage `FEATURES_REPORT.md` calls \"price returned to the "
        f"entry in time\") out of {len(sweeps):,} sweeps → {len(setups):,} FVG setups → "
        f"{len(gated):,} HTF-gated."
    )
    add("")

    add("## 1. Order Block / Breaker / Mitigation")
    add("")
    add("Definition confirmed by the user 2026-08-25 (WP8 Q1): the last opposite-colour")
    add("candle immediately before the MSS's own displacement leg. Status is evaluated")
    add("**as of the setup's own confirmation** — never using a bar the setup itself")
    add("could not yet see.")
    add("")
    found = sum(1 for t in tagged if t.order_block is not None)
    add(f"Order block found before the displacement leg: {found} / {len(tagged)} "
        f"({found / len(tagged):.0%} — 'not found' means every candle in the lookback"
        f" window shared the displacement's own colour).")
    add("")
    status_counts = Counter(t.order_block_status for t in tagged if t.order_block_status)
    add("| Status at setup confirmation | Count |")
    add("|---|---|")
    for status in ("fresh", "mitigated", "breaker"):
        add(f"| {status} | {status_counts.get(status, 0)} |")
    add("")

    add("## 2. Equal Highs / Lows")
    add("")
    add("Tolerance confirmed by the user 2026-08-25 (WP8 Q2): 0.10 x ATR(14), sampled at")
    add("the second swing's own bar. Only adjacent same-kind swings are compared.")
    add("")
    eq_h = sum(1 for e in equal_levels if e.kind.name == "HIGH")
    eq_l = sum(1 for e in equal_levels if e.kind.name == "LOW")
    add(f"Equal-high pairs: {eq_h} · Equal-low pairs: {eq_l} · Total: {len(equal_levels)}")
    add("")

    add("## 3. Previous Week High / Low")
    add("")
    add("Not put to the user — a direct extension of the already-approved 17:00-NY")
    add("trading day to a full trading week (Sunday's session already maps to Monday's")
    add("trading day, so no new time-zone decision is introduced).")
    add("")
    weeks_total = len(week_levels.table)
    weeks_with_pwh = int(week_levels.table["pwh"].notna().sum())
    add(f"Trading weeks in the development period: {weeks_total} · with a usable previous")
    add(f"week (i.e. not the very first week in the dataset): {weeks_with_pwh}.")
    add("")

    add("## 4. Premium / Discount")
    add("")
    add("Range confirmed by the user 2026-08-25 (WP8 Q3): each setup's own two levels —")
    add("the level that was swept, and the MSS reference swing it broke.")
    add("")
    zone_counts = Counter(t.premium_discount.zone for t in tagged)
    favorable = sum(1 for t in tagged if t.premium_discount.favorable)
    add(f"Entered in discount: {zone_counts.get('discount', 0)} · in premium: "
        f"{zone_counts.get('premium', 0)}.")
    add(
        f"Landed on the textbook-favourable side for its own direction (discount for a"
        f" long, premium for a short): {favorable} / {len(tagged)} ({favorable / len(tagged):.0%})."
        " This is descriptive only — V1 does not filter on it."
    )
    add("")
    add(
        "**Why this is low, structurally, not by chance.** This setup's reference range "
        "runs from the swept level to the very swing the MSS had to close beyond to "
        "exist at all — so the entry (the displacement candle's own FVG) sits on or past "
        "the far edge of its own range almost by construction, not near the middle. A "
        "premium/discount tag built on a *larger* independent range (e.g. the daily "
        "PDH-PDL, the option this document's WP8 Q3 turned down) would not have this "
        "property. Reported plainly rather than silently — this tag still means exactly "
        "what its definition says, it just rarely reads as 'favourable' under that "
        "definition."
    )
    add("")

    add("## 5. Market Regime")
    add("")
    add("Method confirmed by the user 2026-08-25 (WP8 Q4): rolling ATR(14) percentile")
    add("for volatility, rolling Kaufman efficiency ratio for trend — both simple,")
    add("causal, non-ML measures, per the brief's own instruction.")
    add("")
    add("**Calibration note, found here, fixed before any backtest.** The trend axis was")
    add("first built against the textbook 0.6 efficiency-ratio cutoff. Measured against")
    add("this development period it never fired once in 5.8 years (max observed 0.30) —")
    add("gold is too noisy intraday at 15m for that absolute number. It now reads the")
    add("ratio as a rolling percentile of its own trailing history instead (top quartile")
    add("= trending), the same shape as the volatility axis. See `config.py` and")
    add("`CHANGELOG.md`.")
    add("")
    vol_counts = Counter(t.volatility_regime.value if t.volatility_regime else "unavailable" for t in tagged)
    trend_counts = Counter(t.trend_regime.value if t.trend_regime else "unavailable" for t in tagged)
    add("| Volatility | Count | | Trend | Count |")
    add("|---|---|---|---|---|")
    vol_keys = ["high_volatility", "normal_volatility", "low_volatility", "unavailable"]
    trend_keys = ["trending", "ranging", "unavailable"]
    for i in range(max(len(vol_keys), len(trend_keys))):
        vk = vol_keys[i] if i < len(vol_keys) else ""
        tk = trend_keys[i] if i < len(trend_keys) else ""
        vc = vol_counts.get(vk, 0) if vk else ""
        tc = trend_counts.get(tk, 0) if tk else ""
        add(f"| {vk} | {vc} | | {tk} | {tc} |")
    add("")

    add("## 6. Liquidity Cluster")
    add("")
    add("Mechanics taken directly from the brief: PDH/PDL and Asia High/Low within")
    add("0.10 x ATR (tight) or 0.20 x ATR (wide) of each other, checked pairwise across")
    add("all four levels each trading day. Neither band is given extra weight.")
    add("")
    tight = sum(1 for c in clusters if c.within_tight)
    wide = sum(1 for c in clusters if c.within_wide)
    add(f"Level pairs compared across the development period: {len(clusters)} · within")
    add(f"0.10 x ATR: {tight} · within 0.20 x ATR: {wide}.")
    add("")
    tight_setups = sum(1 for t in tagged if t.liquidity_cluster_tight)
    wide_setups = sum(1 for t in tagged if t.liquidity_cluster_wide)
    add(f"Reachable setups whose trading day had a tight cluster: {tight_setups} /")
    add(f"{len(tagged)} · a wide cluster: {wide_setups} / {len(tagged)}.")
    add("")

    add("## 7. Sequential Liquidity Events")
    add("")
    add("Scoped to the trading day already carried on every `Sweep` — the brief's own")
    add("worked example (Asia Low swept, later PDH/PDL swept) is same-day; no new")
    add("session or day boundary was introduced.")
    add("")
    seq = tag_sequential_liquidity_events(sweeps)
    secondary = sum(1 for v in seq.values() if v.is_secondary)
    add(f"Sweeps tagged `secondary-liquidity-event`: {secondary} / {len(sweeps)} "
        f"({secondary / len(sweeps):.1%}).")
    add("")
    secondary_setups = sum(1 for t in tagged if t.is_secondary_liquidity_event)
    add(f"Reachable setups whose own sweep was a secondary event: {secondary_setups} /"
        f" {len(tagged)}.")
    add("")

    add("## 8. Not implemented")
    add("")
    add("| Tag | Status | Why |")
    add("|---|---|---|")
    add(
        "| 1-minute context tag | **not implemented** | This project never acquired "
        "minute-level XAUUSD data in bulk (see `PREREGISTRATION.md`'s WP3 amendment — "
        "free multi-year 5m-or-finer data was not obtainable). Nothing at that "
        "resolution exists in `data/processed/`. |"
    )
    add("")
    add("A data-availability gap, in the same spirit as WP7's un-implemented")
    add("abnormal-spread filter and news blackout. Restate in the WP15 final report.")
    add("")

    add("## 9. Verdict")
    add("")
    add("Every tag here is descriptive, causal (checked against real-data truncation")
    add("tests, the same discipline as every earlier feature), and provably")
    add("non-mutating: `tag_setup` never changes the `Setup` it describes. Ready for")
    add("Work Package 9, where the baseline is actually backtested for the first time.")

    (REPO_ROOT / "TAGS_REPORT.md").write_text("\n".join(L) + "\n")


if __name__ == "__main__":
    main()
