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

## Pending decisions (to be resolved before relevant work package)

- None currently open.

- WP3 (open): how to handle the 2022-03 → 2026-08 data gap — see next message to user for the
  exact A/B choice (use 2012-2022 as the full working window and holdout, vs. user manually fills
  the recent gap via Dukascopy chunked downloads so the holdout reflects the current market
  regime).
