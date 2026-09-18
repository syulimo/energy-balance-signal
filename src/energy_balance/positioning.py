"""CFTC managed money positioning in NYMEX WTI."""
from __future__ import annotations

import pandas as pd


def managed_money_net(cot: pd.DataFrame) -> pd.Series:
    """Net length = long minus short, in contracts."""
    for c in ("mm_long", "mm_short"):
        if c not in cot:
            raise KeyError(f"missing column {c}")
    return (cot["mm_long"] - cot["mm_short"]).rename("mm_net")


def zscore(s: pd.Series, window: int = 52) -> pd.Series:
    """Rolling z-score using only past values (shifted), so the score at t
    does not include t in its own mean and std."""
    past = s.shift(1)
    return ((s - past.rolling(window, min_periods=window).mean()) / past.rolling(window, min_periods=window).std()).rename(f"{s.name}_z")
