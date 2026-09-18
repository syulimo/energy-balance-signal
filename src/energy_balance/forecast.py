"""Can lagged flows forecast next week's reported crude stock change better than a
naive trailing mean? Walk-forward, refit every k weeks, no lookahead.

This is the P3 discipline applied to a commodity problem: the naive model is the
benchmark, the interval on the RMSE difference is the finding, and the answer
'no, the print is not forecastable from lagged flows' is a legitimate result.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import Ridge


def make_features(panel: pd.DataFrame, features: list[str], lags: list[int]) -> pd.DataFrame:
    X = pd.DataFrame(index=panel.index)
    for f in features:
        if f not in panel:
            continue
        for L in lags:
            X[f"{f}_l{L}"] = panel[f].shift(L)
    return X


def walk_forward(y: pd.Series, X: pd.DataFrame, train_window: int, refit_every: int, models: list[str], seed: int = 42) -> pd.DataFrame:
    """Out-of-sample predictions aligned to y.index. 'naive' = trailing mean of y over the window."""
    d = pd.concat([y.rename("y"), X], axis=1).dropna()
    preds = pd.DataFrame(index=d.index, columns=models, dtype=float)
    fitted = {}
    for k in range(train_window, len(d)):
        if (k - train_window) % refit_every == 0:
            tr = d.iloc[k - train_window:k]
            fitted = {}
            if "naive" in models: fitted["naive"] = float(tr["y"].mean())
            if "ridge" in models: fitted["ridge"] = Ridge(alpha=1.0).fit(tr.drop(columns="y"), tr["y"])
            if "gbm" in models: fitted["gbm"] = HistGradientBoostingRegressor(max_iter=200, max_depth=3, learning_rate=0.05, random_state=seed).fit(tr.drop(columns="y"), tr["y"])
        row = d.iloc[[k]].drop(columns="y")
        for m in models:
            preds.iloc[k, preds.columns.get_loc(m)] = fitted[m] if m == "naive" else float(fitted[m].predict(row)[0])
    return preds.dropna()


def compare_to_naive(y: pd.Series, preds: pd.DataFrame, draws: int = 1000, seed: int = 42) -> dict:
    """RMSE per model and a paired bootstrap on squared-error difference vs naive."""
    d = pd.concat([y.rename("y"), preds], axis=1).dropna()
    rng = np.random.default_rng(seed); out = {}
    e_naive = (d["y"] - d["naive"]) ** 2
    for m in preds.columns:
        e = (d["y"] - d[m]) ** 2
        diff = (e_naive - e).to_numpy()
        boots = np.array([rng.choice(diff, len(diff)).mean() for _ in range(draws)])
        out[m] = {"rmse": float(np.sqrt(e.mean())), "mse_gain_vs_naive": float(diff.mean()),
                  "ci_low": float(np.percentile(boots, 2.5)), "ci_high": float(np.percentile(boots, 97.5)), "n": int(len(d))}
    return out
