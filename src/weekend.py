"""rToken-native weekend-session factors — structurally impossible in traditional markets.

Weekend daily bars are sparse/irregular (Sat added only since June 2026), so signals are
computed on the compressed weekend-only series, then forward-aligned to the daily calendar.
Design on IS (first 200d), one-shot verification on OS (last 100d).

  wk_mom4    cumulative weekend-bar return over past 4 weekends
  wk_volsh   weekend-bar vol / all-bar vol, ~4wk window
  wk_liqsh   weekend quote_vol share of total, ~4wk window
  wk_rev     last weekend-bar return (reversal)
Overlays on the low-vol core: weight_i *= (1 + lam * z(sig_i)), lam picked on IS only.
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "third_party"))

from backtest import metrics, run  # noqa: E402
from factors import panels  # noqa: E402

SPLIT = 200

cache = json.load(open(ROOT / "data" / "closes_raw.json"))
P = panels(cache)
px, qv = P["close"], P["quote_vol"]
rets = px.pct_change().clip(-0.6, 0.6)
is_wknd = pd.Series(px.index.dayofweek >= 5, index=px.index)
split_date = px.index[SPLIT]

sat_rets = rets[is_wknd].dropna(how="all")          # compressed weekend series
sat_qv = qv[is_wknd].dropna(how="all")
day_rets = rets[~is_wknd].dropna(how="all")
day_qv = qv[~is_wknd].dropna(how="all")


def align(sig_compressed):
    """Forward-fill a weekend-dated signal onto the daily calendar."""
    return sig_compressed.reindex(px.index).ffill()


sig_wk_mom4 = align(sat_rets.rolling(8, min_periods=4).sum())
wvol = sat_rets.rolling(8, min_periods=4).std()
avol = rets.rolling(20, min_periods=10).std().reindex(sat_rets.index)
sig_wk_volsh = align(wvol / avol)
wq = sat_qv.rolling(8, min_periods=4).median()
dq = qv.rolling(20, min_periods=10).median().reindex(sat_qv.index)
sig_wk_liqsh = align(wq / (wq + dq))
sig_wk_rev = align(sat_rets)

signals = {"wk_mom4": sig_wk_mom4, "wk_volsh": sig_wk_volsh,
           "wk_liqsh": sig_wk_liqsh, "wk_rev": sig_wk_rev}

# base portfolio ------------------------------------------------------------
liq_gate = qv.rolling(20).median().ge(qv.rolling(20).median().median(axis=1), axis=0)
vol40 = rets.rolling(40).std()
base_net, base_W, base_to = run(vol40, rets, qv.rolling(20).median())

COST = 1e-4


def portfolio_from(W):
    r = (W.shift(1) * rets).sum(axis=1) - (W.diff().abs().sum(axis=1) * COST)
    return r[r.index >= px.index[60]]


# IC evaluation ---------------------------------------------------------------
def weekly_ic(sig):
    fwd = rets.shift(-5)
    ics, dates = [], []
    for i in range(60, len(px) - 5, 5):
        s, f = sig.iloc[i], fwd.iloc[i]
        m = s.notna() & f.notna() & liq_gate.iloc[i]
        if m.sum() < 8:
            continue
        ics.append(s[m].rank().corr(f[m].rank()))
        dates.append(px.index[i])
    return pd.Series(ics, index=dates)


print(f"{'factor':<10} {'IS_IC':>7} {'IS_t':>6} {'OS_IC':>7} {'OS_t':>6}   split@{split_date.date()}")
for name, sig in signals.items():
    ic = weekly_ic(sig)
    ic_is, ic_os = ic[ic.index < split_date], ic[ic.index >= split_date]
    t_is = ic_is.mean() / ic_is.std() * np.sqrt(len(ic_is)) if len(ic_is) > 2 else np.nan
    t_os = ic_os.mean() / ic_os.std() * np.sqrt(len(ic_os)) if len(ic_os) > 2 else np.nan
    print(f"{name:<10} {ic_is.mean():>7.3f} {t_is:>6.2f} {ic_os.mean():>7.3f} {t_os:>6.2f}")

# overlays -------------------------------------------------------------------
W_base = vol40.where(liq_gate)
sel = W_base.le(W_base.quantile(0.2, axis=1), axis=0)      # lowest-vol quintile mask

print(f"\nbase  full={metrics(base_net)['sharpe']:.2f}  "
      f"IS={metrics(base_net[base_net.index < split_date])['sharpe']:.2f}  "
      f"OS={metrics(base_net[base_net.index >= split_date])['sharpe']:.2f}")

for name, sig in signals.items():
    z = sig[sel].rank(axis=1, pct=True) - 0.5              # cross-sectional z within quintile
    is_sharpes = {}
    for lam in (0.25, 0.5, 1.0, 2.0):
        Wt = sel.astype(float).mul(1 + lam * z)
        Wt = Wt.div(Wt.sum(axis=1), axis=0).fillna(0)
        r = portfolio_from(Wt)
        is_sharpes[lam] = metrics(r[r.index < split_date])["sharpe"]
    best = max(is_sharpes, key=is_sharpes.get)
    Wt = sel.astype(float).mul(1 + best * z)
    Wt = Wt.div(Wt.sum(axis=1), axis=0).fillna(0)
    r = portfolio_from(Wt)
    os_sh = metrics(r[r.index >= split_date])["sharpe"]
    print(f"{name:<10} lam*={best:<5}  IS {max(is_sharpes.values()):.2f} -> OS {os_sh:.2f}"
          f"   (all IS: {[f'{l}:{v:.2f}' for l, v in is_sharpes.items()]})")
