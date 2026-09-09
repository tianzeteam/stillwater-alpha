"""Reproduce the full research pipeline: data -> factor variants -> report."""
import json
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
from data import load_cache  # noqa: E402
from factors import panels, volatility_factors  # noqa: E402
from backtest import run, is_os_report  # noqa: E402

BASE = os.path.expanduser("~/stillwater-alpha")


def main():
    cache = load_cache(f"{BASE}/data/closes_raw.json")
    P = panels(cache)
    rets = P["close"].pct_change().clip(-0.6, 0.6)
    liq = P["quote_vol"].rolling(20).median()

    split = rets.index[200]
    report = {}
    for name, sig in volatility_factors(rets).items():
        net, W, to = run(sig, rets, liq)
        report[name] = is_os_report(net, split) | {"avg_daily_turnover": round(float(to.mean()), 3)}

    # cost sensitivity for the chosen variant (vol_40)
    for bps in (10, 20, 30):
        net, _, _ = run(volatility_factors(rets)["vol_40"], rets, liq, cost_bps=bps)
        report[f"vol_40_cost_{bps}bps"] = is_os_report(net, split)

    # equal-weight benchmark on the same window
    bench = rets.loc[rets.index[60]:].mean(axis=1)
    report["ew_benchmark"] = is_os_report(bench, split)

    out = f"{BASE}/data/report.json"
    json.dump(report, open(out, "w"), indent=1)
    print(json.dumps(report, indent=1))
    print(f"\nreport -> {out}")


if __name__ == "__main__":
    main()
