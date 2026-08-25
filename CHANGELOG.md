# Changelog

All notable changes to this project are logged here, newest first.

## 2026-08-25 — Work Package 3: Data acquisition (in progress)

- Confirmed the cloud research sandbox cannot reach financial data sites directly (Dukascopy,
  HistData, Stooq, Yahoo Finance, Hugging Face all unreachable) — only software registries and
  GitHub are network-reachable.
- Found and fetched a free bulk source: GitHub `ejtraderLabs/historical-data` — XAUUSD
  m15/m30/h1/h4/d1, ~2012-05 to 2022-03-04, Apache-2.0 licensed, $0 cost, fully automated.
  Saved to `data/raw/github_ejtrader_2012_2022/` (gitignored like all of `data/raw/`).
- User tested Dukascopy's manual export tool: 1-minute exports capped at 1 day per request;
  1-hour exports capped at ~1-2 months per request. Bulk 5-minute-or-finer multi-year collection
  by hand is not practical.
- **Base strategy timeframe changed from 5-minute to 15-minute** (MSS/CHOCH, displacement, FVG).
  Confirmed with user 2026-08-25. `PREREGISTRATION.md` amended accordingly (pre-backtest, so this
  is a normal amendment, not a red flag).
- User decided: use the 2012-2022 GitHub window in full rather than manually filling the
  2022-2026 gap (Option A). Data split confirmed: Development 2012-05-15→2018-03-04, Validation
  2018-03-04→2020-03-04, Holdout 2020-03-04→2022-03-04. `PREREGISTRATION.md` §3 updated. WP3 done.

## 2026-08-24 — Work Package 2: Preregistration approved

- Wrote `PREREGISTRATION.md` covering baseline configuration, planned one-factor-at-a-time
  ablation comparisons, success/kill criteria, data split, and holdout process.
- Session windows, displacement lookbacks, SL buffer, major-opposing-liquidity hierarchy, and
  broker-cost-assumption approach confirmed with user via A/B/C/D questions before writing.
- All baseline choices not explicitly specified in the founding brief (Asia range variant,
  session tight/wide, HTF strict/flexible, swing N, sweep strictness, MSS variant, displacement
  variant, FVG freshness/entry/selection, pending-timeout duration, SL variant, news/spread
  baseline) were flagged transparently as Claude's defaults; both sides of every such comparison
  remain planned ablation tests in WP10, nothing was discarded.
- User approved the document as-is on 2026-08-24.

## 2026-08-24 — GitHub connected

- User created private GitHub repo `Zeeshanhussyn/XAUUSD---Trading-bot-ICT-Concepts-` and provided
  a fine-scoped Personal Access Token.
- Pushed initial WP1 scaffold commit to `origin/main`. Verified remote HEAD matches local HEAD.
- Token was used only transiently for the push command (via a one-off `http.extraheader`, never
  written to `.git/config` or any file) and is not stored anywhere.

## 2026-08-24 — Work Package 1: Project Scaffold

- Created clean project folder structure: `data/`, `src/xauusd_research/`, `tests/`, `config/`,
  `scripts/`, `results/`.
- Installed `pytest` and `pyarrow` (free, open-source) in the research environment.
- Created governance files: `README.md`, `CHANGELOG.md`, `RESEARCH_DECISIONS.md`,
  `MASTER_PROGRESS_TRACKER.md`, `TRIAL_LOG.csv`, `.gitignore`, `requirements.txt`.
- Initialized `src/xauusd_research` as a minimal Python package (`__init__.py` only — feature
  code will be added in the work packages that implement it, not before).
- Initialized local Git repository, first commit.
- Connected a folder on the user's Windows desktop (`Desktop\XAUUSD_Research`) so the project
  persists outside the cloud session; GitHub remote pending (Personal Access Token requested from
  user, not yet provided).

## 2026-08-24 — Work Package 0: Environment Audit

- Confirmed cloud research environment: Python 3.11.15, Git 2.43.0, Node 22.22.2, pandas 3.0.2,
  numpy 2.4.4, scipy 1.17.1, matplotlib 3.10.9 already present; ~30GB free disk.
- Confirmed no MetaTrader5 python package available (expected — MT5 is Windows-only, this sandbox
  is Linux). No broker/MT5 access from the cloud sandbox.
- Confirmed desktop bridge available to user's Windows device; no folder connected yet at audit
  time.
- Recommended Sonnet 5 (session default) as sufficient for this routine audit.
