"""US distillate balance and the diesel crack.

Identity in kb per week:
    stock change = (production + imports - exports - product supplied) * 7
Crack in USD/bbl: ULSD (USD/gal) * 42 - WTI (USD/bbl).
"""
from __future__ import annotations

import pandas as pd

GAL_PER_BBL = 42.0


def implied_distillate_change(df: pd.DataFrame) -> pd.Series:
    for c in ("distillate_production", "distillate_imports", "distillate_exports", "distillate_product_supplied"):
        if c not in df:
            raise KeyError(f"missing column {c}")
    flows = df["distillate_production"] + df["distillate_imports"] - df["distillate_exports"] - df["distillate_product_supplied"]
    return (flows * 7.0).rename("distillate_implied_change_kb")


def reported_distillate_change(df: pd.DataFrame) -> pd.Series:
    return df["distillate_stocks"].diff().rename("distillate_reported_change_kb")


def days_of_supply(df: pd.DataFrame) -> pd.Series:
    return (df["distillate_stocks"] / df["distillate_product_supplied"]).rename("distillate_days_of_supply")


def diesel_crack(ulsd_usd_gal: pd.Series, wti_usd_bbl: pd.Series) -> pd.Series:
    return (ulsd_usd_gal * GAL_PER_BBL - wti_usd_bbl).rename("diesel_crack_usd_bbl")


def five_year_deviation(stocks: pd.Series) -> pd.Series:
    """Deviation from the same-week average of the prior five years, in percent.
    Matches how the EIA phrases it ('13 percent below the five-year average')."""
    s = stocks.copy()
    wk = s.index.isocalendar().week.astype(int)
    out = pd.Series(index=s.index, dtype=float, name="distillate_vs_5y_pct")
    for i, (d, v) in enumerate(s.items()):
        hist = s[(s.index < d - pd.Timedelta(days=360)) & (s.index >= d - pd.Timedelta(days=5 * 366)) & (wk == wk.iloc[i])]
        out.iloc[i] = (v / hist.mean() - 1.0) * 100.0 if len(hist) >= 3 else float("nan")
    return out
