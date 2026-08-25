# ENGINE_SPEC — backtest engine rules (Work Package 5)

Every rule the engine applies, in one place, written **before any strategy
exists**. Each rule states where it came from: the founding brief, an approved
line of `PREREGISTRATION.md`, or a dated user decision.

This file exists so that a rule cannot be quietly relaxed later to improve a
result. Any change after Work Package 9 has run must be logged as a dated entry
in `RESEARCH_DECISIONS.md` and called out in the final report.

Empirical evidence for everything claimed here is in `ENGINE_SELFTEST_REPORT.md`.

---

## 1. Bar timestamps are OPEN times

A bar labelled `T` with duration `D` covers `[T, T+D)` and its OHLC is **unknown
until `T+D`**.

Verified, not assumed: aggregating m15 bars into h1 bars matched the forward
(open-time) reading on 2992 of 2992 bars and the backward (close-time) reading
on 0 of 2992. Reading these labels as close times would have given every single
decision in the project a silent 15-minute lookahead.

`clock.bar_close_time()` is the only place this conversion happens.

## 2. The trading day is 17:00 New York, always

Source: `PREREGISTRATION.md` §2 (from the founding brief).

A trading day labelled `D` runs from 17:00 NY on `D-1` to 17:00 NY on `D`,
named after the date it ends on. Resolved through `America/New_York`, so it
follows US daylight saving: the day containing a spring-forward is 23 hours and
the one containing a fall-back is 25.

The engine never derives the day boundary from the broker's bar labels. The
broker rolls its day at 00:00 EET/EEST, which lands on 17:00 NY for 2242 days
but on 18:00 NY for 159 of 2532 days (6.6%) — the weeks where US and EU
daylight-saving dates differ.

## 3. Session windows

Source: `PREREGISTRATION.md` §2, confirmed by user.

| Window | Local time | Zone | Role |
|---|---|---|---|
| Asia range A | 00:00–05:00 | `Europe/London` | baseline |
| Asia range B | 00:00–06:00 | `Europe/London` | WP10 ablation |
| London tight | 07:00–10:00 | `Europe/London` | baseline |
| London wide | 07:00–16:00 | `Europe/London` | WP10 ablation |
| New York tight | 08:30–11:00 | `America/New_York` | baseline |
| New York wide | 08:00–17:00 | `America/New_York` | WP10 ablation |

All half-open `[start, end)`. Every window is asserted to lie inside its own
trading day, on every date, including both DST transitions.

## 4. Higher-timeframe bars

User decision, 2026-08-25 (WP5 Q1 = "build both, compare in ablation").

- **Baseline**: D1 and H4 rebuilt from m15, anchored to the 17:00-NY trading
  day, so the HTF bias and the PDH/PDL levels share one definition of "day".
- **WP10 ablation**: the broker's native D1/H4, via `load_native_htf()`.

Bucketing uses the New York **wall clock**, so the 01:00–05:00 NY bucket holds
3 real hours on the spring-forward date and 5 on the fall-back date. A trading
day therefore never produces a seventh 4H bucket.

Cross-check: on all 2242 days where the two day definitions coincide, the
rebuilt daily bars equal the broker's own daily bars with a maximum difference
of **0.0000** across open, high, low and close. One comparison validating the
WP4 timezone conversion, the price scaling, the m15 series and this aggregation
at once. Rebuilding also recovers ~6 months of development history the native
daily series does not cover.

## 5. Order lifecycle

**Submission.** A strategy sees bar `i` only after every fill bar `i` could
cause has already been decided. An order submitted at bar `i`'s close is
eligible from bar `i+1`. Enforced twice: by the loop's ordering, and by an
explicit submitted-at-bar guard.

**Validity.** An order is eligible during a bar only if it is live for the
**whole** bar (`expires_at >= bar.close_time`). The engine never knows where
inside a bar a level was touched, so it cannot know whether a touch preceded a
mid-bar expiry; refusing the partial bar applies the same
no-intrabar-path principle used everywhere else. With the preregistered
25-minute validity this leaves an order live for exactly one 15m bar.

> **Open for user review.** `PREREGISTRATION.md` §2 describes the 25-minute
> validity as "≈1-2 fifteen-minute candles". The whole-bar rule makes it
> exactly 1. Setting `whole_bar_validity=False` relaxes it to any overlap,
> giving 2. Both are already inside the WP10 ablation ("pending validity
> duration"), and no backtest has been run, so this can be changed at no cost
> to research integrity.

**One position at a time.** Source: `PREREGISTRATION.md` §2, hard rule. The
moment one resting order fills, every other resting order is cancelled. Where
several orders could fill on the same bar, the earliest-submitted one wins —
deterministic, never price-dependent.

**Trailing.** `modify_stop()` moves the protective stop, for the WP10 runner
variants. It cannot move entry or target.

## 6. Fill rules

Confirmed by user 2026-08-25 (WP5 Q2 = conservative/pessimistic); the
tick-through rule is a hard rule from the founding brief. Tick size 0.01 USD,
verified from the data.

| Order | Trigger | Fill price | On a gap through the level |
|---|---|---|---|
| Limit entry | ≥1 tick **through** | the limit | still the limit — no gap bonus |
| Stop loss | **touch** | the stop | the **bar open** — full gap taken |
| Take profit | ≥1 tick **through** | the target | still the target — no gap bonus |

The asymmetry is deliberate. A gap can only ever hurt us. Measured over the
development period, information-free strategies produced 44 and 58 losses worse
than −1R, and **zero** wins above +2R.

## 7. Intrabar ambiguity

A 15-minute bar reports its high and its low but not their order, and no finer
data exists. Resolution, in order:

1. **Gap phase.** Levels are checked against the bar's **open** first. A level
   the bar opened beyond was reached before any intrabar movement, so it is
   unambiguous. Stop and target sit on opposite sides of entry, so at most one
   can gap.
2. **Intrabar phase.** If neither gapped and both levels lie inside
   `[low, high]`, the **stop is taken** — `PREREGISTRATION.md` §2,
   "Ambiguous SL/TP order → stop-first".

Running the gap phase first is not a softening of stop-first. A bar that opened
straight through the target and only later traded down to the stop did hit the
target first; booking that as a loss would be wrong, not conservative.

A position opened *during* the current bar gets **no gap phase** for its own
exits — it did not exist at that bar's open. Its exits are resolved by
stop-first against the whole bar range.

## 8. Position lifetime

User decision, 2026-08-25 (WP5 Q3). A position is held until its stop or target
fills — no time limit, across days and weekends. `close_now()` exists for the
WP10 session-end and day-end ablation variants; it exits at the current bar's
close, which is known at the instant the decision is made.

Positions still open when the data ends are **not booked**. Closing them at the
last available price would invent an exit the strategy never chose. They are
counted instead, so an implausible number of them is visible.

## 9. R-multiples and costs

`risk_per_unit` is frozen at submission as `|planned entry − stop loss|`.

Realised R is therefore degraded by gap fills and by costs rather than being
pinned to exactly −1.00 on every loser. Without this, a 2× cost-stress test
(required by `PREREGISTRATION.md` §5) would show nothing at all.

Costs never move a trigger level. A stop at 1800 fires when the market touches
1800 whatever the spread is; costs change the price obtained, not the price that
fires. `costs.CostModel` defines the interface; the concrete spread, commission
and slippage models are Work Package 7. The engine currently ships only
`ZeroCostModel`, which is for engine tests and never for a research result.

## 10. Equity accounting

User decision, 2026-08-25 (WP5 Q4). Every trade risks a fixed percentage of
**initial** equity — no compounding — so the equity curve stays a faithful
rescaling of the R sequence and edge cannot be confused with a lucky early run.
R-multiples remain the primary reporting unit in every case.

A non-compounding curve keeps subtracting the same cash risk after an account
would really have been wiped out, so equity can go negative. `ruin_point()`
reports where the account actually died, so ruin is never presented as merely a
bad final balance.

---

## What this engine deliberately does NOT do

- **No strategy logic.** No sweeps, no MSS/CHOCH, no FVGs, no bias. WP6 onward.
- **No costs.** Interface only. WP7.
- **No sub-bar reconstruction.** There is no data finer than 15 minutes, so the
  engine never guesses an intrabar path — it applies the conservative rule and
  says so.
- **No optimisation of anything.** The engine has no parameters to tune. Its
  only settable option, `whole_bar_validity`, is a documented ablation switch.

## Test coverage

90 tests, all passing:

| Area | What is pinned |
|---|---|
| `test_engine_clock` | trading day, session windows, 23h/25h DST days, invalid wall times |
| `test_engine_orders` | every fill rule and ambiguity case, on hand-computed numbers |
| `test_engine_marketview` | lookahead traps: cursor bounds, unclosed HTF bars, read-only arrays |
| `test_engine_resample` | aggregation vs constituents; zero difference vs native daily bars |
| `test_engine_known_answers` | end-to-end scenarios where +2R / −1R is known by arithmetic |
| `test_engine_on_real_data` | real gaps, no win above target, no manufactured edge |

The single most valuable test is
`test_information_free_entries_do_not_manufacture_edge`. A lookahead leak does
not raise an exception and does not look wrong — it just prints a better number.
An entry rule that carries no information must land at its theoretical
breakeven, and it does.
