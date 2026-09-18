"""Weekly US crude balance.

Identity, in thousand barrels per week:
    stock change = (production + imports - exports - refinery inputs) * 7
plus an "adjustment" the EIA publishes because the identity never closes exactly.
The reported stock change is the number the market trades on Wednesday. The
implied change from flows is what a naive analyst would forecast. The gap between
reported and a trailing consensus proxy is the surprise.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

KB_D_TO_KB_WEEK = 7.0


def _col(df, *names):
    for n in names:
        if n in df: return df[n]
    raise KeyError(f"missing column, tried {names}")


def implied_stock_change(df: pd.DataFrame) -> pd.Series:
    """From flow columns in kb/d to an implied weekly stock change in kb."""
    flows = _col(df, "production", "crude_production") + _col(df, "imports", "crude_imports") - _col(df, "exports", "crude_exports") - df["refinery_inputs"]
    return (flows * KB_D_TO_KB_WEEK).rename("implied_change_kb")


def reported_stock_change(df: pd.DataFrame) -> pd.Series:
    return df["crude_stocks_ex_spr"].diff().rename("reported_change_kb")


def surprise(reported: pd.Series, window: int = 8, method: str = "rolling_mean") -> pd.Series:
    """Reported change minus a naive consensus proxy.

    The proxy is deliberately dumb: the trailing mean of reported changes,
    lagged one week so it uses only past prints. Real consensus (Reuters,
    Bloomberg surveys) is better and is the obvious upgrade; it is not free.
    """
    if method != "rolling_mean":
        raise ValueError("only rolling_mean is implemented")
    proxy = reported.shift(1).rolling(window, min_periods=window).mean()
    return (reported - proxy).rename("surprise_kb")


def adjustment(df: pd.DataFrame) -> pd.Series:
    """Reported minus implied: the EIA 'unaccounted-for crude'. Large persistent
    values mean the flow data are mis-measured; worth plotting before trusting anything."""
    return (reported_stock_change(df) - implied_stock_change(df)).rename("adjustment_kb")
