"""Event-driven, strictly causal backtest engine (Work Package 5).

This package contains NO strategy logic. It provides only the machinery that
guarantees a strategy cannot see the future:

- `clock`      : bar timestamp semantics, 17:00-NY trading day, session windows
- `resample`   : higher-timeframe bar construction from the 15m base series
- `marketview` : the strategy's only window onto data; raises on lookahead
- `orders`     : order/position model + conservative fill simulation
- `costs`      : pluggable transaction-cost interface (implemented in WP7)
- `backtester` : the single forward-pass event loop

The engine's central invariant, verified empirically in WP4/WP5:

    A bar labelled with timestamp T covers the half-open interval [T, T+D)
    and its OHLC is UNKNOWN until T+D.

Confirmed against the data (2992/2992 h1 bars matched forward aggregation of
m15 bars, 0/2992 matched backward aggregation), so the source uses OPEN-time
labels. Treating T as a close-time label would have introduced a silent
one-bar lookahead on every single decision.
"""
