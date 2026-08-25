"""Work Package 7: measure what transaction costs actually do, and write
COST_MODEL_REPORT.md.

Two things are established here, both from measurement rather than assumption:

1. **The price series is a BID series.** Checked against the user's Dukascopy
   reference files, which state their side explicitly. This decides which leg of
   a round trip pays the spread — get it backwards and the cost either doubles
   or vanishes, with nothing in a summary statistic to reveal which.

2. **How large the baseline's stops really are**, and therefore what a given
   spread costs as a share of one R. This is where the co-primary stop-loss
   amendment came from.

No strategy profit or loss figure appears here. Development period only.

Run: python3 scripts/run_cost_model_report.py
"""

from __future__ import annotations

import glob
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from xauusd_research.config import (  # noqa: E402
    BASELINE_SL_BUFFER_ATR_MULTIPLE,
    BASELINE_SWING_N,
    BASELINE_TARGET_RR,
)
from xauusd_research.data.loaders import load_raw_ejtrader  # noqa: E402
from xauusd_research.engine.clock import bar_close_index  # noqa: E402
from xauusd_research.engine.costs import COST_PROFILES, stressed  # noqa: E402
from xauusd_research.engine.orders import ExitReason  # noqa: E402
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

REPO_ROOT = Path(__file__).resolve().parents[1]
DEV_END = pd.Timestamp("2018-03-04", tz="UTC")


def measure_side() -> list[tuple[str, str, int, float, float]]:
    """Compare our series against every Dukascopy file whose side is labelled."""
    gh = load_raw_ejtrader("h1")
    out = []
    for path in sorted(glob.glob(str(REPO_ROOT / "data/raw/XAU-USD_1Hour_*.csv"))):
        side = "ASK" if "_ASK_" in path else "BID"
        d = pd.read_csv(path).rename(columns=lambda x: x.strip())
        d = d.rename(columns={d.columns[0]: "ts"})
        d["ts"] = pd.to_datetime(d["ts"], utc=True)
        d = d.set_index("ts").sort_index()
        d.columns = [c.lower() for c in d.columns]
        d = d[~d.index.duplicated()]
        common = gh.index.intersection(d.index)
        if len(common) < 50:
            continue
        diff = gh.loc[common, "close"].astype(float) - d.loc[common, "close"].astype(float)
        out.append((Path(path).name, side, len(common), float(diff.mean()), float(diff.median())))
    return out


def hourly_spread_profile() -> pd.Series | None:
    """Implied spread by UTC hour, from the one month where we hold the ASK side."""
    gh = load_raw_ejtrader("h1")
    ask_files = glob.glob(str(REPO_ROOT / "data/raw/XAU-USD_1Hour_ASK_*.csv"))
    if not ask_files:
        return None
    d = pd.read_csv(ask_files[0]).rename(columns=lambda x: x.strip())
    d = d.rename(columns={d.columns[0]: "ts"})
    d["ts"] = pd.to_datetime(d["ts"], utc=True)
    d = d.set_index("ts").sort_index()
    d.columns = [c.lower() for c in d.columns]
    common = gh.index.intersection(d.index)
    spread = d.loc[common, "close"].astype(float) - gh.loc[common, "close"].astype(float)
    return spread


def build_setup_risks() -> pd.DataFrame:
    """Stop distance under each SL variant, for every tradeable baseline setup."""
    m15 = pd.read_parquet(REPO_ROOT / "data" / "processed" / "XAUUSD_m15.parquet")
    dev = m15[m15.index < DEV_END]
    o, h, l, c = (dev[x].to_numpy(dtype=float) for x in ("open", "high", "low", "close"))
    close_times = bar_close_index(dev.index, "m15")

    def track(series):
        sw = find_swings(
            series.df["high"].to_numpy(float), series.df["low"].to_numpy(float),
            BASELINE_SWING_N,
        )
        n_closed = np.searchsorted(series.close_time.values, close_times.values, side="right")
        return project_to_base(bias_by_bar(sw, len(series)), n_closed)

    gate = [
        htf_gate_flexible(a, b) for a, b in zip(track(build_d1_ny(dev)), track(build_h4_ny(dev)))
    ]
    sweeps = find_sweeps(dev, build_levels(dev), build_session_map(dev.index))
    mss, _ = find_mss(sweeps, find_swings(h, l, BASELINE_SWING_N), o, c, displacement_ratio(o, c))
    setups, _ = build_setups(mss, h, l)
    kept = [s for s in setups if gate[s.confirmed_at] is s.direction]

    a14 = atr(h, l, c)
    rows = []
    for s in kept:
        buf = BASELINE_SL_BUFFER_ATR_MULTIPLE * a14[s.confirmed_at]
        if not np.isfinite(buf):
            continue
        sign = 1 if s.direction is Bias.BULLISH else -1
        rows.append(
            {
                "direction": s.direction.name,
                "risk_a": sign * (s.entry_price - (s.invalidation_extreme - sign * buf)),
                "risk_b": sign * (s.entry_price - (s.invalidation_swing - sign * buf)),
                "fvg_size": s.fvg.size,
                "atr": a14[s.confirmed_at],
            }
        )
    return pd.DataFrame(rows)


def breakeven_win_rate(model, risk: float) -> float:
    """Win rate a fixed 1:2 system needs just to break even after costs."""
    cw = model.cost_in_r(risk, ExitReason.TAKE_PROFIT)
    cl = model.cost_in_r(risk, ExitReason.STOP_LOSS)
    rr = BASELINE_TARGET_RR
    return (1 + cl) / (rr + 1 + cl - cw)


def main() -> None:
    sides = measure_side()
    spread = hourly_spread_profile()
    d = build_setup_risks()
    print(f"setups measured: {len(d)}")

    L: list[str] = []
    add = L.append
    add("# COST_MODEL_REPORT")
    add("")
    add("Generated by `scripts/run_cost_model_report.py` — Work Package 7.")
    add("")
    add("**No strategy profit or loss figure appears in this report.** It establishes")
    add("which side of the market our prices sit on, what a round trip costs, and how")
    add("that compares with the size of the stops the baseline actually produces.")
    add("")

    add("## 1. The series is a BID series (measured)")
    add("")
    add("The source does not say which side it quotes. The user's Dukascopy reference")
    add("files do, so the question is settled by comparison rather than assumption:")
    add("")
    add("| Reference file | Side | Bars | Mean (ours − reference) | Median |")
    add("|---|---|---|---|---|")
    for name, side, n, mean, median in sides:
        add(f"| `{name[:46]}` | {side} | {n} | {mean:+.4f} | {median:+.4f} |")
    add("")
    add("Our prices sit ~$0.42 below the ask and within a few cents of the bid. They")
    add("are bid quotes.")
    add("")
    add("**Why this decides the cost model.** Every level in this project — entries,")
    add("stops, targets, PDH/PDL, Asia high/low — is derived from this series and is")
    add("therefore in bid terms. So:")
    add("")
    add("| Leg | Transacts at | Pays spread? |")
    add("|---|---|---|")
    add("| Long entry (buy) | ask | **yes** |")
    add("| Long exit (sell) | bid | no |")
    add("| Short entry (sell) | bid | no |")
    add("| Short exit (buy) | ask | **yes** |")
    add("")
    add("Exactly one leg of every round trip pays the spread — never two, never none.")
    add("Assuming both legs pay would double the cost; assuming neither would delete")
    add("it, and no summary statistic would show which mistake had been made.")
    add("")

    if spread is not None and len(spread):
        add("## 2. What the spread actually was")
        add("")
        add(
            f"From the one month where we hold the ask side ({len(spread)} hourly bars, "
            "January 2013):"
        )
        add("")
        add(
            f"median **${spread.median():.3f}/oz** · mean ${spread.mean():.3f} · "
            f"25th pct ${spread.quantile(.25):.3f} · 75th pct ${spread.quantile(.75):.3f} · "
            f"95th pct ${spread.quantile(.95):.3f}"
        )
        add("")
        lon = spread[(spread.index.hour >= 7) & (spread.index.hour < 10)]
        ny = spread[(spread.index.hour >= 13) & (spread.index.hour < 16)]
        add(
            f"London window (07–10 UTC) median ${lon.median():.3f} · "
            f"New York window (13–16 UTC) median ${ny.median():.3f}."
        )
        add("")
        add("Worth noting: our trading hours are **not** cheaper than the rest of the day.")
        add("A common assumption is that kill-zone hours bring tighter spreads; in this")
        add("sample they did not.")
        add("")
        add("This is 2013 and an ECN-style broker — a wide-spread era for gold. It is")
        add("kept as its own labelled scenario rather than used as the baseline.")
        add("")

    add("## 3. Cost profiles")
    add("")
    add("Labelled assumptions confirmed by the user 2026-08-25. The data source has no")
    add("bid/ask for the backtest period, so no spread can be measured from it.")
    add("FOUNDING_BRIEF.md: *\"Do not pretend estimated costs are actual broker facts.\"*")
    add("")
    add("| Profile | Spread | Commission | Slippage | Round trip @ target | @ stop |")
    add("|---|---|---|---|---|---|")
    for p in COST_PROFILES:
        for m in (p, stressed(p)):
            add(
                f"| `{m.name}` | ${m.spread:.2f} | ${m.commission:.2f} | ${m.slippage:.2f} | "
                f"${m.round_trip_cost(ExitReason.TAKE_PROFIT):.2f} | "
                f"${m.round_trip_cost(ExitReason.STOP_LOSS):.2f} |"
            )
    add("")
    add("Slippage applies only to stops and forced closes, which execute at market. A")
    add("limit order fills at its price or not at all, so take-profits and limit")
    add("entries carry none. Slippage is always adverse.")
    add("")

    add("## 4. How big are the stops? (the finding that changed the baseline)")
    add("")
    add(f"Measured across the {len(d)} tradeable baseline setups from Work Package 6:")
    add("")
    add("| | SL Variant A (sweep wick) | SL Variant B (broken swing) |")
    add("|---|---|---|")
    va, vb = d["risk_a"], d["risk_b"]
    pa, pb = va[va > 0], vb[vb > 0]
    add(f"| Setups producing a valid order | **{len(pa)} / {len(d)}** | {len(pb)} / {len(d)} |")
    add(f"| Median stop | ${pa.median():.2f} | ${pb.median():.2f} |")
    add(f"| 10th percentile | ${pa.quantile(.1):.2f} | ${pb.quantile(.1):.2f} |")
    add(f"| 90th percentile | ${pa.quantile(.9):.2f} | ${pb.quantile(.9):.2f} |")
    add(f"| Stops under $0.50 | {(pa < 0.5).mean():.0%} | {(pb < 0.5).mean():.0%} |")
    add("")
    add(
        f"For scale: the median FVG is ${d['fvg_size'].median():.2f} wide and median "
        f"ATR(14) on the 15m series is ${d['atr'].median():.2f}."
    )
    add("")
    add("**Why Variant B collapses.** The eligible FVG is created by the very")
    add("displacement candle that broke the reference swing, so the gap sits directly")
    add("on top of that swing. The entry — the gap's near edge — often lands almost")
    add("exactly on the stop, and in 24% of cases beyond it, which cannot be executed")
    add("at all. This is a mechanical consequence of combining two pre-registered rules,")
    add("and carries no information about whether the strategy is profitable.")
    add("")

    add("## 5. Cost as a share of one R")
    add("")
    add("This is the number that matters. A spread is not expensive or cheap in the")
    add("abstract — only relative to the risk being taken.")
    add("")
    add("| Profile | @ Variant A median stop | @ Variant B median stop |")
    add("|---|---|---|")
    ma, mb = float(pa.median()), float(pb.median())
    for p in COST_PROFILES:
        for m in (p, stressed(p)):
            add(
                f"| `{m.name}` | {m.cost_in_r(ma, ExitReason.STOP_LOSS):.1%} | "
                f"{m.cost_in_r(mb, ExitReason.STOP_LOSS):.1%} |"
            )
    add("")
    add("And the same thing expressed as the hurdle a fixed 1:2 system has to clear —")
    add("the win rate required merely to break even, against **33.3%** with no costs:")
    add("")
    add("| Profile | Variant A | Variant B |")
    add("|---|---|---|")
    for p in COST_PROFILES[:2]:
        for m in (p, stressed(p)):
            add(
                f"| `{m.name}` | {breakeven_win_rate(m, ma):.1%} | "
                f"{breakeven_win_rate(m, mb):.1%} |"
            )
    add("")
    add("Under Variant B a 1:2 system must win roughly half its trades just to stand")
    add("still. A test set up that way would almost certainly return \"no edge\" — but")
    add("the result would be uninformative, because it could not distinguish a weak")
    add("signal from a stop that was simply too tight to survive the spread.")
    add("")
    add("Both variants are therefore now co-primary baselines, declared before any")
    add("backtest, run together and reported together. See the WP7 amendment in")
    add("`PREREGISTRATION.md`.")
    add("")

    add("## 6. What is deliberately not built")
    add("")
    add("| Planned comparison | Status | Why |")
    add("|---|---|---|")
    add(
        "| Abnormal-spread filter (spread variant B) | **not implemented** | Needs a "
        "spread that varies bar by bar. We have one assumed constant, so the filter "
        "would compare a number against itself. |"
    )
    add(
        "| News-period blackout and news slippage | **not implemented** | Needs "
        "point-in-time economic-event timestamps, which this sandbox cannot reach. The "
        "brief: *\"If trustworthy point-in-time data cannot be obtained for a particular "
        "field: DO NOT fabricate it.\"* |"
    )
    add("")
    add("Both must be restated as gaps in the WP15 final report rather than quietly")
    add("dropped from the list of planned comparisons.")
    add("")

    add("## 7. Verdict")
    add("")
    add("The cost model is measured where measurement was possible (which side the")
    add("series quotes, and what the spread was in the one month we can check) and")
    add("clearly labelled as assumption everywhere else. It is ready for Work Package 8.")
    add("")
    add("**Carried forward:** with a $0.30 spread, Variant A costs ~10% of R per trade")
    add("and Variant B ~49%. Costs are not a rounding error for this strategy; at the")
    add("tighter stop they are the dominant term.")

    (REPO_ROOT / "COST_MODEL_REPORT.md").write_text("\n".join(L) + "\n")
    print(f"Report written to {REPO_ROOT / 'COST_MODEL_REPORT.md'}")


if __name__ == "__main__":
    main()
