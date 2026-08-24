# Research Decisions Log

Every material decision made during this project, with date and reasoning. Nothing here is
changed retroactively — new decisions are appended, old ones are never silently edited.

## 2026-08-24 — Project infrastructure decisions (Work Package 0/1)

**Decision:** Permanent project storage = local folder on user's Windows desktop
(`Desktop\XAUUSD_Research`), synced from the cloud research sandbox after each meaningful
checkpoint, PLUS a GitHub remote (private repo) once the user provides repo details and a
scoped Personal Access Token.
**Why:** The cloud sandbox this session runs in is ephemeral (can be reclaimed after inactivity).
A multi-week/month research project needs durable storage outside any single session.
**Status:** Local folder connected and in use. GitHub remote: pending user input.

**Decision:** Model selection is chosen per work package between Claude Sonnet 5 and Claude
Opus 5 only (no Haiku), per explicit user preference — user will pick which one to actually use
each time it is proposed.
**Why:** User's explicit instruction (2026-08-24).

**Decision:** MT5 / broker access is out of scope for the cloud research sandbox. Claude cannot
open, log into, or control MT5 from here (no remote-desktop/terminal control of the user's
machine — only file read/write via the desktop bridge). Historical data source (broker MT5
export vs. free public source) will be decided explicitly in Work Package 3.
**Why:** Technical limitation of the current tool access; must not be silently worked around.

## Pending decisions (to be resolved before relevant work package)

- WP2: exact London/NY tight & wide session windows (DST-safe), displacement lookback, ATR
  lookback, SL buffer, "major opposing liquidity" hierarchy, broker cost assumptions.
- WP3: MT5 broker export vs. free public XAUUSD data source.
