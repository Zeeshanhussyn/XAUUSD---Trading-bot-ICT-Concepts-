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
| 2 | Research Design / Preregistration | Done — approved 2026-08-24 |
| 3 | Data Acquisition | Done — GitHub source, 2012-2022, 15m base timeframe, data split confirmed |
| 4 | Data Integrity | Done — EET/EEST timezone finding, 5 timeframes clean |
| 5 | Backtest Engine | **Done** — see below |
| 6 | Core Features | Not started |
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
0.3213 / 0.3313 win rate against a theoretical breakeven of 1/3, with zero wins above the
planned target and real gap losses down to −4.91R. The engine manufactures no edge, never
credits gap improvement, and always takes gap damage. **Verdict: proceed to WP6.**

**One item open for the user:** the whole-bar validity rule makes the preregistered 25-minute
pending-order life exactly 1 bar rather than the "≈1-2" in PREREGISTRATION.md §2. Both
settings are already WP10 ablations and no backtest has run — changing it costs nothing.

## Infrastructure status
- Cloud research sandbox: Python 3.11.15, Git 2.43.0, pandas/numpy/scipy/matplotlib/pytest/pyarrow installed.
- Local persistent folder: connected — `C:\Users\AK\Desktop\XAUUSD_Research` on user's Windows PC, kept in sync after every checkpoint.
- GitHub: connected — `Zeeshanhussyn/XAUUSD---Trading-bot-ICT-Concepts-` (private), `main` branch, verified remote HEAD == local HEAD after every push.
- Cloud sandbox network is restricted to software registries + GitHub only — cannot reach financial data sites or MT5 directly.

## Next action
WP6 (Core Features) — not yet started, awaiting user go-ahead + model choice (Sonnet 5 vs
Opus 5). This is where the actual ICT/SMC definitions get implemented on top of the engine:
PDH/PDL and Asia High/Low levels, swing fractals (N=2), liquidity sweeps (strict), MSS/CHOCH
with displacement, and FVG detection — every one strictly causal, each with its own
known-answer tests. Another core-correctness package; the stronger model is likely warranted
again.
