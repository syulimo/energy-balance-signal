"""Regime labels from a dated events file. Each event sets the regime from its date
until the next event with a different label. 'pre' before the first event."""
from __future__ import annotations

import pandas as pd


def load_events(path: str) -> pd.DataFrame:
    ev = pd.read_csv(path, parse_dates=["date"]).sort_values("date")
    if not {"date", "event", "regime", "source"} <= set(ev.columns):
        raise KeyError("events.csv needs date, event, regime, source")
    return ev


def regime_series(index: pd.DatetimeIndex, events: pd.DataFrame) -> pd.Series:
    changes = events.loc[events["regime"].ne(events["regime"].shift()), ["date", "regime"]]
    s = pd.Series("pre", index=index, name="regime")
    for d, lab in zip(changes["date"], changes["regime"]):
        s.loc[s.index >= d] = lab
    return s
