"""Parsers for the two public feeds. Kept apart from the fetch scripts so that the
parsing is unit tested without a network call or an API key.

EIA API v2: the /v2/seriesid/ route accepts APIv1 series ids such as PET.WCESTUS1.W
(weekly) and PET.RWTC.D (daily) and returns rows with 'period' and 'value' (a string).
CFTC: the disaggregated futures-only report, either from the Public Reporting
Environment (lower-case field names) or from the yearly text files (mixed case).
Markets are matched on the CFTC contract market code, which is stable across the
2022 renaming of the WTI contract.
"""
from __future__ import annotations

import pandas as pd

WTI_CODE = "067651"    # NYMEX light sweet crude (named WTI-PHYSICAL since 2022)
ULSD_CODE = "022651"   # NYMEX NY Harbor ULSD


def eia_series_id(short_id: str, frequency: str) -> str:
    """WCESTUS1, weekly -> PET.WCESTUS1.W. Ids that already carry a prefix pass through."""
    if short_id.upper().startswith("PET."):
        return short_id
    suffix = {"weekly": "W", "daily": "D", "monthly": "M"}[frequency]
    return f"PET.{short_id}.{suffix}"


def eia_rows_to_series(rows: list[dict], name: str, start: str | None = None) -> pd.Series:
    """Rows from response.data -> float series indexed by date, ascending, duplicates dropped."""
    if not rows:
        raise ValueError(f"EIA returned no rows for {name}")
    df = pd.DataFrame(rows)
    if not {"period", "value"} <= set(df.columns):
        raise KeyError(f"EIA rows for {name} lack period/value; got {sorted(df.columns)}")
    s = pd.Series(pd.to_numeric(df["value"], errors="coerce").to_numpy(), index=pd.to_datetime(df["period"]), name=name)
    s = s[~s.index.duplicated(keep="last")].sort_index().dropna()
    return s.loc[start:] if start else s


def _find(cols: list[str], *needles: str) -> str:
    low = {c.lower().replace("-", "_"): c for c in cols}
    for key, orig in low.items():
        if all(n in key for n in needles):
            return orig
    raise KeyError(f"no column matching {needles} in {cols[:8]}...")


def cot_frame(df: pd.DataFrame, contract_code: str) -> pd.DataFrame:
    """Disaggregated COT rows -> mm_long, mm_short, open_interest for one contract.

    The index is the reference Friday before the Tuesday position date (Tuesday minus
    four days), which is the convention align.py expects: public at index plus 8 days.
    """
    code_col = _find(list(df.columns), "contract_market_code")
    date_col = _find(list(df.columns), "yyyy")
    sub = df[df[code_col].astype(str).str.strip().str.zfill(6) == contract_code]
    if sub.empty:
        raise ValueError(f"no COT rows for contract code {contract_code}")
    out = pd.DataFrame({
        "mm_long": pd.to_numeric(sub[_find(list(df.columns), "m_money", "long_all")], errors="coerce").to_numpy(),
        "mm_short": pd.to_numeric(sub[_find(list(df.columns), "m_money", "short_all")], errors="coerce").to_numpy(),
        "open_interest": pd.to_numeric(sub[_find(list(df.columns), "open_interest_all")], errors="coerce").to_numpy(),
    }, index=pd.to_datetime(sub[date_col]).dt.tz_localize(None).dt.normalize() - pd.Timedelta(days=4))
    out.index.name = "date"
    return out[~out.index.duplicated(keep="last")].sort_index()
