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

## Pending decisions (to be resolved before relevant work package)

- WP3 (open): how to handle the 2022-03 → 2026-08 data gap — see next message to user for the
  exact A/B choice (use 2012-2022 as the full working window and holdout, vs. user manually fills
  the recent gap via Dukascopy chunked downloads so the holdout reflects the current market
  regime).
