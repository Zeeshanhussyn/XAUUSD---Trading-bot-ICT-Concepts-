"""Volatility measures used by the pre-registered rules.

ATR(14) appears in three places in `PREREGISTRATION.md` §2: the stop-loss buffer
(0.1 x ATR), displacement Variant B (range >= 1.5 x ATR), and the FVG size
filters (>= 0.25 / 0.50 ATR).

Causality: `atr[i]` uses bars up to and including `i`, and bar `i` has closed by
the time anything reads it. True range needs the previous close, so `atr[0]` is
undefined and the first `period` values are NaN rather than a partial average
quietly standing in for a full one.
"""

from __future__ import annotations

import numpy as np

from ..config import BASELINE_ATR_PERIOD


def true_range(high: np.ndarray, low: np.ndarray, close: np.ndarray) -> np.ndarray:
    """Wilder's true range. `tr[0]` is NaN — there is no previous close."""
    high = np.asarray(high, dtype=float)
    low = np.asarray(low, dtype=float)
    close = np.asarray(close, dtype=float)
    prev_close = np.concatenate([[np.nan], close[:-1]])
    return np.maximum(
        high - low,
        np.maximum(np.abs(high - prev_close), np.abs(low - prev_close)),
    )


def atr(
    high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = BASELINE_ATR_PERIOD
) -> np.ndarray:
    """Wilder-smoothed ATR — the standard definition, not a simple moving average.

    Seeded with the simple mean of the first `period` true ranges, then smoothed
    as `atr[i] = (atr[i-1] * (period - 1) + tr[i]) / period`.
    """
    if period < 1:
        raise ValueError("period must be >= 1")
    tr = true_range(high, low, close)
    out = np.full(len(tr), np.nan)
    if len(tr) <= period:
        return out

    # tr[0] is NaN, so the seed window is tr[1 : period+1].
    seed = float(np.mean(tr[1 : period + 1]))
    out[period] = seed
    for i in range(period + 1, len(tr)):
        out[i] = (out[i - 1] * (period - 1) + tr[i]) / period
    return out
