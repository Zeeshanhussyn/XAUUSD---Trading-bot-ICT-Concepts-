# XAUUSD ICT/SMC Research Prototype — Master Progress Tracker

(Local copy — canonical cross-session copy also lives in the "New Venture" Claude project.)

## Project in one line
Lean Python research prototype to test, with strict no-lookahead backtesting, whether a specific
XAUUSD ICT/SMC setup (PDH/PDL or Asia H/L liquidity sweep → HTF bias → 5m MSS/CHOCH →
displacement → FVG retracement entry) contains repeatable statistical edge after realistic
execution costs. Falsification-oriented — a negative result is a valid outcome. No live trading,
no MQL5, no product/dashboard in Phase 1.

## Work package status
| WP | Name | Status |
|----|------|--------|
| 0 | Environment Audit | Done |
| 1 | Project Scaffold | Done — structure/docs created, synced to local folder, pushed to GitHub |
| 2 | Research Design / Preregistration | **Done** — approved by user 2026-08-24 |
| 3 | Data Acquisition | In progress |
| 4 | Data Integrity | Not started |
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

## Infrastructure status
- Cloud research sandbox: Python 3.11.15, Git 2.43.0, pandas/numpy/scipy/matplotlib/pytest/pyarrow installed.
- Local persistent folder: connected — `C:\Users\AK\Desktop\XAUUSD_Research` on user's Windows PC.
- GitHub: connected — `Zeeshanhussyn/XAUUSD---Trading-bot-ICT-Concepts-` (private). WP1 scaffold commit pushed to `main`, verified remote HEAD == local HEAD.
- Data source (MT5 export vs. free public data): to be decided in WP3.

## Next action
Starting WP2 (Preregistration) — resolve session-window / lookback / SL-buffer / liquidity-hierarchy
ambiguities with the user via A/B/C/D questions before writing PREREGISTRATION.md.
