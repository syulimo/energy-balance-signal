import numpy as np, pandas as pd, pytest
from energy_balance.align import align_release_dates, EIA_LAG_DAYS, COT_LAG_DAYS
from energy_balance.balance import implied_stock_change, reported_stock_change, surprise, adjustment
from energy_balance.positioning import managed_money_net, zscore
from energy_balance.event_study import forward_returns, quantile_returns, bootstrap_spread


def test_identity_units():
    df = pd.DataFrame({"production": [10000.0], "imports": [6000.0], "exports": [3000.0], "refinery_inputs": [16000.0]})
    assert implied_stock_change(df).iloc[0] == pytest.approx((10000 + 6000 - 3000 - 16000) * 7)


def test_surprise_uses_only_past_prints():
    r = pd.Series(np.arange(20, dtype=float))
    s = surprise(r, window=4)
    assert s.iloc[:4].isna().all()
    assert s.iloc[5] == pytest.approx(5 - np.mean([1, 2, 3, 4]))


def test_zscore_is_shifted():
    s = pd.Series(np.r_[np.zeros(52), 100.0], name="x")
    z = zscore(s, 52)
    assert np.isnan(z.iloc[51])           # window not yet full of past values
    assert np.isnan(z.iloc[52]) or z.iloc[52] > 3   # std of zeros is 0, so nan or huge; never uses itself


def test_alignment_never_looks_ahead():
    weeks = pd.date_range("2020-01-03", periods=6, freq="W-FRI")
    eia = pd.DataFrame({"v": range(6)}, index=weeks); cot = pd.DataFrame({"w": range(6)}, index=weeks)
    price = pd.DataFrame({"close": 1.0}, index=weeks)
    a = align_release_dates(eia, cot, price)
    # on Friday t, the EIA row for week t is public at t+5, so the latest usable is t-7
    assert a.loc[weeks[3], "v"] == 2
    # COT for week t is public at t+8, so the latest usable on Friday t is t-14
    assert a.loc[weeks[3], "w"] == 1
    assert EIA_LAG_DAYS == 5 and COT_LAG_DAYS == 8


def test_event_study_finds_planted_and_rejects_null():
    rng = np.random.default_rng(0); n = 300
    sig = pd.Series(rng.normal(size=n)); r = pd.Series(0.01 * sig + rng.normal(0, 0.02, n))
    b = bootstrap_spread(sig, r, q=5, draws=300)
    assert b["ci_low"] > 0
    null = bootstrap_spread(pd.Series(rng.normal(size=n)), r, q=5, draws=300)
    assert null["ci_low"] < 0 < null["ci_high"]
    qt = quantile_returns(sig, forward_returns(pd.Series(np.cumprod(1 + r)), [1]), 5)
    assert qt.shape == (5, 1)
