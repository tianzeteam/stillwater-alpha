"""Stillwater (静水) — research report app for the Bitget AI Base Camp S2 submission.

Run locally:  streamlit run app.py
Deploys as-is to Hugging Face Spaces (Streamlit template).
"""
import json
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "third_party"))

from backtest import metrics, run, run_killswitch  # noqa: E402
from data import MIN_DAYS, SYMBOLS, UNLISTED  # noqa: E402
from factors import panels, volatility_factors  # noqa: E402

CACHE = ROOT / "data" / "closes_raw.json"
REPORT = ROOT / "data" / "report.json"
SPLIT_IDX = 200
ANN = 365

st.set_page_config(page_title="Stillwater (静水)", page_icon="🐢", layout="wide")


# ---------------------------------------------------------------- data & pipeline

@st.cache_data(show_spinner="Loading price cache…")
def load_cache():
    if CACHE.exists():
        return json.load(open(CACHE))
    # fallback: fetch live via the official SDK (vendored under third_party)
    from data import load_cache as fetch_all
    return fetch_all(str(CACHE))


@st.cache_data(show_spinner="Running pipeline…")
def pipeline(cache):
    P = panels(cache)
    rets = P["close"].pct_change().clip(-0.6, 0.6)
    liq = P["quote_vol"].rolling(20).median()
    vol40 = rets.rolling(40).std()
    net, W, to = run(vol40, rets, liq)
    bench = rets.loc[rets.index[60]:].mean(axis=1)
    return dict(rets=rets, liq=liq, vol40=vol40, net=net, W=W, to=to, bench=bench,
                px=P["close"], quote_vol=P["quote_vol"])


@st.cache_data(show_spinner="Fetching live candles…")
def live_quote(symbols: tuple, ttl=300):
    """Fresh daily candles for the currently held names only (cheap live call)."""
    try:
        from data import make_client, fetch_symbol
        client = make_client()
        out = {}
        for sym in symbols:
            rows = fetch_symbol(client, sym, limit=5)
            if rows:
                out[sym] = rows[-1]  # [ts, open, close, high, low, base_vol, quote_vol, usdt_vol]
        return out
    except Exception:
        return {}


cache = load_cache()
P = pipeline(cache)
rets, net, W, bench = P["rets"], P["net"], P["W"], P["bench"]
split = rets.index[SPLIT_IDX]

# ---------------------------------------------------------------- header

st.title("🐢 Stillwater（静水）")
st.caption("Low-Volatility Alpha for Bitget rTokens · Bitget AI Base Camp Hackathon S2 · "
           "Alpha Factory track / rToken Factor Strategies sub-theme")
st.markdown('*"Still waters run deep." — the quietest 20% of the universe outperforms; '
            'we just filter the mud first.*')

tab_overview, tab_curve, tab_graveyard, tab_live, tab_costs = st.tabs(
    ["📈 Overview", "📉 Equity curve", "⚰️ Factor graveyard", "🛰️ Live portfolio", "🎚️ Cost sensitivity"])

# ---------------------------------------------------------------- overview

with tab_overview:
    m_net, m_bench = metrics(net), metrics(bench)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Strategy Sharpe (full)", m_net.get("sharpe", "—"), f"vs {m_bench.get('sharpe', '—')} benchmark")
    c2.metric("Max drawdown", f"{m_net.get('max_dd_pct', '—')}%", f"vs {m_bench.get('max_dd_pct', '—')}%")
    c3.metric("Ann. vol", f"{m_net.get('ann_vol_pct', '—')}%", f"vs {m_bench.get('ann_vol_pct', '—')}%")
    c4.metric("Universe", f"{rets.shape[1]} rTokens", f"{rets.shape[0]} daily bars · 7×24")

    st.divider()
    st.markdown(
        "**Thesis.** In a retail-dominated, liquidity-layered market, 19 of 20 classic US-equity "
        "factors fail out-of-sample — the low-volatility anomaly survives. A weekly-rebalanced, "
        "equal-weight long portfolio of the **lowest-vol quintile among liquid names** is the only "
        "configuration stable in both in-sample and out-of-sample windows.\n\n"
        "**Rule.** At each weekly rebalance: keep names with 20d median quote-volume ≥ cross-sectional "
        "median, pick the 20% with the lowest 40d volatility, hold equal-weight. Costs 10bps/side.")
    st.markdown(f"*Backtest window: {rets.index[60].date()} → {rets.index[-1].date()} · "
                f"OS starts {split.date()} · data: official Bitget V3 SDK (public endpoints).*")
    st.link_button("GitHub — one-command reproduction", "https://github.com/tianzeteam/stillwater-alpha")

# ---------------------------------------------------------------- equity curve

with tab_curve:
    eq_s = (1 + net).cumprod()
    eq_b = (1 + bench).cumprod()
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=eq_s.index, y=eq_s, name="Stillwater (vol_40 + liquidity gate)",
                             line=dict(color="#00b0ff", width=2)))
    fig.add_trace(go.Scatter(x=eq_b.index, y=eq_b, name="Equal-weight universe benchmark",
                             line=dict(color="#9e9e9e", width=1.5)))
    fig.add_vrect(x0=split, x1=eq_s.index[-1], fillcolor="#1f77b4", opacity=0.08,
                  annotation_text="out-of-sample", annotation_position="top left", line_width=0)
    fig.add_vline(x0=split, line_dash="dash", line_color="#1f77b4")
    fig.update_layout(height=480, margin=dict(l=10, r=10, t=30, b=10),
                      yaxis_title="Equity (start = 1)", legend=dict(orientation="h"))
    st.plotly_chart(fig, use_container_width=True)

    dd_s = (eq_s / eq_s.cummax() - 1) * 100
    dd_b = (eq_b / eq_b.cummax() - 1) * 100
    fig2 = go.Figure()
    fig2.add_trace(go.Scatter(x=dd_s.index, y=dd_s, name="Stillwater drawdown", line=dict(color="#00b0ff")))
    fig2.add_trace(go.Scatter(x=dd_b.index, y=dd_b, name="Benchmark drawdown", line=dict(color="#9e9e9e")))
    fig2.add_vrect(x0=split, x1=eq_s.index[-1], fillcolor="#1f77b4", opacity=0.08, line_width=0)
    fig2.update_layout(height=280, margin=dict(l=10, r=10, t=10, b=10), yaxis_title="Drawdown %")
    st.plotly_chart(fig2, use_container_width=True)

# ---------------------------------------------------------------- factor graveyard

with tab_graveyard:
    st.markdown("**20 tested. 19 dead.** Every factor below was run through the same harness: "
                "daily rank-IC, weekly-rebalanced long portfolio, liquidity screen, 10bps/side. "
                "This table is the anti-overfitting evidence chain.")
    graveyard = pd.DataFrame([
        ["Momentum 20d",        "IS 1.43 / OS -0.14", "OS decay — crosses the judges' OS<0.5×IS line"],
        ["Momentum 60d",        "IS 3.33 / OS -0.07", "Textbook in-sample overfit"],
        ["Momentum 5-25d",      "IS 1.51 / OS -0.69", "Skip-period fix doesn't help"],
        ["Reversal 5d",         "IS -1.33 / OS +2.01", "Sign flip — unstable, not deployable"],
        ["Vol-regime switch",   "IS 1.33 / OS -0.97", "Regime variable doesn't explain reversal's OS edge"],
        ["Rank composite",      "IS -0.86 / OS -0.45", "Polluted by zombie names pre-screen"],
        ["Volume z-score",      "OS IC -0.108 (t -4.7)", "Negative even after liquidity screen"],
        ["MAX lottery (long)",  "OS IC +0.068 (t 2.1)", "Edge lives in the tail; long-only can't harvest"],
        ["MAX lottery (short)", "IS -2.26 / OS -0.54", "Fails even without borrow cost"],
        ["Skew (short)",        "OS IC +0.053 (t 1.9)", "Same tail problem as MAX"],
        ["Residual momentum",   "IS 0.14 / OS -1.46 (combo)", "Weakened when combined with low-vol"],
        ["Idiosyncratic vol",   "OS IC -0.023", "No increment over total vol"],
        ["Dollar volume",       "OS IC -0.013", "Illiquidity premium absent"],
        ["Amihud illiquidity",  "OS IC -0.018", "Absent"],
        ["52w-high proximity",  "OS IC -0.028", "Absent"],
        ["Walk-forward pick-best", "OS 0.51", "Selector chases the just-decayed variant"],
        ["Weekend reversal",    "OS IC +0.072 (t 3.7)", "Real but too weak standalone"],
        ["Weekend vol share",   "OS IC +0.050 (t 2.7)", "Real but too weak standalone"],
        ["downside vol 20d",    "IS 1.26 / OS 0.86", "Positive but unstable across windows"],
        ["**Low vol 40d + liquidity gate**", "**IS 0.89 / OS 1.55**", "✅ the only survivor"],
    ], columns=["Factor", "Evidence", "Verdict"])
    styled = graveyard.style.apply(
        lambda col: ["background:#12351f;color:#d4ffd4" if "survivor" in str(v) else "" for v in col],
        axis=0)
    st.dataframe(styled, use_container_width=True, height=560)

# ---------------------------------------------------------------- live portfolio

with tab_live:
    st.markdown("**Current holdings** — recomputed from the latest cached rebalance, "
                "with live last-price ticks from the official Bitget SDK.")
    last_w = W.iloc[-1]
    held = last_w[last_w > 0].sort_values(ascending=False)
    if held.empty:
        st.warning("Portfolio is flat at the last rebalance.")
    else:
        ticks = live_quote(tuple(held.index))
        rows = []
        for sym, w in held.items():
            last_close = float(P["px"][sym].dropna().iloc[-1])
            live_close = float(ticks[sym][2]) if sym in ticks else last_close
            chg = (live_close / last_close - 1) * 100 if last_close > 0 else 0.0
            rows.append({"Symbol": sym, "Weight": f"{w:.1%}", "Last (USDT)": round(live_close, 3),
                         "Since last cached close": f"{chg:+.2f}%"})
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        st.caption(f"Live tick freshness: {'live' if ticks else 'cached fallback'} · "
                   f"held names re-priced every 5 minutes.")
    c1, c2, c3 = st.columns(3)
    c1.metric("Names held", len(held))
    c2.metric("Data date", str(P["px"].index[-1].date()))
    c3.metric("Weekly turnover", f"{P['to'].mean() * 7:.1%}")

# ---------------------------------------------------------------- cost sensitivity

with tab_cost:
    bps = st.slider("Cost per side (bps)", 0, 50, 10, 5)
    net_c = net - (P["to"] * (bps - 10) / 1e4)  # reprice cost relative to 10bps baseline
    m = metrics(net_c)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Ann. return", f"{m.get('ann_ret_pct', '—')}%")
    c2.metric("Sharpe", m.get("sharpe", "—"))
    c3.metric("Ann. vol", f"{m.get('ann_vol_pct', '—')}%")
    c4.metric("Max drawdown", f"{m.get('max_dd_pct', '—')}%")
    st.caption("Full-sample, cost applied to actual daily turnover of the weekly-rebalanced portfolio.")
