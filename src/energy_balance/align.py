"""Release-date alignment. The single most common leak in commodity signals is
using Wednesday's inventory print for a return window that started Monday.

EIA: week ending Friday t, released Wednesday t+5 (Thursday after a Monday holiday;
data/release_calendar.csv overrides the default when present).
CFTC: positions Tuesday t+4, released Friday t+7 at 15:30 ET, after the settlement, so usable from t+8.
"""
from __future__ import annotations

import pandas as pd

EIA_LAG_DAYS = 5
COT_LAG_DAYS = 8


def eia_public_dates(index: pd.DatetimeIndex, calendar: pd.DataFrame | None = None) -> pd.Series:
    pub = pd.Series(index + pd.Timedelta(days=EIA_LAG_DAYS), index=index)
    if calendar is not None and len(calendar):
        cal = calendar.set_index("week_ending")["release_date"]
        for wk, rel in cal.items():
            if wk in pub.index: pub.loc[wk] = rel
    return pub


def align_release_dates(eia: pd.DataFrame, cot: pd.DataFrame, price: pd.DataFrame, calendar: pd.DataFrame | None = None) -> pd.DataFrame:
    """One row per price Friday with the latest EIA and COT rows public before that close."""
    e = eia.copy(); e["public"] = eia_public_dates(e.index, calendar).values
    c = cot.copy(); c["public"] = c.index + pd.Timedelta(days=COT_LAG_DAYS)
    p = price.sort_index().copy(); p["asof"] = p.index
    out = pd.merge_asof(p.sort_values("asof"), e.sort_values("public"), left_on="asof", right_on="public", direction="backward", suffixes=("", "_eia"))
    out = pd.merge_asof(out.sort_values("asof"), c.sort_values("public"), left_on="asof", right_on="public", direction="backward", suffixes=("", "_cot"))
    out.index = p.index
    return out.drop(columns=[c for c in out.columns if c.startswith("public") or c == "asof"])
