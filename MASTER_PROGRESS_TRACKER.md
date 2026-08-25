# XAUUSD ICT/SMC Research Prototype — Master Progress Tracker

(Local copy — canonical cross-session copy also lives in the "New Venture" Claude project.)

## Project in one line
Lean Python research prototype to test, with strict no-lookahead backtesting, whether a specific
XAUUSD ICT/SMC setup (PDH/PDL or Asia H/L liquidity sweep → HTF bias → 15m MSS/CHOCH →
displacement → FVG retracement entry) contains repeatable statistical edge after realistic
execution costs. Falsification-oriented — a negative result is a valid outcome. No live trading,
no MQL5, no product/dashboard in Phase 1.

## Work package status
| WP | Name | Status |
|----|------|--------|
| 0 | Environment Audit | Done |
| 1 | Project Scaffold | Done |
| 2 | Research Design / Preregistration | Done — approved 2026-08-24, amended 2026-08-25 (x2) |
| 3 | Data Acquisition | Done — GitHub source, 2012-2022, 15m base timeframe, data split confirmed |
| 4 | Data Integrity | Done — EET/EEST timezone finding, 5 timeframes clean |
| 5 | Backtest Engine | **Done** — see below |
| 6 | Core Features | **Done** — see below |
| 7 | Execution/Cost Model | Not started |
| 8 | Analysis Tags | Not started |
| 9 | Baseline Development Backtest | Not started |
| 10 | Staged Ablation | Not started |
| 11 | Random Benchmark + Robustness | Not started |
| 12 | Walk-Forward | Not started |
| 13 | Pre-Holdout Decision | Not started |
| 14 | Untouched Holdout (Phase-1 gate) | Not started — requires explicit user approval |
| 15 | Phase 1 Final Report | Not started |

## Work Package 4 result (2026-08-25)
**Critical finding:** raw GitHub timestamps are EET/EEST broker time (UTC+2 winter / UTC+3
summer), NOT UTC. Determined empirically by correlating against user-downloaded Dukascopy
UTC-labeled reference data for both a winter and summer month (corr 0.9998+ both times).
Implemented as proper DST-aware conversion (`Europe/Bucharest` zoneinfo). Zero duplicate
timestamps, bad OHLC rows, non-positive prices, or nulls found across all 5 timeframes.
Cleaned Parquet saved to `data/processed/` (regenerable, gitignored). 7 unit tests passing.
Full detail in `DATA_INTEGRITY_REPORT.md`. **Verdict: proceed to WP5.**

## Work Package 5 result (2026-08-25)
**Critical finding:** bar timestamps are **open times**, not close times (2992/2992 h1 bars
matched forward aggregation of m15, 0/2992 matched backward). Reading them the other way
would have given every decision in the project a silent 15-minute lookahead.

**Second cross-check of WP4:** daily bars rebuilt from m15 on the 17:00-NY boundary match the
broker's own daily bars to **0.0000** across OHLC on all 2242 days where the two definitions
coincide — validating the EET/EEST conversion, price scaling, m15 series and aggregation at
once.

Built `src/xauusd_research/engine/` (clock, resample, marketview, orders, costs interface,
backtester). Four engine decisions confirmed with the user before coding: HTF bars built both
ways and compared in ablation; conservative gap fills; positions held to stop/target with no
time limit; equity fixed on initial capital. Rules documented in `ENGINE_SPEC.md` before any
strategy exists.

**83 new tests (90 total, all passing)**, including lookahead traps and end-to-end scenarios
with arithmetically known answers. Engine runs 230,400 bars in ~3.7s.

**Strongest evidence:** information-free 1:2 entries over the development period return a
0.3211 / 0.3335 win rate against a theoretical breakeven of 1/3, with zero wins above the
planned target and real gap losses down to −4.91R. The engine manufactures no edge, never
credits gap improvement, and always takes gap damage. **Verdict: proceed to WP6.**

**Preregistration amended (2026-08-25, pre-backtest):** pending-order validity 25 → **50
minutes**. The engine's whole-bar validity rule had made 25 minutes work out to exactly one
15m bar, against the "≈1-2 candles" the document described. User chose to lengthen the
validity rather than weaken the fill rule. 25-minute and current-session-only remain WP10
ablations. Baseline parameters now live in `src/xauusd_research/config.py`.

## Work Package 6 result (2026-08-25)
Recovered the original 37,443-character master prompt from the session transcript and stored it
verbatim as `FOUNDING_BRIEF.md` — it had existed only inside a chat session, and a compacted
summary is not the source text.

**Preregistration amended (pre-backtest):** the brief uses four terms it never defines
operationally. Each was put to the user as an A/B/C choice and answered: Daily bias "clear" =
swing structure HH+HL / LH+LL (neutral blocks); MSS reference swing fixed at the sweep; a sweep
stays live only until the end of its own session; only the MSS displacement candle's own FVG is
eligible. Every alternative remains a WP10 ablation.

Built `src/xauusd_research/features/` — swings (fractal N=2 carrying an explicit `confirmed_at`
lag), levels (PDH/PDL and Asia H/L with per-level availability instants), bias, sessions,
sweeps, structure (displacement + MSS), fvg. 73 new tests (163 total, all passing), including a
truncation test that recomputes the entire chain on a shortened series and demands identical
results.

**Major finding — sample size.** The baseline funnel over 5.8 development years:
5,980 sweeps -> 959 MSS -> 638 FVG setups -> 149 past the HTF gate -> **88 where price actually
returned to the entry in time** (~15/year). Extrapolated across development plus validation
that is ~118 trades, against the 400+ floor in PREREGISTRATION.md §5.

Reported, **not fixed** — the brief says "Never force extra trades merely to increase sample",
so loosening a rule after seeing the count is the user's decision to take knowingly. Awaiting
that decision. Biggest filter: 4,147 of 5,980 sweeps expire before an MSS, because the median
sweep completes with only 5 bars left in a 12-bar session. Displacement itself is not scarce
(34% of session bars qualify).

**Verdict: feature layer ready for WP7; sample-size risk carried forward.**

## Infrastructure status
- Cloud research sandbox: Python 3.11.15, Git 2.43.0, pandas/numpy/scipy/matplotlib/pytest/pyarrow installed.
- Local persistent folder: connected — `C:\Users\AK\Desktop\XAUUSD_Research` on user's Windows PC, kept in sync after every checkpoint.
- GitHub: connected — `Zeeshanhussyn/XAUUSD---Trading-bot-ICT-Concepts-` (private), `main` branch, verified remote HEAD == local HEAD after every push.
- Cloud sandbox network is restricted to software registries + GitHub only — cannot reach financial data sites or MT5 directly.

## Next action
**User decision needed first:** whether to accept the baseline's ~15 setups/year and report
reduced confidence, or amend a baseline rule to reach the pre-registered sample floor (for that
stated non-performance reason, with the original kept as a mandatory ablation). See
`FEATURES_REPORT.md` §5 and the open item in `RESEARCH_DECISIONS.md`.

Then WP7 (Execution/Cost Model): spread, commission and slippage as concrete `CostModel`
implementations behind the interface the engine already exposes, using the generic labelled
industry-typical assumptions confirmed in WP2 — never presented as the user's actual broker
facts.
