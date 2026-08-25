# PREREGISTRATION — XAUUSD ICT/SMC Liquidity-Sweep Strategy (Phase 1)

Status: **APPROVED by user on 2026-08-24, amended 2026-08-25 (still pre-backtest — see amendment
below).** No strategy backtest has been run yet — this document was approved before WP9 (Baseline
Development Backtest). Any change after a backtest has been run must be logged as a new dated
entry below and in `RESEARCH_DECISIONS.md` / `TRIAL_LOG.csv`.
Date: 2026-08-24 (approved 2026-08-24)

### Amendment — 2026-08-25 (pre-backtest, WP3 data acquisition)

**Base structural timeframe changed from 5-minute to 15-minute** for MSS/CHOCH, displacement, and
FVG detection. Reason: genuine bulk free multi-year 5-minute-or-finer XAUUSD data is not obtainable
(cloud sandbox network is restricted to software registries + GitHub only; Dukascopy's manual
export tool caps 1-minute exports at 1 day and 1-hour exports at ~1-2 months per request — hand-
collecting years of 5-minute data is impractical). Confirmed with user 2026-08-25. Every "5m" /
"5-minute" reference below now means 15-minute; session/PDH/PDL/Asia-range definitions are
time-based and unaffected. Displacement/ATR lookback periods keep the same period-*counts* (20-bar
average body, ATR(14)) now applied to 15-minute bars — this was Claude's default at the new
timeframe, not re-confirmed line-by-line, and is called out here for the user to veto if desired.

This document is written BEFORE any strategy result exists. It is not to be edited after results
are seen without recording the change as a new, dated entry in `RESEARCH_DECISIONS.md` and a new
row in `TRIAL_LOG.csv`. Any post-hoc edit to this file after WP9 has run is itself a red flag for
overfitting and must be called out as such in the final report.

## 1. Research question

> Does a PDH/PDL or Asia High/Low liquidity-sweep → HTF-bias → 15m MSS/CHOCH+displacement → FVG
> retracement XAUUSD setup contain statistically repeatable information after realistic execution
> costs (spread, commission, slippage)?

This is a falsification exercise. No edge is assumed. A negative, well-evidenced result is a
successful outcome and will be reported as such.

## 2. Baseline configuration (run once, unmodified, in Work Package 9)

Every parameter below marked **(default — not yet explicitly confirmed by user)** was chosen by
Claude as a reasonable starting point because the master brief listed it as "test separately"
without naming which side is the baseline. All such items **are still tested as the other side of
the comparison in the staged ablation (Work Package 10)** — nothing is discarded, this only fixes
what runs first. The user can change any of these before approving this document.

| Component | Baseline setting | Status |
|---|---|---|
| Asset | XAUUSD | fixed |
| Liquidity sources | Both PDH/PDL and Asia High/Low, tracked and reported separately (never combined into one hidden metric) | fixed (from brief) |
| PDH/PDL trading day | 17:00 New York → 17:00 New York next day, DST-aware (`America/New_York` tz) | fixed (from brief) |
| Asia range | Variant A: 00:00–05:00 London time (`Europe/London` tz, DST-aware) | **default** — Variant B (00:00–06:00) tested in WP10 |
| Session windows | London tight 07:00–10:00 / wide 07:00–16:00; New York tight 08:30–11:00 / wide 08:00–17:00 (both `Europe/London` / `America/New_York` local time, DST-aware). Baseline uses **tight** windows; wide tested in WP10 | confirmed by user (windows) + default (tight-as-baseline) |
| HTF bias | Daily = primary, 4H = confirmation, **FLEXIBLE** rule: Daily clear + 4H neutral/transition → trade allowed only if 15m MSS/CHOCH+displacement confirms Daily direction; 4H clearly opposing → blocked | **default** — STRICT (Daily+4H must both align) tested in WP10 |
| Previous-day midpoint/open filter | Not used in baseline (optional analysis tag only) | fixed (from brief) |
| Swing definition | Fractal N=2. A swing requiring future confirmation bars is usable only after those bars have closed (strict no-lookahead) | **default** — N=3 tested in WP10 |
| Liquidity sweep | STRICT: penetration + same-candle close back inside/reclaim | **default** — LOOSER (reclaim within next 1–2 candles) tested in WP10 |
| MSS/CHOCH | Variant B: body-close break of a meaningful swing **+ displacement required** (matches brief's stated core logic) | **default** — Variant A (body-close only, no displacement) tested in WP10 to isolate displacement's value |
| Displacement | Variant A: candle body ≥ 1.5 × average body of the preceding 20 candles (15m, causal, current candle excluded) | **default** — Variant B (range ≥ 1.5 × ATR(14), 15m, causal) tested in WP10. Lookback period-counts (20-bar average, ATR 14) confirmed by user at 5m; carried forward unchanged to 15m per 2026-08-25 amendment |
| FVG | Standard 3-candle FVG | fixed (from brief) — size filters (≥0.25 ATR, ≥0.50 ATR) tested in WP10 |
| FVG freshness | Valid only until first touch | **default** — 50%-mitigation and full-fill freshness rules tested in WP10 |
| FVG entry | First touch | **default** — 50% midpoint entry tested in WP10 |
| Multiple-FVG selection | Nearest FVG to current price (deterministic, no hindsight) | **default** — "first formed" and "deepest retracement" selection rules tested in WP10 |
| Entry fill realism | Limit entry must trade ≥1 tick THROUGH the level to count as filled. Real intrabar sequence used where available; conservative assumption otherwise. Ambiguous SL/TP order → **stop-first** | fixed (hard rule, from brief) |
| Confirmation timing | Confirmation candle must **close** before entry becomes eligible; entry starts next candle onward | **default** (matches brief's stated "Primary") — same-candle aggressive variant tested in WP10, built so it cannot use information only available at that candle's close before the close actually happened |
| Missed entry | PRIMARY: if FVG never retraces, it is a missed setup — no chase | fixed (matches brief's stated "PRIMARY") — market-entry-after-confirmation variant tracked separately |
| Pending entry validity | Maximum 25 minutes real time (expressed in minutes, not candle-count, so it survives the 5m→15m timeframe change — ≈1-2 fifteen-minute candles) | **default** — current-session-only and 50-min variants tested in WP10. Cancelled immediately on opposite structure break, sweep-extreme invalidation, or session end (hard rule) |
| Stop loss | Variant B: beyond MSS/CHOCH invalidation swing | **default** — Variant A (beyond sweep extreme) tested in WP10 |
| SL buffer | 0.1 × ATR(14), 15m, causal | confirmed by user at 5m; carried forward to 15m per 2026-08-25 amendment |
| Minimum RR | Fixed target ≥ 1:2 | fixed (from brief) — stricter "nearest opposing PDH/PDL or Asia H/L also allows ≥1:2" variant tested in WP10, using the hierarchy below |
| Major opposing liquidity hierarchy | Opposite-side PDH/PDL and opposite-side Asia High/Low only, nearest-to-entry-price first. No subjective zones, no "clean path" judgment | confirmed by user |
| Exit model | MODEL 1 — BENCHMARK: fixed 1:2, full close | fixed (labeled "BENCHMARK" in brief) — MODEL 2 (2R partial + runner, both runner variants) tested in WP10, reported separately (entry MFE/MAE vs final strategy P/L kept separate, never mixed) |
| Max trades/day | Reported at cap = 5/day (research cap, not a target) AND separately at cap = first 2/day, for comparison | fixed (from brief) |
| Overlapping positions | No overlapping full-risk positions. New signal while a position is active → logged as valid-but-not-executed (`overlap` tag). Once existing position has taken 2R partial and runner is protected, a fresh valid setup may be executed (`runner-active` tag) | fixed (hard rule, from brief) |
| Opposite-direction setup | Primary: only if Daily/4H context flips or clearly confirms opposite direction. Aggressive variant (fresh 5m MSS/CHOCH+displacement reversal without full HTF flip) tracked separately | fixed (from brief) |
| Re-entry after loss | Allowed only with fresh liquidity event + fresh 15m MSS/CHOCH + fresh displacement, tagged `re-entry` | fixed (from brief) |
| News filter | OFF (Filter A) | **default** (labeled "A" first in brief) — ±15min (B) and ±30min (C) USD high-impact blackout tested in WP10, using free timestamp-correct historical event data only (no fabricated data if unavailable) |
| Spread | A: include actual historical spread cost, do not skip abnormal spread | **default** (labeled "A" first in brief) — B (abnormal-spread filter skips entry) tested in WP10 |
| Slippage | Normal slippage modeled in baseline; news-period slippage and 2× stressed slippage applied as explicit stress-test layers (WP11), not baseline alternatives | fixed (from brief) |
| Broker cost profile | Standard account style, using **generic labeled industry-typical assumptions** (spread + zero/low commission) — NOT the user's actual broker facts, since those were not available. Explicitly labeled as an assumption everywhere it appears in reports | confirmed by user (use generic assumptions) |
| Broker cost profile — comparison | Raw/ECN style (tighter spread + explicit commission), also generic labeled assumptions | fixed (from brief) — plus mandatory 2× total-cost stress test (WP11) |
| Risk per trade | Results reported primarily in **R-multiples**. Equity-curve sensitivity compared at 0.25% / 0.50% / 1.00% risk/trade. 0.50% is the eventual demo default; 1% is research sensitivity only | fixed (from brief) |
| Random benchmark | Mandatory, reproducible seeds, matched sessions/trade-count/cost assumptions/risk distribution | fixed (from brief) |

## 3. Data split (exact year boundaries fixed after WP4, once actual clean-data range is known)

- **Development period:** earliest clean years available
- **Validation / rolling walk-forward period:** middle years
- **Untouched holdout:** latest 1–2 years — never inspected, never optimized on, until the user
  gives explicit written approval in WP13, run exactly once in WP14
- Target: up to 8 clean years total; minimum 5–6 clean years if older data quality is poor. No bad
  data used merely to inflate sample size.
- No random shuffling of time-series data at any stage.

## 4. Planned comparisons (staged, one-factor-at-a-time from the baseline above — no grid search)

Asia range variant · session tight vs wide · HTF bias strict vs flexible · swing N=2 vs N=3 ·
sweep strict vs looser · MSS body-close-only vs +displacement · displacement Variant A vs B ·
FVG size filters · FVG freshness rules · FVG entry (first-touch vs midpoint) · multi-FVG selection
rule · confirmation timing (close vs same-candle) · pending validity duration · SL Variant A vs B ·
stricter minimum-RR (major-opposing-liquidity) · exit Model 1 vs Model 2 (+ runner variants) ·
news filter off/±15/±30 · spread filter on/off · broker cost profile (Standard vs Raw/ECN) · 2×
cost stress · risk % sensitivity (0.25/0.50/1.00%) · max-trades/day (5 vs first-2) · re-entry vs
no-re-entry · long vs short · London vs NY · PDH/PDL vs Asia sweep.

Every configuration ever run — baseline or ablation — is logged in `trials.csv` with trial_id,
timestamp, git commit, data period, parameters, purpose, result summary, and whether it influenced
future development. Nothing is ever deleted from this log.

## 4a. Data sourcing (added 2026-08-25, Work Package 3)

- **2012-05 to 2022-03-04 (~9.6 years):** GitHub `ejtraderLabs/historical-data` (free,
  Apache-2.0), m15/m30/h1/h4/d1, fetched automatically, $0 cost. See
  `data/raw/github_ejtrader_2012_2022/SOURCE.md` for exact provenance and known caveats (price
  values are ×100 scaled, must be corrected in WP4).
- **2022-03-04 to present:** not yet covered — resolution pending user decision (see chat).
- Any additional manually-collected Dukascopy chunks are kept in `data/raw/` with self-describing
  filenames (instrument, timeframe, side, exact date range).

## 5. Success criteria (evidence-based, no single metric is decisive alone)

- Positive out-of-sample expectancy (R/trade) after realistic costs.
- Profit factor: 1.2–1.3 = weak/marginal, 1.3–1.5 = promising, ≥1.5 = stronger evidence — but PF
  alone never decides pass/fail.
- Edge survives 2× total transaction-cost stress.
- Meaningfully separated from the matched random benchmark.
- Not concentrated in one narrow period or in the top-5 trades.
- Reasonably stable under parameter sensitivity and walk-forward.
- Adequate sample: 400+ trades for initial feasibility, 800+ preferred; if trade frequency is
  inherently low, years/regime coverage substitutes for raw count.

## 6. Kill / warning criteria (evidence + recommendation, never an automatic single-metric kill)

OOS expectancy ≤ 0 after realistic costs · edge disappears under modest cost stress · random
benchmark performs similarly · performance concentrated in one tiny period or the top-5 trades ·
extreme sensitivity to small parameter changes · strict anti-lookahead implementation kills the
result (this is treated as a valid finding, not a bug to work around) · trade count too low to
conclude anything · later demo/live diverges materially from research · complexity keeps
increasing merely to repair poor results.

## 7. Holdout boundary and process (non-negotiable)

Development and validation/walk-forward work (WP9–WP12) uses only the development and validation
periods. When that work is complete, Claude STOPS at Work Package 13, summarizes what worked,
what failed, trial count, best legitimate configuration, and any overfitting evidence, and asks:

> "Untouched holdout ab ek dafa run karna hai?"

The holdout is run — exactly once, in WP14 — only after an explicit "yes" from the user. No
retuning after seeing it while still calling it a holdout test.
