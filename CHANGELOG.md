# Changelog

All notable changes to this project are logged here, newest first.

## 2026-08-25 — Work Package 5: Backtest Engine (done)

- **Critical finding, empirically verified:** the source labels bars by **open time**,
  not close time. Aggregating m15 into h1 matched the open-time reading on 2992/2992 bars
  and the close-time reading on 0/2992. Every decision in the project would otherwise have
  carried a silent 15-minute lookahead. Encoded once, in `clock.bar_close_time()`.
- **Second cross-check of the WP4 timezone work:** daily bars rebuilt from m15 on the
  17:00-NY boundary equal the broker's own daily bars with **max difference 0.0000** across
  OHLC on all 2242 days where the two day definitions coincide. Validates the EET/EEST
  conversion, the price scaling, the m15 series and the aggregation in one comparison.
- Built `src/xauusd_research/engine/`: `clock.py` (17:00-NY trading day, session windows,
  DST-safe wall-clock resolution), `resample.py` (D1/H4 rebuilt from m15 + native loader for
  the WP10 ablation), `marketview.py` (cursor-bounded causal data access), `orders.py`
  (order/position model + conservative fill simulator), `costs.py` (WP7 interface,
  zero-cost placeholder only), `backtester.py` (single forward-pass event loop).
- Four engine decisions confirmed with the user before any code was written: HTF bars built
  both ways and compared in ablation; conservative/pessimistic gap fills; positions held to
  stop or target with no time limit; equity fixed on initial capital, no compounding.
- `ENGINE_SPEC.md` records every engine rule with its source, written before any strategy
  exists so no rule can be quietly relaxed later.
- `scripts/run_engine_selftest.py` writes `ENGINE_SELFTEST_REPORT.md` from the real
  development period.
- **83 new tests** (90 total, all passing), including end-to-end scenarios whose answer is
  known by arithmetic and explicit lookahead traps. Engine runs 230,400 bars in ~3.7s.
- **Strongest single result:** information-free 1:2 entries over the development period
  return a 0.3213 / 0.3313 win rate against a theoretical breakeven of 1/3, with zero wins
  above the planned target and 44/58 real gap losses worse than −1R. The engine does not
  manufacture edge, never credits gap improvement, and always takes gap damage.
- **PREREGISTRATION.md amended (pre-backtest):** pending-order validity 25 → **50 minutes**.
  The whole-bar validity rule had made 25 minutes work out to exactly one 15m bar, against the
  "≈1-2 candles" the document described. User chose to lengthen the validity rather than
  weaken the fill rule; 25-minute and current-session-only remain WP10 ablations. No backtest
  had been run, so the change carries no overfitting risk. Self-test after the change:
  expiries fell from ~4,500 to ~2,150 per run, win rates stayed at breakeven
  (0.3211 / 0.3335 against 1/3), wins above target stayed at zero.
- Preregistered baseline parameters collected into `src/xauusd_research/config.py`, each
  traceable to a line of PREREGISTRATION.md §2. WP6 extends it per feature.
- **Verdict: proceed to Work Package 6 (core features).**

## 2026-08-25 — Work Package 4: Data Integrity (done)

- **Critical finding, empirically verified:** the GitHub source's raw timestamps are NOT UTC.
  Cross-correlated against user-downloaded Dukascopy `Etc/UTC` reference data (Jan 2013 and
  Jul 2013): winter offset = raw−2h (corr 0.99983), summer offset = raw−3h (corr 0.99996).
  This is the standard EET/EEST broker-server-time convention. Implemented as a proper
  DST-aware conversion via `Europe/Bucharest` (zoneinfo), not a naive fixed offset. Verified
  zero raw rows fall in a nonexistent/ambiguous DST-transition local time, so conversion is
  exact.
- Built `src/xauusd_research/data/loaders.py` (raw CSV → price-corrected, UTC-indexed
  DataFrame) and `src/xauusd_research/data/integrity.py` (gap/duplicate/OHLC-sanity checks).
- `scripts/run_data_integrity.py` loads all 5 timeframes, runs checks, trims to the confirmed
  data split, saves cleaned Parquet to `data/processed/` (gitignored, regenerable), and writes
  `DATA_INTEGRITY_REPORT.md`.
- 7 unit tests added (`tests/unit/test_data_loaders.py`), all passing — timezone calibration,
  price-scale sanity, DST edge-case verification, no-lookahead column check.
- Result: no duplicate timestamps, no bad OHLC relationships, no non-positive prices, no nulls
  in any of the 5 timeframes. Two flagged "extreme" daily bars correspond to genuine documented
  gold events (2013-04-15 crash, 2016-06-23 Brexit) — corroborates the series is real/correctly
  dated. **Verdict: data quality sufficient to proceed to Work Package 5.**

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
