# XAUUSD ICT/SMC Research Prototype

**Status: Phase 1 — Python research prototype only. No live trading. No MQL5. No product.**

## What this is

A lean, falsification-oriented research project testing whether a specific XAUUSD ICT/SMC setup —
PDH/PDL or Asia High/Low liquidity sweep → HTF (Daily/4H) directional bias → 5m MSS/CHOCH →
displacement → FVG retracement entry — contains repeatable statistical edge after realistic
execution costs (spread, commission, slippage).

This is **not** a trading bot and **not** a product. The goal is to answer one question:

> Does this specific XAUUSD setup contain repeatable information after realistic execution costs?

A negative answer is a successful research outcome. No profit is assumed or claimed anywhere in
this project until proven with an untouched holdout test.

## Project state

The single source of truth for current status, decisions, and next steps is
`MASTER_PROGRESS_TRACKER.md` in this folder (and mirrored in the "New Venture" Claude project).

## Structure

```
XAUUSD_Research/
├── data/                    # raw / processed / external market + reference data ($0 free sources only)
│   ├── raw/                 # untouched source data (not committed to git — see .gitignore)
│   ├── processed/           # cleaned, validated data used by the engine
│   └── external/            # e.g. free economic-calendar / news-event data
├── src/xauusd_research/     # Python package (research engine)
│   ├── data/                # data loading / integrity checks
│   ├── engine/               # event-driven, strictly causal backtest engine (WP5)
│   ├── features/             # sessions, PDH/PDL, Asia H/L, swings, sweeps, MSS/CHOCH, displacement, FVG (WP6)
│   ├── execution/             # fills, SL/TP, partials, runner, spread/commission/slippage, risk (WP7)
│   ├── tags/                  # analysis-only tags: OB, breaker, mitigation, EQH/EQL, PWH/PWL, premium/discount, regime, liquidity cluster (WP8)
│   └── reporting/             # report/metric generation
├── tests/
│   ├── unit/                 # unit tests per feature/variant
│   └── synthetic/             # known-answer synthetic tests for the backtest engine
├── config/                   # preregistered baseline parameters
├── scripts/                  # small run scripts (e.g. run_backtest.py)
└── results/                  # generated output (trades.csv, summary.html, equity_curve.png, trials.csv, ...)
```

## Governance documents

- `MASTER_PROGRESS_TRACKER.md` — current status, always up to date
- `RESEARCH_DECISIONS.md` — every material decision made and why
- `CHANGELOG.md` — chronological log of changes
- `TRIAL_LOG.csv` — every strategy configuration ever run (never deleted)
- `PREREGISTRATION.md` — created in Work Package 2, before any strategy backtest is run

## Rules this project follows (non-negotiable, from the founding brief)

- $0 additional cost in Phase 1 — free data and open-source tools only.
- No lookahead: the backtester is a strict event replay; nothing may use information from after
  decision time T.
- No giant grid search — one pre-registered baseline configuration, then staged
  one-factor-at-a-time ablation.
- Time-ordered data split: development → validation/walk-forward → untouched holdout.
- The untouched holdout is run exactly once, only after explicit human approval.
- No MQL5 / live trading work until Phase 1 passes and is explicitly approved.

## Setup

```bash
pip install -r requirements.txt
pytest tests/
```
