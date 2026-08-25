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
| 4 | Data Integrity | **Done** — see below |
| 5 | Backtest Engine | Not started |
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

## Infrastructure status
- Cloud research sandbox: Python 3.11.15, Git 2.43.0, pandas/numpy/scipy/matplotlib/pytest/pyarrow installed.
- Local persistent folder: connected — `C:\Users\AK\Desktop\XAUUSD_Research` on user's Windows PC, kept in sync after every checkpoint.
- GitHub: connected — `Zeeshanhussyn/XAUUSD---Trading-bot-ICT-Concepts-` (private), `main` branch, verified remote HEAD == local HEAD after every push.
- Cloud sandbox network is restricted to software registries + GitHub only — cannot reach financial data sites or MT5 directly.

## Next action
WP5 (Backtest Engine) — not yet started, awaiting user go-ahead + model choice (Sonnet 5 vs Opus 5). This is a core-correctness package (event-driven, strictly causal engine + synthetic known-answer tests) — likely warrants the stronger model.
