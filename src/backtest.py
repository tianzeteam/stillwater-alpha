"""Low-volatility portfolio backtest with liquidity screen on Bitget rTokens."""
import numpy as np
import pandas as pd

TRADING_DAYS = 365  # rToken trades 7x24


def build_weights(vol_row: pd.Series, liq_row: pd.Series, q: float = 0.2,
                  liq_quantile: float = 0.5, min_names: int = 15) -> pd.Series:
    """Equal-weight long portfolio of the lowest-vol quintile among liquid names.
    vol_row/liq_row: cross-sectional Series for a single rebalance date."""
    s = vol_row.dropna()
    lq = liq_row.dropna()
    syms = s.index.union(lq.index)
    liquid = lq[lq >= lq.quantile(1 - liq_quantile)].index if len(lq) > 10 else s.index
    s = s[s.index.isin(liquid)]
    if len(s) < min_names:
        return pd.Series(0.0, index=syms)
    k = max(3, int(len(s) * q))
    w = pd.Series(0.0, index=syms)
    w[s.nsmallest(k).index] = 1.0 / k
    return w


def run(vol_sig: pd.DataFrame, rets: pd.DataFrame, liq: pd.DataFrame,
        rebal_days: int = 7, start_idx: int = 60, cost_bps: float = 10.0):
    """Weekly-rebalanced low-vol portfolio. Returns (net_returns, weights, turnover)."""
    dates = rets.index[start_idx:]
    W = pd.DataFrame(0.0, index=dates, columns=rets.columns)
    cur = pd.Series(0.0, index=rets.columns)
    for i, dt in enumerate(dates):
        if i % rebal_days == 0:
            cur = build_weights(vol_sig.loc[dt], liq.loc[dt])
        W.loc[dt] = cur
    gross = (W.shift(1) * rets.loc[dates]).sum(axis=1)
    turnover = W.diff().abs().sum(axis=1).fillna(0)
    return gross - turnover * cost_bps / 1e4, W, turnover


def metrics(r: pd.Series) -> dict:
    r = r.dropna()
    if len(r) < 5 or r.std() == 0:
        return {}
    eq = (1 + r).cumprod()
    return {
        "ann_ret_pct": round(r.mean() * TRADING_DAYS * 100, 1),
        "ann_vol_pct": round(r.std() * np.sqrt(TRADING_DAYS) * 100, 1),
        "sharpe": round(r.mean() / r.std() * np.sqrt(TRADING_DAYS), 2),
        "max_dd_pct": round((eq / eq.cummax() - 1).min() * 100, 1),
    }


def is_os_report(net: pd.Series, split: pd.Timestamp) -> dict:
    return {"IS": metrics(net[net.index < split]), "OS": metrics(net[net.index >= split])}
