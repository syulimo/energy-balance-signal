"""Hormuz reopening scenarios, stated as changes relative to today.

Why relative: the IEA annual averages already include the disruption, so adding
recovered flows to them double counts. The tool instead starts from the current
month and asks what changes if Gulf supply that is still shut in comes back.

Every input is either an IEA number with a release date (see data/global_balance_monthly.csv)
or a labelled assumption. Outputs are monthly incremental balance vs today (mb/d, plus
means builds) and cumulative stock change vs a no-change baseline (mb).
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def ramp(total: float, fraction: float, months_to_full: int, horizon: int = 12) -> np.ndarray:
    """Recovered supply path: linear ramp to fraction * total over months_to_full, then flat."""
    target = fraction * total
    path = np.linspace(0.0, target, months_to_full + 1)[1:]
    return np.r_[path, np.full(max(horizon - months_to_full, 0), target)][:horizon]


def run_scenarios(cfg: dict) -> pd.DataFrame:
    s = cfg["scenario"]; rows = []
    shut_in = s["gulf_shut_in_current_mbd"]                       # IEA, still below pre-war
    for frac in s["reopening_fractions"]:
        for m in s["months_to_full"]:
            recovered = ramp(shut_in, frac, m)                                       # mb/d supply back
            demand_back = s["demand_recovery_per_mbd_supply"] * recovered            # assumption
            us_giveback = s["us_export_giveback_per_mbd_supply"] * recovered         # assumption
            incremental_balance = recovered - demand_back - us_giveback              # mb/d vs today
            cum = np.cumsum(incremental_balance * 30.4)
            rows.append({"reopening_fraction": frac, "months_to_full": m,
                         "supply_back_m12_mbd": round(float(recovered[-1]), 2),
                         "demand_back_m12_mbd": round(float(demand_back[-1]), 2),
                         "incremental_balance_m6_mbd": round(float(incremental_balance[5]), 2),
                         "incremental_balance_m12_mbd": round(float(incremental_balance[-1]), 2),
                         "cum_stock_change_vs_today_12m_mb": round(float(cum[-1]), 0)})
    return pd.DataFrame(rows)
