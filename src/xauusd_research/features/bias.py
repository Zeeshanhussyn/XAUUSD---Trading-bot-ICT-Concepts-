"""Higher-timeframe directional bias from swing structure.

FOUNDING_BRIEF.md says "Daily = PRIMARY bias, 4H = CONFIRMATION" and refers to
the Daily bias being "clear", but never says what clear means. Resolved with the
user on 2026-08-25 (WP6 Q1) and recorded as a preregistration amendment:

    bullish  = higher high AND higher low
    bearish  = lower high  AND lower low
    neutral  = anything else, including not enough swings yet

Both conditions are required. A higher high with a lower low is an expanding
range, not a trend, and is correctly neutral. Neutral Daily blocks the trade
outright — "Daily primary" means Daily gets a veto.

This reuses the same fractal definition as everything else, so it introduces no
new parameter. It does inherit the fractal's confirmation lag, and on the Daily
that lag is real: with N=2 a daily swing is not knowable until two more daily
bars have closed. That is the honest cost of not looking ahead, and it is why
the bias here will sometimes disagree with what a human would call obvious from
the chart.

The FLEXIBLE combination rule is the brief's own (baseline); STRICT is the
planned WP10 comparison.
"""

from __future__ import annotations

from enum import Enum

import numpy as np

from .swings import Swing, SwingSeries, SwingType


class Bias(Enum):
    BULLISH = 1
    BEARISH = -1
    NEUTRAL = 0

    @property
    def opposite(self) -> "Bias":
        if self is Bias.BULLISH:
            return Bias.BEARISH
        if self is Bias.BEARISH:
            return Bias.BULLISH
        return Bias.NEUTRAL


def _bias_from(highs: list[Swing], lows: list[Swing]) -> Bias:
    if len(highs) < 2 or len(lows) < 2:
        return Bias.NEUTRAL
    higher_high = highs[-1].price > highs[-2].price
    higher_low = lows[-1].price > lows[-2].price
    lower_high = highs[-1].price < highs[-2].price
    lower_low = lows[-1].price < lows[-2].price
    if higher_high and higher_low:
        return Bias.BULLISH
    if lower_high and lower_low:
        return Bias.BEARISH
    return Bias.NEUTRAL


def structural_bias(swings: SwingSeries, bar_index: int) -> Bias:
    """Bias implied by the swings confirmed as of `bar_index` on that series."""
    return _bias_from(
        swings.last_n(bar_index, SwingType.HIGH, 2),
        swings.last_n(bar_index, SwingType.LOW, 2),
    )


def bias_by_bar(swings: SwingSeries, n_bars: int) -> list[Bias]:
    """Bias at every bar of a series, in one causal forward sweep.

    Swings of one kind are always confirmed in the same order as their own bar
    indices (confirmation is index + n), so accumulating them in confirmation
    order also keeps them in chart order — which is what "the last two swing
    highs" has to mean.
    """
    out: list[Bias] = []
    highs: list[Swing] = []
    lows: list[Swing] = []
    ptr = 0
    ordered = swings.all
    for j in range(n_bars):
        while ptr < len(ordered) and ordered[ptr].confirmed_at <= j:
            s = ordered[ptr]
            (highs if s.kind is SwingType.HIGH else lows).append(s)
            ptr += 1
        out.append(_bias_from(highs, lows))
    return out


def project_to_base(htf_bias: list[Bias], n_closed: np.ndarray) -> list[Bias]:
    """Map a higher-timeframe bias onto base bars, strictly causally.

    `n_closed[i]` is how many HTF bars have closed by the time base bar `i`
    closes (the same quantity `MarketView` precomputes). The newest usable HTF
    bar is therefore `n_closed[i] - 1`; before any HTF bar has closed the bias
    is neutral, not "the first one".
    """
    out: list[Bias] = []
    for k in n_closed:
        j = int(k) - 1
        out.append(htf_bias[j] if 0 <= j < len(htf_bias) else Bias.NEUTRAL)
    return out


# --------------------------------------------------------------------------
# Combining Daily and 4H
# --------------------------------------------------------------------------


def htf_gate_flexible(daily: Bias, h4: Bias) -> Bias:
    """Baseline rule. Returns the permitted trade direction, or NEUTRAL for none.

    From FOUNDING_BRIEF.md, "HTF BIAS": Daily is primary; a 4H that is neutral
    or in transition may still allow the trade; a 4H that clearly opposes blocks
    it. The brief's extra condition — that a Daily-clear/4H-neutral trade needs
    15m MSS/CHOCH plus displacement to confirm the Daily direction — is
    satisfied by construction, since the baseline setup requires exactly that
    for every trade regardless.
    """
    if daily is Bias.NEUTRAL:
        return Bias.NEUTRAL
    if h4 is daily.opposite:
        return Bias.NEUTRAL
    return daily


def htf_gate_strict(daily: Bias, h4: Bias) -> Bias:
    """WP10 comparison: Daily and 4H must both be clear and agree."""
    if daily is Bias.NEUTRAL or daily is not h4:
        return Bias.NEUTRAL
    return daily
