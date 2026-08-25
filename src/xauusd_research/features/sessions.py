"""Which trading session each 15m bar belongs to, and where that session ends.

Needed because the user's WP6 Q3 answer ties a sweep's life to the session it
happened in: a sweep stays live until the end of the same session, and a sweep
outside any session window is not tracked at all — it would have no session in
which to expire.

A bar counts as inside a session only if it lies **entirely** within the window
(`session_start <= open_time` and `close_time <= session_end`). The baseline
windows are whole hours and half-hours, so 15-minute bars tile them exactly and
nothing is lost to this rule; it exists so a bar straddling the boundary can
never be silently claimed by a session it only partly overlaps.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from ..engine.clock import bar_close_index, session_bounds
from ..engine.resample import ny_session_keys


@dataclass(frozen=True)
class SessionMap:
    """Per-bar session membership for the base series."""

    #: Session name per bar, or "" for bars outside every tracked session.
    name: np.ndarray
    #: Index of the last bar of that bar's session; -1 outside a session.
    last_index: np.ndarray
    #: Trading-day label per bar.
    trading_day: np.ndarray

    def __len__(self) -> int:
        return len(self.name)

    def in_session(self, i: int) -> bool:
        return bool(self.name[i])


def build_session_map(
    index: pd.DatetimeIndex, sessions: tuple[str, ...] = ("london_tight", "ny_tight")
) -> SessionMap:
    """Label every bar of `index` with the tracked session it falls inside."""
    close_time = bar_close_index(index, "m15")
    day_label, _ = ny_session_keys(index)

    name = np.full(len(index), "", dtype=object)
    last_index = np.full(len(index), -1, dtype=int)

    open_values = index.values
    close_values = close_time.values

    # Both arrays are sorted, so each session resolves to one contiguous slice:
    # `open_time >= start` bounds it below and `close_time <= end` above. Doing
    # this with searchsorted rather than a full-array mask per day matters —
    # there are ~2500 days and ~230k bars.
    for day in pd.unique(day_label):
        d = pd.Timestamp(day).date()
        for session in sessions:
            start, end = session_bounds(d, session)
            lo = int(np.searchsorted(open_values, start.to_datetime64(), side="left"))
            hi = int(np.searchsorted(close_values, end.to_datetime64(), side="right"))
            if hi <= lo:
                continue
            name[lo:hi] = session
            last_index[lo:hi] = hi - 1

    return SessionMap(name=name, last_index=last_index, trading_day=np.asarray(day_label))
