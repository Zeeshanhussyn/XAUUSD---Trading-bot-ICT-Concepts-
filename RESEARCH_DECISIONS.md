# Research Decisions Log

Every material decision made during this project, with date and reasoning. Nothing here is
changed retroactively — new decisions are appended, old ones are never silently edited.

## 2026-08-24 — Project infrastructure decisions (Work Package 0/1)

**Decision:** Permanent project storage = local folder on user's Windows desktop
(`Desktop\XAUUSD_Research`), synced from the cloud research sandbox after each meaningful
checkpoint, PLUS a GitHub remote (private repo).
**Why:** The cloud sandbox this session runs in is ephemeral (can be reclaimed after inactivity).
A multi-week/month research project needs durable storage outside any single session.
**Status:** Both connected. Local folder in use. GitHub remote `Zeeshanhussyn/XAUUSD---Trading-bot-ICT-Concepts-`
connected and WP1 scaffold pushed to `main` (2026-08-24).

**Decision:** Model selection is chosen per work package between Claude Sonnet 5 and Claude
Opus 5 only (no Haiku), per explicit user preference — user will pick which one to actually use
each time it is proposed.
**Why:** User's explicit instruction (2026-08-24).

**Decision:** MT5 / broker access is out of scope for the cloud research sandbox. Claude cannot
open, log into, or control MT5 from here (no remote-desktop/terminal control of the user's
machine — only file read/write via the desktop bridge). Historical data source (broker MT5
export vs. free public source) will be decided explicitly in Work Package 3.
**Why:** Technical limitation of the current tool access; must not be silently worked around.

## 2026-08-25 — Work Package 3 data-source findings

**Decision:** Base strategy timeframe shifted from 5-minute to **15-minute** for MSS/CHOCH,
displacement, and FVG detection (session/PDH/PDL/Asia-range logic unaffected — those stay time-
based, not bar-based).
**Why:** Genuine bulk free multi-year 5-minute (or finer) XAUUSD data is not obtainable — the
cloud research sandbox's network is restricted to software-package registries and GitHub only
(confirmed by testing: Dukascopy, HistData, Stooq, Yahoo Finance, Hugging Face all unreachable).
Dukascopy's manual web export tool cannot bulk-export minute-level data (1-day cap per request for
1-minute; ~1-2 months per request for 1-hour) — collecting 5-minute data for a full multi-year
window by hand would require hundreds of manual downloads, which is not practical.
**Status:** Confirmed by user 2026-08-25.

**Decision:** Primary bulk data source = GitHub repo `ejtraderLabs/historical-data` (free,
Apache-2.0, fetched automatically via `raw.githubusercontent.com`, $0 cost, zero manual effort).
Provides XAUUSD m15/m30/h1/h4/d1 for ~2012-05 to 2022-03-04 (~9.6 years).
**Limitation:** Does not cover 2022-03-04 → present (2026-08). This gap must be resolved before
finalizing the data split (see open question below).
**Status:** Data fetched and saved to `data/raw/github_ejtrader_2012_2022/` (2026-08-25), not yet
cleaned/validated (WP4).

## 2026-08-25 — Work Package 4 finding: raw data timezone

**Finding:** The GitHub source's raw `Date` column is EET/EEST broker-server time (UTC+2
winter / UTC+3 summer), not UTC as might be assumed. Determined empirically (not guessed) by
cross-correlating against user-downloaded Dukascopy `Etc/UTC` reference data for both a winter
and a summer month — see `DATA_INTEGRITY_REPORT.md` for the full correlation results.
**Why this matters:** every session/PDH-PDL/DST calculation in this project depends on correct
UTC timestamps. Getting this wrong would have silently corrupted every downstream result.
**Status:** Implemented as a proper DST-aware `zoneinfo` conversion (`Europe/Bucharest`),
verified with unit tests, zero ambiguous/nonexistent-time rows found.

## 2026-08-25 — Work Package 5 engine decisions (all confirmed by user before coding)

**Finding (not a decision):** bar timestamps in this source are **open times**, not close
times. Established by aggregating m15 into h1 in both directions — 2992/2992 bars matched
the open-time reading, 0/2992 matched close-time. Encoded in `clock.bar_close_time()`; a
bar is unusable until `open_time + duration`.

**Q1 — Higher-timeframe bars: build both, compare in ablation.**
Baseline D1/H4 are rebuilt from m15 anchored to the 17:00-NY trading day; the broker's
native D1/H4 become a WP10 ablation.
**Why:** the broker's own day rolls at 00:00 EET/EEST, which lands on 18:00 NY rather than
17:00 NY on 159 of 2532 days (the weeks where US and EU DST dates differ), conflicting with
the PDH/PDL definition in PREREGISTRATION.md §2. The native daily series also starts
2012-11-13 against m15's 2012-05-15, which would have silently cost ~6 months of the
development period. Rebuilding fixes both; keeping the native series as an ablation means
the difference gets measured rather than assumed.
**Validation:** on the 2242 days where both definitions coincide, the rebuilt daily bars
match the broker's own to a maximum OHLC difference of 0.0000.

**Q2 — Gap fills: conservative / pessimistic.**
A gap through the stop fills at the bar open (full gap taken as loss). A gap through the
target fills at the target (no gap bonus). A gap through the entry limit fills at the limit
(no gap bonus).
**Why:** ambiguity should never flatter the result. Confirmed working on real data — 44 and
58 losses worse than −1R across the two self-test runs, and zero wins above the target.

**Q3 — Open positions are held to stop or target, with no time limit**, including across
days and weekends. Session-end and day-end forced closes remain available as WP10 ablations
via `close_now()`.
**Why:** simplest rule, and the one most consistent with the fixed 1:2 exit model that
PREREGISTRATION.md §2 labels BENCHMARK. Note this is what produces the largest gap losses
(worst observed −4.91R, over a weekend) — that cost is real and is being taken honestly.

**Q4 — Equity curves use fixed risk on INITIAL equity (no compounding).**
**Why:** keeps the equity curve a faithful rescaling of the R sequence, so edge and
compounding effects stay separable and drawdowns are not flattered by a good early run.
R-multiples remain the primary reporting unit regardless. `ruin_point()` reports where an
account would actually have been wiped out, since a non-compounding curve can otherwise show
a meaningless negative balance.

**Q5 — Pending-order validity: baseline lengthened from 25 to 50 minutes (RESOLVED).**
The engine resolves a resting order against a bar only if the order was live for the *whole*
bar, because it never knows where inside a 15-minute bar a level was touched and so cannot
know whether a touch preceded a mid-bar expiry — the same no-intrabar-path principle applied
to stop/target ambiguity. That made the preregistered 25-minute validity work out to exactly
**one** 15m bar, against the "≈1-2 fifteen-minute candles" PREREGISTRATION.md §2 described.
Presented to the user with three options (keep 1 bar / relax the fill rule to 2 bars / lengthen
the validity); the user chose to **lengthen the baseline validity to 50 minutes** and keep the
fill rule intact.
**Why this is not overfitting:** no backtest of any kind had been run when the change was made,
so no result could have influenced it. Logged as a dated amendment in PREREGISTRATION.md.
25-minute and current-session-only remain WP10 ablation variants, and `whole_bar_validity=False`
remains a separate ablation switch — nothing was discarded.
**Effect measured on the self-test:** expiries fell from ~4,500 to ~2,150 per run; win rates
stayed at breakeven (0.3211 / 0.3335 against 1/3), and wins above the planned target stayed at
zero.

**Housekeeping:** preregistered baseline parameters now live in one place,
`src/xauusd_research/config.py`, each traceable to a line of PREREGISTRATION.md §2. WP6 extends
that file as each feature is implemented.

## 2026-08-25 — Work Package 6 feature definitions (all confirmed by user before coding)

**Housekeeping first:** the original 37,443-character master prompt was recovered from the
session transcript and stored verbatim as `FOUNDING_BRIEF.md`. It had lived only inside a chat
session, and a compacted summary of a brief is not the brief. Anything later claimed to come
"from the brief" is now checkable against that file. Re-reading it also confirmed the WP5
50-minute pending-order validity was one of the brief's own three listed variants.

The brief uses four terms without ever defining them operationally. Code cannot be written
against an undefined term, so each was put to the user as an explicit choice. No backtest had
been run, so no result could have influenced any answer.

**Q1 — "Daily bias is clear" = Daily swing structure.** Higher-high AND higher-low = bullish;
lower-high AND lower-low = bearish; anything else neutral, and neutral Daily blocks the trade.
**Why:** reuses the fractal definition already required elsewhere, so it adds no parameter, and
it produces a principled "neutral" (an expanding range is genuinely not a trend). Measured
consequence: Daily is neutral on 39% of development bars, and the combined FLEXIBLE gate blocks
58% of all bars.

**Q2 — MSS reference swing is fixed at the sweep.** The most recent *confirmed* opposite-side
swing that already existed when the sweep candle closed; it does not update as new swings form.
**Why:** keeps the sweep and the structure break part of one event and gives SL Variant B a
stable invalidation level. A necessary corollary, implemented and counted rather than assumed:
if price is already past that swing at the sweep, there is nothing to break and the setup is
rejected (874 of 5,980 sweeps).

**Q3 — A sweep stays live until the end of its own session.** Direct consequence, stated
explicitly: a sweep occurring outside a tracked session window is not tracked at all, since it
would have no session in which to expire.
**Why:** sessions are already part of the strategy, so this adds no parameter. Measured
consequence: this is the single largest filter in the funnel — 4,147 of 5,980 sweeps expire
before any MSS, because the median sweep completes with only 5 bars left in a 12-bar session.

**Q4 — Only the FVG centred on the MSS displacement candle is eligible.**
**Why:** matches the brief's own logic chain (sweep → MSS → displacement → FVG), and keeps the
entry inside the move that broke structure. Measured consequence: 321 of 959 MSS events left no
gap at all and produced no setup.

## 2026-08-25 — Work Package 6 finding: the baseline is low-frequency

**Finding:** the pre-registered baseline produces **88 tradeable setups in 5.8 development
years (~15/year)**. Extrapolated across development plus validation that is ~118, against the
400+ initial-feasibility floor in PREREGISTRATION.md §5. Full funnel in `FEATURES_REPORT.md`.

**Not acted on.** FOUNDING_BRIEF.md is explicit: *"Never force extra trades merely to increase
sample."* Loosening a rule now, having just seen that the strict version yields few setups,
would be a degree of freedom exercised after looking at the data — even though no P/L exists
yet. It was therefore reported and put to the user as an explicit decision rather than absorbed
quietly.

**User decision, 2026-08-25: keep the baseline exactly as pre-registered.** Nothing is changed
to raise the trade count. The consequences are accepted knowingly and must be stated in the
WP15 final report:

- Any conclusion rests on roughly 118 trades across development and validation, not the 400+
  the pre-registration asks for.
- A **positive** result on this sample would be meaningful precisely because the sample is
  small and the rules were fixed in advance — but confidence intervals will be wide and must
  be shown, not hidden behind point estimates.
- A **null or negative** result on this sample is weak evidence. It cannot be reported as "the
  strategy has no edge"; only as "no edge was detectable at this sample size", which is a
  different and much weaker claim. PREREGISTRATION.md §6 already lists "trade count too low to
  conclude anything" as a warning criterion, and it is now expected to trigger.
- The higher-frequency variants (trading-day sweep window, wide sessions, N=3) remain WP10
  ablations and will be run there as planned comparisons — not as a repair to the baseline.

For reference, the STRICT HTF gate — a planned WP10 comparison — yields fewer setups, not more.

## 2026-08-25 — Work Package 7 cost decisions

**Finding (measured, not a decision): the price series quotes BID.** Established against the
user's Dukascopy reference files, which label their side: ours sits $0.42 below their ASK
(Jan 2013, n=525) and within $0.03-$0.12 of their BID (Feb 2013 n=457, Jul 2013 n=524).
**Why it matters:** every level in the project is derived from this series and is therefore in
bid terms, so exactly one leg of each round trip transacts at the ask and pays the spread — the
buy leg. Long pays going in, short coming out. Charging both legs would double the modelled cost;
charging neither would erase it, and no summary statistic would reveal which error had been made.

**Finding: the implied spread in Jan 2013 was ~$0.41/oz median**, and ~$0.40 inside both the
London and New York windows. Our trading hours are not cheaper than the rest of the day. That is
worth stating because the opposite is widely assumed.

**Decision — cost assumptions (user, 2026-08-25):** two generic labelled profiles, Standard
($0.30/oz spread, no commission) and Raw/ECN ($0.15/oz + $0.07/oz round-trip commission), plus
the measured 2013 era ($0.42) as a third scenario. Normal slippage $0.10/oz, applied only to
stops and forced closes. Mandatory 2x stress on the total.
**Why not the measured figure as baseline:** it comes from 2013 and an ECN-style broker, a
wide-spread era for gold; applying it across 2012-2022 would overstate cost in the later years.
**Labelling:** these are assumptions, never presented as the user's broker's terms.

**Decision — co-primary stop-loss baselines (user, 2026-08-25).**
*What forced it:* SL Variant B — Claude's flagged, never-user-confirmed default — is mechanically
unsound in combination with the WP6 FVG rule. The eligible gap is created by the same candle that
broke the reference swing, so the gap sits on the swing: **36 of 149 setups put the entry at or
beyond the stop**, which cannot be executed. Of the remainder the median stop is $0.81, so a
$0.30 spread plus $0.10 slippage is ~49% of one R and a 1:2 system would need a ~48% win rate
merely to break even. Variant A (sweep wick) gives 149/149 valid orders, a $3.85 median stop and
~10% cost.
*Chosen resolution:* run **both** as co-primary baselines rather than swapping one default for
another.
*Integrity conditions, fixed now:* both declared before any backtest, so this is a pre-registered
two-arm comparison and not two looks; multiplicity stated in every report; the holdout still spent
exactly once with both arms inside that single pass; taking only the better development arm to the
holdout explicitly forbidden; Variant B's unexecutable setups skipped and counted, not dropped.

**Not implemented, deliberately:** the abnormal-spread filter (requires a bar-by-bar spread that
does not exist in this data — the filter would compare a constant against itself) and the news
blackout plus news-period slippage (requires point-in-time economic-event data this sandbox cannot
reach). FOUNDING_BRIEF.md: "If trustworthy point-in-time data cannot be obtained for a particular
field: DO NOT fabricate it." Both are gaps to restate in the WP15 report, not silent omissions.

## 2026-08-25 — Work Package 8 tag decisions

**Decisions (user, 2026-08-25, WP8 Q1-4) — four tag mechanics the brief never defined
operationally:**
- **Order Block** (also fixes Breaker and Mitigation, which are states an order block passes
  through, not separate detectors): the last opposite-colour candle immediately before the
  MSS's own displacement leg, searched backward. Ties directly into the setup pipeline already
  built rather than introducing a second, unrelated notion of "swing" for OB purposes.
- **Equal Highs/Lows tolerance:** 0.10 x ATR(14), sampled at the second swing's own bar —
  consistent with the SL buffer and liquidity-cluster tolerances already in the project.
- **Premium/Discount reference range:** each setup's own two already-computed levels — the
  level that was swept, and the MSS reference swing it broke — not a new independent range.
  Adds zero causal risk since both prices already exist on the `Setup`.
- **Market Regime method:** rolling ATR(14) percentile for volatility; rolling Kaufman
  efficiency ratio for trend, per the brief's explicit "keep it simple, no ML classifier"
  instruction.

**Not put to the user — direct, unambiguous extensions of a rule already fixed elsewhere in the
project, implemented as Claude's default and logged rather than voted on:**
- **Previous Week High/Low** boundary: every 17:00-NY trading day already belongs to exactly
  one ISO calendar week (the Sunday-evening session already maps to Monday's trading day), so
  "week" needed no new time-zone or roll-hour decision.
- **Sequential Liquidity Events:** scoped to the trading day already carried on every `Sweep`.
  The brief's own worked example (Asia Low swept, later PDH/PDL swept) is same-day.

**Finding and self-correction: the trend-regime cutoff was miscalibrated, and was fixed before
any backtest touched it.** The first implementation used the textbook 0.6 efficiency-ratio
threshold for "trending." Measured against the actual 5.8-year development period, the 480-bar
efficiency ratio never once reached 0.6 (max observed 0.30) — gold is too noisy intraday at 15m
for that number, and using it anyway would have made "trending" a label that never fires, with
zero information content. Replaced with a rolling percentile of the ratio against its own
trailing history (top quartile = trending), matching the volatility axis's own design. This is
a parameter calibration correction, not a strategy-rule change, found and fixed while building
the WP8 report — before Work Package 9 exists — so it carries no overfitting risk of any kind.

**Not implemented, deliberately:** the 1-minute context tag. This project never acquired
minute-level XAUUSD data in bulk (WP3 amendment — free multi-year 5m-or-finer data was not
obtainable), and nothing at that resolution exists in `data/processed/`. A data-availability
gap, not a decision, logged for restatement in the WP15 final report alongside WP7's two gaps
(abnormal-spread filter, news blackout).

Full counts for every tag against the 88 reachable baseline setups are in `TAGS_REPORT.md`.

## Pending decisions (to be resolved before relevant work package)

- None currently open.

- WP3 (open): how to handle the 2022-03 → 2026-08 data gap — see next message to user for the
  exact A/B choice (use 2012-2022 as the full working window and holdout, vs. user manually fills
  the recent gap via Dukascopy chunked downloads so the holdout reflects the current market
  regime).
