"""The strategy's only window onto market data — structurally incapable of lookahead.

The engine advances a private cursor; a strategy can only ever ask for "the last
N closed bars". There is no public method that returns a future bar, and every
slice is bounded by the cursor rather than by a caller-supplied end index, so a
strategy cannot look forward even by mistake.

Higher-timeframe alignment is precomputed once, causally: for base bar *i*, the
number of HTF bars whose **close time** is <= the base bar's close time. A 4H
bar that is still forming is invisible until the instant it completes.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .resample import BarSeries


class LookaheadError(RuntimeError):
    """Raised when something tries to read data that has not happened yet."""


@dataclass(frozen=True)
class Window:
    """A read-only view of the most recent closed bars of one series.

    Arrays are ordered oldest → newest; index -1 is the most recently closed
    bar. All arrays are non-writeable numpy views: a strategy cannot mutate the
    underlying data and thereby corrupt later bars.
    """

    open_time: pd.DatetimeIndex
    close_time: pd.DatetimeIndex
    open: np.ndarray
    high: np.ndarray
    low: np.ndarray
    close: np.ndarray

    def __len__(self) -> int:
        return len(self.close)

    @property
    def empty(self) -> bool:
        return len(self.close) == 0


class MarketView:
    """Causal, cursor-bounded access to the base series and its higher timeframes."""

    def __init__(self, base: BarSeries, htf: dict[str, BarSeries] | None = None):
        self._base = base
        self._htf = dict(htf or {})
        self._i = -1

        self._base_arrays = _arrays(base.df)
        self._htf_arrays = {k: _arrays(v.df) for k, v in self._htf.items()}

        # n_closed[name][i] = how many bars of `name` have closed by the time
        # base bar i closes. searchsorted(side="right") gives exactly that, and
        # ties (HTF close == base close) count as closed, which is correct: both
        # bars complete at the same instant.
        base_close = base.close_time.values
        self._n_closed = {
            name: np.searchsorted(series.close_time.values, base_close, side="right")
            for name, series in self._htf.items()
        }
        for name, series in self._htf.items():
            if (series.close_time.values[:-1] > series.close_time.values[1:]).any():
                raise ValueError(f"{name}: close times not sorted")

    # -- engine-facing -----------------------------------------------------

    def _advance_to(self, i: int) -> None:
        self._i = i

    # -- strategy-facing ---------------------------------------------------

    @property
    def now(self) -> pd.Timestamp:
        """The current instant: the close time of the most recently closed base bar."""
        self._require_started()
        return self._base.close_time[self._i]

    @property
    def timeframes(self) -> tuple[str, ...]:
        return ("m15",) + tuple(self._htf)

    def bars(self, timeframe: str, n: int) -> Window:
        """Return the last `n` **closed** bars of `timeframe` (oldest → newest).

        Fewer than `n` bars are returned near the start of the data; the caller
        must handle a short window rather than assume it got `n`.
        """
        self._require_started()
        if n <= 0:
            raise ValueError("n must be >= 1")

        if timeframe == "m15":
            end = self._i + 1
            arrays = self._base_arrays
            series = self._base
        else:
            if timeframe not in self._htf:
                raise ValueError(
                    f"unknown timeframe {timeframe!r}; available: {self.timeframes}"
                )
            end = int(self._n_closed[timeframe][self._i])
            arrays = self._htf_arrays[timeframe]
            series = self._htf[timeframe]

        start = max(0, end - n)
        window = Window(
            open_time=series.df.index[start:end],
            close_time=series.close_time[start:end],
            open=arrays["open"][start:end],
            high=arrays["high"][start:end],
            low=arrays["low"][start:end],
            close=arrays["close"][start:end],
        )
        # Defence in depth: the cursor arithmetic above should make this
        # impossible, but a wrong close_time upstream would not be caught by it.
        if len(window) and window.close_time[-1] > self.now:
            raise LookaheadError(
                f"{timeframe} window ends at {window.close_time[-1]} "
                f"but now is {self.now}"
            )
        return window

    def last(self, timeframe: str) -> Window:
        """The single most recently closed bar of `timeframe` (may be empty)."""
        return self.bars(timeframe, 1)

    def _require_started(self) -> None:
        if self._i < 0:
            raise LookaheadError("market view has not been advanced to a bar yet")


def _arrays(df: pd.DataFrame) -> dict[str, np.ndarray]:
    out = {}
    for col in ("open", "high", "low", "close"):
        a = np.ascontiguousarray(df[col].to_numpy(dtype=float))
        a.setflags(write=False)
        out[col] = a
    return out
