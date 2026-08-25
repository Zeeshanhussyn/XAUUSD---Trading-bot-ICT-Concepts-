"""Data integrity checks for Work Package 4.

Every function here is read-only and returns plain Python / pandas structures suitable for
writing into DATA_INTEGRITY_REPORT.md. Nothing here mutates the input DataFrame.
"""

from dataclasses import dataclass, field

import pandas as pd


@dataclass
class IntegrityResult:
    timeframe: str
    n_rows: int
    date_min: pd.Timestamp
    date_max: pd.Timestamp
    n_duplicate_timestamps: int
    n_bad_ohlc_rows: int
    n_nonpositive_price_rows: int
    n_null_rows: int
    price_min: float
    price_max: float
    weekend_gaps: int
    holiday_gaps_3plus_days: list = field(default_factory=list)
    suspicious_midweek_gaps: list = field(default_factory=list)
    extreme_bar_moves: list = field(default_factory=list)


def check_timeframe(df: pd.DataFrame, timeframe: str, expected_bar_minutes: int) -> IntegrityResult:
    n_rows = len(df)
    dup = df.index.duplicated().sum()
    bad_ohlc = int(
        (
            (df["high"] < df["low"])
            | (df["close"] > df["high"])
            | (df["close"] < df["low"])
            | (df["open"] > df["high"])
            | (df["open"] < df["low"])
        ).sum()
    )
    nonpositive = int((df[["open", "high", "low", "close"]] <= 0).any(axis=1).sum())
    nulls = int(df.isnull().sum().sum())

    diffs = df.index.to_series().diff().dropna()
    expected = pd.Timedelta(minutes=expected_bar_minutes)

    weekend_gaps = int((diffs > pd.Timedelta(hours=40)).sum())
    holiday_gaps = diffs[diffs > pd.Timedelta(days=3)]
    holiday_list = [
        {"before": str(diffs.index[i] - diffs.iloc[i]), "after": str(diffs.index[i]), "gap": str(g)}
        for i, g in zip(range(len(diffs)), diffs)
        if g > pd.Timedelta(days=3)
    ]
    # midweek gaps: bigger than expected bar spacing but well under a weekend (data outage candidates)
    midweek = diffs[(diffs > expected * 4) & (diffs <= pd.Timedelta(hours=40))]
    midweek_list = []
    idx_list = df.index
    diff_idx = diffs.index
    for ts, g in diffs.items():
        if expected * 4 < g <= pd.Timedelta(hours=40):
            midweek_list.append({"gap_end": str(ts), "gap_size": str(g)})

    # extreme single-bar moves: >8% of price in one bar (gold rarely moves this much intrabar
    # outside historic shocks — flag for manual look, not necessarily an error)
    pct_move = ((df["high"] - df["low"]) / df["close"]).abs()
    extreme = df[pct_move > 0.08]
    extreme_list = [
        {"time": str(ts), "pct_range": round(float(p), 4)}
        for ts, p in pct_move[pct_move > 0.08].items()
    ]

    return IntegrityResult(
        timeframe=timeframe,
        n_rows=n_rows,
        date_min=df.index.min(),
        date_max=df.index.max(),
        n_duplicate_timestamps=int(dup),
        n_bad_ohlc_rows=bad_ohlc,
        n_nonpositive_price_rows=nonpositive,
        n_null_rows=nulls,
        price_min=float(df["close"].min()),
        price_max=float(df["close"].max()),
        weekend_gaps=weekend_gaps,
        holiday_gaps_3plus_days=holiday_list[:30],
        suspicious_midweek_gaps=midweek_list[:30],
        extreme_bar_moves=extreme_list[:30],
    )
