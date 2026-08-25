"""ICT/SMC feature detectors (Work Package 6).

Each module here detects one thing and knows nothing about trading. Assembly
into a strategy is Work Package 9.

The rule every module in this package obeys, from FOUNDING_BRIEF.md:

    "A swing requiring future confirmation becomes usable ONLY after those
    confirmation bars have actually closed. Never allow future-confirmed swings
    to exist earlier in the simulation."

So every detector returns, alongside each detected object, the bar index at
which that object first becomes **knowable**. Consumers filter on that index —
never on the index where the pattern visually "is".
"""
