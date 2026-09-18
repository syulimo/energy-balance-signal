"""Does the signal say anything about forward WTI returns? Quantile sort plus a
bootstrap on the top-minus-bottom spread. No model, no fitting, so there is
nothing to overfit except the choice of quantile count, which is fixed in config."""
from __future__ import annotations

import numpy as np
import pandas as pd


def forward_returns(close: pd.Series, horizons: list[int]) -> pd.DataFrame:
    return pd.DataFrame({f"fwd_{h}w": close.shift(-h) / close - 1.0 for h in horizons})


def quantile_returns(signal: pd.Series, fwd: pd.DataFrame, q: int = 5) -> pd.DataFrame:
    d = pd.concat([signal.rename("sig"), fwd], axis=1).dropna()
    d["q"] = pd.qcut(d["sig"].rank(method="first"), q, labels=range(1, q + 1))
    return d.groupby("q")[fwd.columns].mean()


def bootstrap_spread(signal: pd.Series, fwd: pd.Series, q: int = 5, draws: int = 1000, seed: int = 42) -> dict:
    """Top quantile minus bottom quantile mean forward return, with a bootstrap
    interval over weeks. If the interval crosses zero, say so."""
    d = pd.concat([signal.rename("sig"), fwd.rename("r")], axis=1).dropna()
    d["q"] = pd.qcut(d["sig"].rank(method="first"), q, labels=range(1, q + 1))
    top, bot = d.loc[d["q"] == q, "r"].to_numpy(), d.loc[d["q"] == 1, "r"].to_numpy()
    rng = np.random.default_rng(seed)
    spreads = np.array([rng.choice(top, len(top)).mean() - rng.choice(bot, len(bot)).mean() for _ in range(draws)])
    return {"spread": float(top.mean() - bot.mean()), "ci_low": float(np.percentile(spreads, 2.5)),
            "ci_high": float(np.percentile(spreads, 97.5)), "n_top": int(len(top)), "n_bot": int(len(bot)),
            "p_two_sided": float(2 * min((spreads <= 0).mean(), (spreads >= 0).mean()))}


def bootstrap_slope(signal: pd.Series, fwd: pd.Series, draws: int = 1000, seed: int = 42) -> dict:
    """OLS slope of forward return on the signal with a bootstrap interval over weeks.
    Used for regimes too short for a quintile sort: five buckets of six weeks is noise,
    a slope on thirty weeks is at least one number with an honest interval."""
    d = pd.concat([signal.rename("sig"), fwd.rename("r")], axis=1).dropna()
    x, y = d["sig"].to_numpy(), d["r"].to_numpy()
    def slope(ix): 
        xv = x[ix] - x[ix].mean()
        return float((xv * (y[ix] - y[ix].mean())).sum() / (xv ** 2).sum()) if (xv ** 2).sum() > 0 else float("nan")
    rng = np.random.default_rng(seed); n = len(d)
    boots = np.array([slope(rng.integers(0, n, n)) for _ in range(draws)]); boots = boots[~np.isnan(boots)]
    return {"slope": slope(np.arange(n)), "ci_low": float(np.percentile(boots, 2.5)), "ci_high": float(np.percentile(boots, 97.5)), "n": int(n)}
