"""Render the Stillwater research report as a static HTML page (GitHub Pages).

Usage: python3 build_report.py   -> docs/index.html
"""
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "third_party"))

import numpy as np
import pandas as pd

from backtest import metrics, run  # noqa: E402
from factors import panels  # noqa: E402

SPLIT_IDX = 200
HELD_JS = json.dumps({})  # placeholder, replaced below after pipeline

cache = json.load(open(ROOT / "data" / "closes_raw.json"))
P = panels(cache)
rets = P["close"].pct_change().clip(-0.6, 0.6)
liq = P["quote_vol"].rolling(20).median()
vol40 = rets.rolling(40).std()
net, W, to = run(vol40, rets, liq)
bench = rets.loc[rets.index[60]:].mean(axis=1)
split = rets.index[SPLIT_IDX]

m_net, m_bench = metrics(net), metrics(bench)
held = W.iloc[-1]
held = held[held > 0].sort_values(ascending=False)
held_syms = list(held.index)

# cost sensitivity curve (full sample, actual daily turnover)
bps_grid = list(range(0, 55, 5))
sharpe_at = []
for b in bps_grid:
    n_c = net - to * (b - 10) / 1e4
    mm = metrics(n_c)
    sharpe_at.append(mm.get("sharpe", 0))

eq_s = (1 + net).cumprod()
eq_b = (1 + bench).cumprod()
dd_s = (eq_s / eq_s.cummax() - 1) * 100
dd_b = (eq_b / eq_b.cummax() - 1) * 100


def series(x):
    return json.dumps([[str(i.date()), round(float(v), 4)] for i, v in x.items()])


graveyard_rows = [
    ("Momentum 20d", "IS 1.43 / OS -0.14", "OS decay — crosses the judges' OS&lt;0.5×IS line", ""),
    ("Momentum 60d", "IS 3.33 / OS -0.07", "Textbook in-sample overfit", ""),
    ("Momentum 5-25d", "IS 1.51 / OS -0.69", "Skip-period fix doesn't help", ""),
    ("Reversal 5d", "IS -1.33 / OS +2.01", "Sign flip — unstable, not deployable", ""),
    ("Vol-regime switch", "IS 1.33 / OS -0.97", "Regime variable doesn't explain reversal's OS edge", ""),
    ("Rank composite", "IS -0.86 / OS -0.45", "Polluted by zombie names pre-screen", ""),
    ("Volume z-score", "OS IC -0.108 (t -4.7)", "Negative even after liquidity screen", ""),
    ("MAX lottery (long)", "OS IC +0.068 (t 2.1)", "Edge lives in the tail; long-only can't harvest", ""),
    ("MAX lottery (short)", "IS -2.26 / OS -0.54", "Fails even without borrow cost", ""),
    ("Skew (short)", "OS IC +0.053 (t 1.9)", "Same tail problem as MAX", ""),
    ("Residual momentum", "IS 0.14 / OS -1.46 (combo)", "Weakened when combined with low-vol", ""),
    ("Idiosyncratic vol", "OS IC -0.023", "No increment over total vol", ""),
    ("Dollar volume", "OS IC -0.013", "Illiquidity premium absent", ""),
    ("Amihud illiquidity", "OS IC -0.018", "Absent", ""),
    ("52w-high proximity", "OS IC -0.028", "Absent", ""),
    ("Walk-forward pick-best", "OS 0.51", "Selector chases the just-decayed variant", ""),
    ("Weekend reversal", "OS IC +0.072 (t 3.7)", "Real but too weak standalone", ""),
    ("Weekend vol share", "OS IC +0.050 (t 2.7)", "Real but too weak standalone", ""),
    ("Downside vol 20d", "IS 1.26 / OS 0.86", "Positive but unstable across windows", ""),
    ("Low vol 40d + liquidity gate", "IS 0.89 / OS 1.55", "✅ the only survivor", "background:#12351f;color:#d4ffd4"),
]
gy = "".join(
    f'<tr style="{style}"><td>{f}</td><td>{e}</td><td>{v}</td></tr>' for f, e, v, style in graveyard_rows
)

held_js = json.dumps(held_syms)

SCRIPT = r'''<script>
const EQ=__EQ__,DD_S=__DD_S__,DD_B=__DD_B__,COST=__COST__,HELD=__HELD__,SPLIT="__SPLIT__";
const blue="#00b0ff",grey="#9e9e9e";
function layout(h){return {margin:{l:10,r:10,t:10,b:30},height:h,paper_bgcolor:"#0e1117",plot_bgcolor:"#0e1117",font:{color:"#c9d1d9"}}}
Plotly.newPlot("eq",[
 {x:EQ.map(d=>d[0]),y:EQ.map(d=>d[1]),name:"Stillwater (vol_40 + liquidity gate)",line:{color:blue,width:2}},
 {x:EQ.map(d=>d[0]),y:EQ.map(d=>d[1]),name:"Equal-weight universe benchmark",line:{color:grey,width:1.5}}],
 {...layout(460),yaxis:{title:"Equity (start = 1)",gridcolor:"#222"},legend:{orientation:"h"},
 shapes:[{type:"rect",x0:SPLIT,x1:EQ[EQ.length-1][0],yref:"paper",y0:0,y1:1,fillcolor:"#1f77b4",opacity:0.08,line:{width:0}},
         {type:"line",x0:SPLIT,x1:SPLIT,yref:"paper",y0:0,y1:1,line:{dash:"dash",color:"#1f77b4"}}],
 annotations:[{text:"out-of-sample",x:SPLIT,y:1.05,yref:"paper",showarrow:false,font:{color:"#8ab4f8"}}]});

Plotly.newPlot("dd",[
 {x:DD_S.map(d=>d[0]),y:DD_S.map(d=>d[1]),name:"Stillwater drawdown",line:{color:blue}},
 {x:DD_B.map(d=>d[0]),y:DD_B.map(d=>d[1]),name:"Benchmark drawdown",line:{color:grey}}],
 {...layout(280),yaxis:{ticksuffix:"%",gridcolor:"#222"},legend:{orientation:"h"},
 shapes:[{type:"rect",x0:SPLIT,x1:DD_S[DD_S.length-1][0],yref:"paper",y0:0,y1:1,fillcolor:"#1f77b4",opacity:0.08,line:{width:0}}]});

Plotly.newPlot("cost",[{x:COST.map(d=>d[0]),y:COST.map(d=>d[1]),type:"bar",name:"Sharpe",
 marker:{color:COST.map(d=>d[0]===10?"#00b0ff":"#263445")}}],
 {...layout(320),xaxis:{title:"cost per side (bps)",gridcolor:"#222"},yaxis:{title:"Sharpe",gridcolor:"#222"}});

const body=document.getElementById("livebody"),foot=document.getElementById("livefoot");
let done=0;
const CACHED=__CACHED__,WT=__WT__;
HELD.forEach(sym=>{
  const cached=CACHED[sym], w=WT[sym];
  fetch("https://api.bitget.com/api/v2/spot/market/candles?symbol="+sym+"&granularity=1day&limit=2",{signal:AbortSignal.timeout(5000)})
    .then(r=>r.json()).then(d=>{
      const rows=d.data||[];const live=rows.length?parseFloat(rows[rows.length-1][2]):cached;
      const chg=cached>0?((live/cached-1)*100):"—";
      const cls=(chg!=="—")?("pct-"+(chg>0?"pos":"neg")):"";
      body.insertAdjacentHTML("beforeend",`<tr><td>${sym}</td><td>${(w*100).toFixed(1)}%</td><td>${cached.toFixed(3)}</td><td>${live.toFixed(3)}</td><td class="${cls}">${chg==="—"?"—":chg.toFixed(2)+"%"}</td><td>live</td></tr>`);
    })
    .catch(()=>{
      body.insertAdjacentHTML("beforeend",`<tr><td>${sym}</td><td>${(w*100).toFixed(1)}%</td><td>${cached.toFixed(3)}</td><td>${cached.toFixed(3)}</td><td>—</td><td>cached</td></tr>`);
    })
    .finally(()=>{done++;if(done===HELD.length)foot.textContent="Δ vs last cached daily close. Prices from api.bitget.com public endpoints, fetched in your browser."});
});
</script>
</div></body></html>'''
html_top = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Stillwater（静水）— Low-Volatility Alpha for Bitget rTokens</title>
<script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
<style>
body{{font-family:-apple-system,Segoe UI,Roboto,sans-serif;background:#0e1117;color:#e6e6e6;margin:0;padding:24px 0}}
.wrap{{max-width:1120px;margin:0 auto;padding:0 20px}}
h1{{margin-bottom:2px}}
.tag{{color:#8ab4f8}}
h2{{border-bottom:1px solid #2b3548;padding-bottom:6px;margin-top:26px}}
table{{border-collapse:collapse;width:100%;font-size:13.5px}}
td,th{{border:1px solid #333;padding:8px 10px;text-align:left}}
th{{background:#1a1f2b}}
.metrics{{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:10px;margin:14px 0}}
.metrics span{{display:flex;flex-direction:column;justify-content:center;padding:14px 16px;background:#1a1f2b;border-radius:12px;min-height:84px}}
.metrics b{{font-size:22px;color:#58a6ff;font-variant-numeric:tabular-nums;margin-top:2px}}
.metrics .small{{margin-top:2px}}
a{{color:#58a6ff}}
.small{{font-size:12px;color:#7f8896;line-height:1.5}}
p.lead{{font-size:14.5px;line-height:1.7;color:#c9d1d9;max-width:88ch}}
#live{{border-radius:10px;overflow:hidden}}
#live thead th{{background:#171d29}}
#live td,#livefoot td{{font-variant-numeric:tabular-nums}}
tbody tr:nth-child(odd) td{{background:#141920}}
td.pct-pos{{color:#66bb6a}}
td.pct-neg{{color:#ef5350}}

.topnav{{position:sticky;top:0;z-index:50;display:flex;gap:8px;flex-wrap:wrap;
 padding:10px 20px;margin:0 -20px 6px;background:rgba(14,17,23,0.92);
 border-bottom:1px solid #2b3548;backdrop-filter:blur(8px)}}
.topnav a{{font-size:13px;color:#9aa0a6;text-decoration:none;background:#1a1f2b;
 border-radius:999px;padding:5px 12px;transition:color 120ms cubic-bezier(0.2,0,0,1)}}
.topnav a:hover{{color:#8ab4f8}}
a:focus-visible{{outline:none;box-shadow:0 0 0 2px #00b0ff}}
h2{{scroll-margin-top:64px}}
@media (max-width:720px){{
 body{{padding-top:0}}
 h1{{font-size:28px}}
 .topnav{{padding:8px 16px;gap:6px;overflow-x:auto;flex-wrap:nowrap}}
 .topnav a{{flex:0 0 auto;padding:4px 10px}}
 table{{font-size:12.5px}}
 td,th{{padding:6px 8px}}
 .metrics{{grid-template-columns:repeat(2,1fr)}}
}}
@media (max-width:720px){{ .live-wrap{{overflow-x:auto}} .live-wrap table{{min-width:560px}} }}
</style></head><body>
<div class="wrap">
<nav class="topnav" aria-label="Sections">
<a href="#top">Overview</a><a href="#s-equity">Equity</a><a href="#s-live">Live</a>
<a href="#s-cost">Costs</a><a href="#s-grave">Graveyard</a><a href="#s-wknd">Weekend</a>
</nav>🐢 Stillwater（静水）</h1>
<div class="tag">Low-Volatility Alpha for Bitget rTokens · Bitget AI Base Camp Hackathon S2 · Alpha Factory / rToken Factor Strategies</div>
<p><i>"Still waters run deep." — the quietest 20% of the universe outperforms; we just filter the mud first.</i></p>

<div class="metrics">
<span>Sharpe <b>{m_net.get('sharpe')}</b><br><span class="small">vs {m_bench.get('sharpe')} benchmark</span></span>
<span>Max DD <b>{m_net.get('max_dd_pct')}%</b><br><span class="small">vs {m_bench.get('max_dd_pct')}%</span></span>
<span>Ann. vol <b>{m_net.get('ann_vol_pct')}%</b><br><span class="small">vs {m_bench.get('ann_vol_pct')}%</span></span>
<span>Universe <b>{rets.shape[1]}</b><br><span class="small">rTokens · {rets.shape[0]} daily bars · 7×24</span></span>
</div>

<p class="lead"><b>Thesis.</b> In a retail-dominated, liquidity-layered market, 19 of 20 classic US-equity factors fail
out-of-sample — the low-volatility anomaly survives. Weekly-rebalanced, equal-weight long portfolio of the
<b>lowest-vol quintile among liquid names</b> (20d median quote-volume ≥ cross-sectional median; 40d volatility;
10bps/side). Window {rets.index[60].date()} → {rets.index[-1].date()}, OS starts {split.date()}.
Data via the official Bitget V3 SDK. Reproduce: <a href="https://github.com/tianzeteam/stillwater-alpha">github.com/tianzeteam/stillwater-alpha</a> → <code>python3 src/run.py</code></p>

<h2 id="s-equity">Equity curve</h2>
<div id="eq" style="height:460px"></div>
<div id="dd" style="height:280px"></div>

<h2 id="s-live">Live portfolio <span class="small">(ticks fetched client-side from api.bitget.com — CORS open)</span></h2>
<table id="live"><thead><tr><th>Symbol</th><th>Weight</th><th>Cached close</th><th>Live last</th><th>Δ</th><th>Status</th></tr></thead>
<tbody id="livebody"></tbody></table>
<p class="small" id="livefoot"></p>

<h2 id="s-cost">Cost sensitivity <span class="small">(full sample, applied to actual daily turnover)</span></h2>
<div id="cost" style="height:320px"></div>

<h2 id="s-grave">⚰️ Factor graveyard — 20 tested, 19 dead</h2>
<p class="small">Same harness for every factor: daily rank-IC, weekly-rebalanced long portfolio, liquidity screen, 10bps/side.
This table is the anti-overfitting evidence chain.</p>
<table><thead><tr><th>Factor</th><th>Evidence</th><th>Verdict</th></tr></thead><tbody>{gy}</tbody></table>

<h2 id="s-wknd">🧬 rToken-native weekend-session factors <span class="small">(structurally impossible in traditional markets)</span></h2>
<p class="small">Computed on the compressed weekend-bar series (Sat bars only exist since Jun 2026); designed on IS, one-shot verification on OS; overlay λ picked on IS only.</p>
<table><thead><tr><th>Factor</th><th>IS IC (t)</th><th>OS IC (t)</th><th>Verdict</th></tr></thead><tbody>
<tr><td>Weekend momentum wk_mom4</td><td>+0.025 (0.57)</td><td>+0.080 (0.88)</td><td>right direction OS, t insufficient</td></tr>
<tr><td>Weekend vol share wk_volsh</td><td>+0.018 (0.53)</td><td>-0.015 (-0.19)</td><td>sign flip — dead</td></tr>
<tr><td>Weekend liq share wk_liqsh</td><td>-0.111 (-3.15)</td><td>+0.016 (0.25)</td><td>significant IS, flips OS — dead</td></tr>
<tr><td>Weekend reversal wk_rev</td><td>+0.019 (0.43)</td><td>+0.045 (0.57)</td><td>too weak</td></tr>
<tr><td>Overlays on low-vol core (IS-picked λ)</td><td>—</td><td>OS 0.07~-0.31 vs 1.55 base</td><td>IS-tuning trap caught by our own pipeline — dead</td></tr>
</tbody></table>
<p><b>Liquidity-gate ablation (original contribution).</b> The 113-name universe carries zero zombie contamination — the thinnest name in the low-vol quintile trades &gt;$5M/day, so an absolute floor ($0.1M-$5M) never binds in backtest and is kept purely as a live-deployment guard. The <i>relative</i> median gate is the opposite of a drag: it is the only configuration whose OS&gt;IS across both daily and weekly rebalancing (OS 1.67 / 1.55). Removing the gate yields OS 2.33 on daily rebalancing but collapses to 0.19 on weekly — <b>frequency-fragile, therefore rejected</b>. The gate buys robustness, not return.</p>

<p class="small">Built for the Bitget AI Base Camp Hackathon S2. #BitgetHackathon @Bitget_AI</p>"""
__EQ__ = series(eq_s)
__DD_S__ = series(dd_s)
__DD_B__ = series(dd_b)
html = (html_top
        + SCRIPT.replace("__EQ__", __EQ__)
                .replace("__DD_S__", __DD_S__)
                .replace("__DD_B__", __DD_B__)
                .replace("__COST__", json.dumps([[b, sh] for b, sh in zip(bps_grid, sharpe_at)]))
                .replace("__HELD__", json.dumps(held_syms))
                .replace("__SPLIT__", str(split.date()))
                .replace("__CACHED__", json.dumps({sy: float(P["close"][sy].dropna().iloc[-1]) for sy in held_syms}))
                .replace("__WT__", json.dumps({sy: float(held[sy]) for sy in held_syms}))
        )

out = ROOT / "docs" / "index.html"
out.parent.mkdir(exist_ok=True)
out.write_text(html)
print(f"written {out} ({out.stat().st_size/1024:.0f} KB); held={held_syms}; sharpe@costs={sharpe_at}")
