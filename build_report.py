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

PRE = r"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Stillwater— Low-Volatility Alpha for Bitget rTokens</title>
<script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
:root{
  --bg:#07090d; --panel:rgba(26,31,43,.55); --panel-quiet:rgba(23,29,41,.6);
  --ink:#e9ecf1; --ink-2:#c6ccd6; --muted:#98a1b0; --meta:#6d7686;
  --line:rgba(255,255,255,.07); --line-soft:rgba(255,255,255,.045);
  --cyan:#00b0ff; --azure:#4f9dff; --soft:#8ab4f8;
  --pos:#5fd08a; --neg:#ff6b6b;
  --disp:"Space Grotesk",Inter,-apple-system,"Segoe UI",Roboto,"PingFang SC","Noto Sans SC",sans-serif;
  --body:Inter,-apple-system,"Segoe UI",Roboto,"PingFang SC","Noto Sans SC",sans-serif;
  --mono:"JetBrains Mono",ui-monospace,"SF Mono",Menlo,Consolas,monospace;
}
*{box-sizing:border-box}
html{scroll-behavior:smooth}
body{margin:0;background:var(--bg);color:var(--ink);font-family:var(--body);
  font-size:14px;line-height:1.6;-webkit-font-smoothing:antialiased;overflow-x:hidden}
/* ambient light */
body::before{content:"";position:fixed;inset:0;z-index:-2;pointer-events:none;
  background:
    radial-gradient(1100px 620px at 50% -140px, rgba(0,176,255,.13), transparent 62%),
    radial-gradient(900px 560px at 88% 18%, rgba(101,78,255,.09), transparent 60%),
    radial-gradient(1000px 700px at 8% 88%, rgba(0,176,255,.05), transparent 55%)}
body::after{content:"";position:fixed;inset:0;z-index:-1;pointer-events:none;opacity:.5;
  background:repeating-linear-gradient(90deg, rgba(255,255,255,.028) 0 1px, transparent 1px 96px)}
.wrap{max-width:1120px;margin:0 auto;padding:0 24px}
/* nav */
.topnav{position:sticky;top:0;z-index:60;display:flex;align-items:center;justify-content:space-between;
  gap:16px;padding:12px 24px;margin:0 -24px 8px;background:rgba(7,9,13,.72);
  border-bottom:1px solid var(--line);backdrop-filter:blur(14px);-webkit-backdrop-filter:blur(14px)}
.brand{font-family:var(--disp);font-weight:600;font-size:15px;letter-spacing:.2px;color:var(--ink);text-decoration:none;white-space:nowrap}
.brand i{font-style:normal;color:var(--cyan)}
.topnav .links{display:flex;gap:6px;flex-wrap:wrap}
.topnav .links a{font-size:12.5px;font-weight:500;color:var(--muted);text-decoration:none;
  padding:6px 13px;border-radius:999px;border:1px solid transparent;
  transition:color 160ms cubic-bezier(.2,0,0,1),border-color 160ms cubic-bezier(.2,0,0,1)}
.topnav .links a:hover{color:var(--soft);border-color:var(--line)}
a:focus-visible{outline:none;box-shadow:0 0 0 2px var(--cyan)}
/* hero */
.hero{padding:64px 0 40px;max-width:860px}
.chips{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:22px}
.chips span{font-family:var(--mono);font-size:11px;letter-spacing:.08em;text-transform:uppercase;
  color:var(--soft);background:rgba(0,176,255,.07);border:1px solid rgba(0,176,255,.18);
  padding:5px 12px;border-radius:999px}
.hero h1{font-family:var(--disp);font-size:58px;line-height:1.04;letter-spacing:-.02em;
  font-weight:600;margin:0 0 18px}
.hero h1 em{font-style:normal;background:linear-gradient(94deg,#00b0ff 8%,#4f9dff 52%,#9d7bff 96%);
  -webkit-background-clip:text;background-clip:text;color:transparent}
.hero .sub{font-size:16.5px;color:var(--ink-2);max-width:620px;margin:0 0 10px}
.hero .quote{font-family:var(--mono);font-size:12.5px;color:var(--meta);margin-top:14px}
/* stat band */
.band{display:grid;grid-template-columns:repeat(4,1fr);border:1px solid var(--line);
  border-radius:18px;background:var(--panel);backdrop-filter:blur(14px);-webkit-backdrop-filter:blur(14px);
  box-shadow:0 24px 60px -34px rgba(0,0,0,.65), inset 0 1px 0 rgba(255,255,255,.05);
  overflow:hidden;margin:34px 0 8px}
.band .stat{padding:22px 26px;position:relative}
.band .stat + .stat{border-left:1px solid var(--line-soft)}
.stat .k{display:block;font-family:var(--mono);font-size:10.5px;letter-spacing:.1em;
  text-transform:uppercase;color:var(--meta);margin-bottom:10px}
.stat .v{display:block;font-family:var(--disp);font-size:40px;font-weight:600;line-height:1;
  letter-spacing:-.02em;color:var(--ink);font-variant-numeric:tabular-nums}
.stat .v small{font-size:22px;color:var(--muted);font-weight:500}
.stat .s{display:block;margin-top:10px;font-size:12px;color:var(--meta);font-variant-numeric:tabular-nums}
.stat.hero-stat .v{color:var(--cyan)}
/* sections */
section{padding:44px 0 6px}
.sec{display:flex;align-items:baseline;gap:16px;border-bottom:1px solid var(--line);
  padding-bottom:16px;margin-bottom:22px;scroll-margin-top:76px}
.sec .n{font-family:var(--mono);font-size:12px;color:var(--cyan);letter-spacing:.08em}
.sec h2{font-family:var(--disp);font-size:24px;font-weight:600;letter-spacing:-.01em;margin:0}
.sec .note{font-size:12.5px;color:var(--meta);margin-left:auto;text-align:right;max-width:46%}
/* glass cards */
.glass{border:1px solid var(--line);border-radius:18px;background:var(--panel);
  backdrop-filter:blur(14px);-webkit-backdrop-filter:blur(14px);
  box-shadow:0 24px 60px -34px rgba(0,0,0,.6), inset 0 1px 0 rgba(255,255,255,.05);
  overflow:hidden;margin-bottom:26px}
/* tables */
table{border-collapse:collapse;width:100%;font-size:13.5px}
thead th{font-family:var(--mono);font-size:10.5px;font-weight:500;letter-spacing:.1em;
  text-transform:uppercase;color:var(--meta);text-align:left;padding:12px 16px;
  background:rgba(23,29,41,.5);border-bottom:1px solid var(--line)}
tbody td{padding:11px 16px;border-bottom:1px solid var(--line-soft);color:var(--ink-2);
  font-variant-numeric:tabular-nums}
tbody tr:last-child td{border-bottom:none}
tbody tr:hover td{background:rgba(0,176,255,.035);color:var(--ink)}
tbody tr[style*="12351f"] td{background:linear-gradient(90deg,rgba(38,102,63,.28),rgba(38,102,63,.10))!important;
  color:#d9ffe2!important;box-shadow:inset 3px 0 0 #3ecf7a}
td.pct-pos{color:var(--pos);font-weight:600}
td.pct-neg{color:var(--neg);font-weight:600}
.pill{display:inline-flex;align-items:center;gap:6px;font-family:var(--mono);font-size:10.5px;
  letter-spacing:.08em;text-transform:uppercase;padding:3px 10px;border-radius:999px;
  border:1px solid var(--line)}
.pill.live{color:var(--cyan);border-color:rgba(0,176,255,.25)}
.pill.live::before{content:"";width:6px;height:6px;border-radius:50%;background:var(--cyan);
  box-shadow:0 0 8px var(--cyan)}
.pill.cached{color:var(--meta)}
td .dpill{font-family:var(--mono);font-size:12px;padding:2px 9px;border-radius:999px;
  display:inline-block}
td .dpill.pos{color:var(--pos);background:rgba(95,208,138,.08);border:1px solid rgba(95,208,138,.18)}
td .dpill.neg{color:var(--neg);background:rgba(255,107,107,.08);border:1px solid rgba(255,107,107,.18)}
#live-wrap{overflow-x:auto}#live-wrap table{min-width:640px}
/* prose */
.lead{font-size:15px;line-height:1.75;color:var(--ink-2);max-width:92ch;margin:18px 0 6px}
.lead b{color:var(--ink)}
.small{font-size:12px;color:var(--meta);line-height:1.6}
a{color:var(--soft)}
/* footer */
footer{border-top:1px solid var(--line);margin-top:52px;padding:26px 0 40px;
  display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap}
footer .small{max-width:70%}
/* charts */
#eq{height:480px}#dd{height:250px}#cost{height:300px}
/* motion: single gentle entrance */
@keyframes rise{from{opacity:0;transform:translateY(14px)}to{opacity:1;transform:none}}
.hero,.band,section{animation:rise 480ms cubic-bezier(.2,0,0,1) both}
.band{animation-delay:90ms}section{animation-delay:140ms}
@media (prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}}
/* mobile */
@media (max-width:760px){
 .wrap{padding:0 16px}
 .topnav{padding:10px 16px;margin:0 -16px 4px}
 .brand{font-size:14px}
 .topnav .links{overflow-x:auto;flex-wrap:nowrap;justify-content:flex-start;scrollbar-width:none}
 .hero{padding:44px 0 26px}
 .hero h1{font-size:36px}
 .hero .sub{font-size:15px}
 .band{grid-template-columns:1fr 1fr}
 .band .stat{padding:16px 18px}
 .band .stat:nth-child(odd){border-left:none}
 .band .stat:nth-child(n+3){border-top:1px solid var(--line-soft)}
 .stat .v{font-size:30px}
 .sec{flex-wrap:wrap}.sec .note{margin-left:0;text-align:left;max-width:100%}
 table{font-size:12.5px}tbody td{padding:9px 12px}thead th{padding:10px 12px}
}
</style></head><body>
<div class="wrap">
<nav class="topnav" aria-label="Sections">
  <a class="brand" href="#top">🐢 Stillwater</a>
  <div class="links">
    <a href="#s-equity">Equity</a><a href="#s-live">Live</a><a href="#s-cost">Costs</a>
    <a href="#s-grave">Graveyard</a><a href="#s-wknd">Weekend</a><a href="#s-repro">Reproduce</a>
  </div>
</nav>
<header class="hero" id="top">
  <div class="chips"><span>Alpha Factory</span><span>rToken Factor Strategies</span><span>Bitget S2 · 2026</span></div>
  <h1>The quietest 20%<br><em>outperforms.</em></h1>
  <p class="sub">Low-volatility alpha for Bitget rTokens — a weekly-rebalanced, equal-weight
  portfolio of the lowest-volatility quintile among liquid names.</p>
  <div class="quote">"Still waters run deep." — __UNI__ rTokens · __BARS__ daily bars · 7×24 · official Bitget V3 SDK</div>
</header>
"""

BODY = f"""<div class="band">
<div class="stat hero-stat"><span class="k">Sharpe · full</span><span class="v">{m_net.get('sharpe')}</span><span class="s">vs {m_bench.get('sharpe')} benchmark</span></div>
<div class="stat"><span class="k">Max drawdown</span><span class="v">{m_net.get('max_dd_pct')}<small>%</small></span><span class="s">vs {m_bench.get('max_dd_pct')}%</span></div>
<div class="stat"><span class="k">Ann. vol</span><span class="v">{m_net.get('ann_vol_pct')}<small>%</small></span><span class="s">vs {m_bench.get('ann_vol_pct')}%</span></div>
<div class="stat"><span class="k">Weekly turnover</span><span class="v">~2.7<small>%</small></span><span class="s">low-touch · capacity-friendly</span></div>
</div>

<p class="lead"><b>Thesis.</b> In a retail-dominated, liquidity-layered market, 19 of 20 classic US-equity factors fail
out-of-sample — the low-volatility anomaly survives. Weekly-rebalanced, equal-weight long portfolio of the
<b>lowest-vol quintile among liquid names</b> (20d median quote-volume ≥ cross-sectional median; 40d volatility;
10bps/side). Window {rets.index[60].date()} → {rets.index[-1].date()}, OS starts {split.date()}.
Reproduce: <a href="https://github.com/tianzeteam/stillwater-alpha">github.com/tianzeteam/stillwater-alpha</a> → <code>python3 src/run.py</code></p>

<section>
<div class="sec"><span class="n">01</span><h2 id="s-equity">Equity curve</h2>
<span class="note">strategy vs equal-weight universe · IS/OS split at {split.date()}</span></div>
<div class="glass" style="padding:8px 6px 0">
<div id="eq"></div><div id="dd"></div>
</div>
</section>

<section>
<div class="sec"><span class="n">02</span><h2 id="s-live">Live portfolio</h2>
<span class="note">ticks fetched client-side from api.bitget.com — CORS open</span></div>
<div class="glass" id="live-wrap">
<table id="live"><thead><tr><th>Symbol</th><th>Weight</th><th>Cached close</th><th>Live last</th><th>Δ</th><th>Status</th></tr></thead>
<tbody id="livebody"></tbody></table>
</div>
<p class="small" id="livefoot"></p>
</section>

<section>
<div class="sec"><span class="n">03</span><h2 id="s-cost">Cost sensitivity</h2>
<span class="note">full sample · applied to actual daily turnover · 10bps baseline highlighted</span></div>
<div class="glass" style="padding:10px 6px 0"><div id="cost"></div></div>
</section>

<section>
<div class="sec"><span class="n">04</span><h2 id="s-grave">Factor graveyard</h2>
<span class="note">20 tested · 19 dead — the anti-overfitting evidence chain</span></div>
<div class="glass">
<table><thead><tr><th>Factor</th><th>Evidence</th><th>Verdict</th></tr></thead><tbody>{gy}</tbody></table>
</div>
</section>

<section>
<div class="sec"><span class="n">05</span><h2 id="s-wknd">rToken-native weekend factors</h2>
<span class="note">structurally impossible in traditional markets · IS design / one-shot OS verify</span></div>
<div class="glass">
<table><thead><tr><th>Factor</th><th>IS IC (t)</th><th>OS IC (t)</th><th>Verdict</th></tr></thead><tbody>
<tr><td>Weekend momentum wk_mom4</td><td>+0.025 (0.57)</td><td>+0.080 (0.88)</td><td>right direction OS, t insufficient</td></tr>
<tr><td>Weekend vol share wk_volsh</td><td>+0.018 (0.53)</td><td>-0.015 (-0.19)</td><td>sign flip — dead</td></tr>
<tr><td>Weekend liq share wk_liqsh</td><td>-0.111 (-3.15)</td><td>+0.016 (0.25)</td><td>significant IS, flips OS — dead</td></tr>
<tr><td>Weekend reversal wk_rev</td><td>+0.019 (0.43)</td><td>+0.045 (0.57)</td><td>too weak</td></tr>
<tr><td>Overlays on low-vol core (IS-picked λ)</td><td>—</td><td>OS 0.07~-0.31 vs 1.55 base</td><td>IS-tuning trap caught by our own pipeline — dead</td></tr>
</tbody></table>
</div>
<p class="small"><b>Liquidity-gate ablation.</b> Zero zombie contamination in the 113-name universe — the thinnest
name in the low-vol quintile trades &gt;$5M/day; an absolute floor ($0.1M-$5M) never binds in backtest and is kept
as a live-deployment guard. The relative median gate is the only configuration whose OS&gt;IS across both daily and
weekly rebalancing (OS 1.67 / 1.55). Removing it: OS 2.33 on daily rebalancing but 0.19 on weekly — frequency-fragile,
rejected. <b>The gate buys robustness, not return.</b></p>
</section>

<footer id="s-repro">
<div class="small">Built for the Bitget AI Base Camp Hackathon S2 · data: official Bitget V3 SDK public endpoints ·
reproduce with <code>python3 src/run.py</code> · prices re-checked live in your browser above.</div>
<div class="small">#BitgetHackathon @Bitget_AI</div>
</footer>"""

SCRIPT = r"""<script>
const EQ=__EQ__,DD_S=__DD_S__,DD_B=__DD_B__,COST=__COST__,HELD=__HELD__,SPLIT="__SPLIT__";
const C="00b0ff",AZ="4f9dff",INK="c6ccd6",MUT="8b93a3";
const FONT={family:"Space Grotesk, Inter, sans-serif",size:11,color:MUT};
const cfg={displayModeBar:false,responsive:true};
function ax(t){return {title:{text:t,font:FONT,standoff:12},gridcolor:"rgba(255,255,255,.05)",zeroline:false,tickfont:{family:"JetBrains Mono, monospace",size:10,color:MUT}}}
function lay(h){return {margin:{l:52,r:16,t:14,b:38},height:h,autosize:true,
 paper_bgcolor:"rgba(0,0,0,0)",plot_bgcolor:"rgba(0,0,0,0)",font:FONT,
 hoverlabel:{bgcolor:"#131824",bordercolor:"rgba(255,255,255,.12)",font:{family:"JetBrains Mono, monospace",size:11,color:INK}},
 xaxis:ax(""),showlegend:true,legend:{orientation:"h",x:0,y:1.06,font:{family:"Inter",size:11,color:INK}}}}

const eqT=[{x:EQ.map(d=>d[0]),y:EQ.map(d=>d[1]),name:"Stillwater (vol_40 + liquidity gate)",
 line:{color:"#"+C,width:2.2},hovertemplate:"%{x}<br>Stillwater %{y:.3f}<extra></extra>"},
 {x:EQ.map(d=>d[0]),y:EQ.map(d=>d[1]),name:"Equal-weight universe benchmark",
 line:{color:"rgba(255,255,255,.42)",width:1.4},hovertemplate:"%{x}<br>Benchmark %{y:.3f}<extra></extra>"}];
Plotly.newPlot("eq",eqT,{...lay(480),yaxis:ax("Equity (start = 1)"),
 shapes:[{type:"rect",x0:SPLIT,x1:EQ[EQ.length-1][0],yref:"paper",y0:0,y1:1,
  fillcolor:"rgba(0,176,255,.05)",line:{width:0}},
  {type:"line",x0:SPLIT,x1:SPLIT,yref:"paper",y0:0,y1:1,line:{dash:"dot",color:"rgba(0,176,255,.55)",width:1}}],
 annotations:[{text:"OUT-OF-SAMPLE",x:SPLIT,xanchor:"left",dx:8,y:1.04,yref:"paper",showarrow:false,
  font:{family:"JetBrains Mono, monospace",size:10,color:"#"+C}}]},cfg);

const ddT=[{x:DD_S.map(d=>d[0]),y:DD_S.map(d=>d[1]),name:"Stillwater drawdown",
 line:{color:"rgba(0,176,255,.75)",width:1.4},fill:"tozeroy",fillcolor:"rgba(0,176,255,.07)",hoverinfo:"x+y"},
 {x:DD_B.map(d=>d[0]),y:DD_B.map(d=>d[1]),name:"Benchmark drawdown",
 line:{color:"rgba(255,255,255,.30)",width:1.1},fill:"tozeroy",fillcolor:"rgba(255,255,255,.03)",hoverinfo:"x+y"}];
Plotly.newPlot("dd",ddT,{...lay(250),showlegend:false,yaxis:ax("Drawdown %"),
 shapes:[{type:"rect",x0:SPLIT,x1:DD_S[DD_S.length-1][0],yref:"paper",y0:0,y1:1,fillcolor:"rgba(0,176,255,.05)",line:{width:0}}]},cfg);

const costT=[{x:COST.map(d=>d[0]),y:COST.map(d=>d[1]),type:"bar",name:"Sharpe",
 marker:{color:COST.map(d=>d[0]===10?"#00b0ff":"rgba(79,157,255,.30)"),
  line:{width:0}},hovertemplate:"%{x} bps · Sharpe %{y:.2f}<extra></extra>"}];
Plotly.newPlot("cost",costT,{...lay(300),showlegend:false,yaxis:ax("Sharpe"),
 xaxis:ax("cost per side (bps)")},cfg);

const body=document.getElementById("livebody"),foot=document.getElementById("livefoot");
let done=0;
const CACHED=__CACHED__,WT=__WT__;
HELD.forEach(sym=>{
  const cached=CACHED[sym], w=WT[sym];
  fetch("https://api.bitget.com/api/v2/spot/market/candles?symbol="+sym+"&granularity=1day&limit=2",{signal:AbortSignal.timeout(5000)})
    .then(r=>r.json()).then(d=>{
      const rows=d.data||[];const live=rows.length?parseFloat(rows[rows.length-1][2]):cached;
      const chg=cached>0?((live/cached-1)*100):null;
      const cls=chg===null?"":(chg>0?"pos":"neg");
      const disp=chg===null?"—":((chg>0?"+":"")+chg.toFixed(2)+"%");
      body.insertAdjacentHTML("beforeend",`<tr><td style="font-family:var(--mono);font-size:12.5px;color:var(--ink)">${sym}</td><td>${(w*100).toFixed(1)}%</td><td>${cached.toFixed(3)}</td><td>${live.toFixed(3)}</td><td><span class="dpill ${cls}">${disp}</span></td><td><span class="pill live">live</span></td></tr>`);
    })
    .catch(()=>{
      body.insertAdjacentHTML("beforeend",`<tr><td style="font-family:var(--mono);font-size:12.5px;color:var(--ink)">${sym}</td><td>${(w*100).toFixed(1)}%</td><td>${cached.toFixed(3)}</td><td>${cached.toFixed(3)}</td><td><span class="dpill">—</span></td><td><span class="pill cached">cached</span></td></tr>`);
    })
    .finally(()=>{done++;if(done===HELD.length)foot.textContent="Δ vs last cached daily close. Prices from api.bitget.com public endpoints, fetched in your browser."});
});
</script>
"""

EQ_S = series(eq_s); DD_SJ = series(dd_s); DD_BJ = series(dd_b)
html = ((PRE + BODY + SCRIPT)
        .replace("__EQ__", EQ_S)
        .replace("__DD_S__", DD_SJ)
        .replace("__DD_B__", DD_BJ)
        .replace("__COST__", json.dumps([[b, sh] for b, sh in zip(bps_grid, sharpe_at)]))
        .replace("__HELD__", json.dumps(held_syms))
        .replace("__SPLIT__", str(split.date()))
        .replace("__CACHED__", json.dumps({sy: float(P["close"][sy].dropna().iloc[-1]) for sy in held_syms}))
        .replace("__WT__", json.dumps({sy: float(held[sy]) for sy in held_syms}))
        .replace("__UNI__", str(rets.shape[1]))
        .replace("__BARS__", str(rets.shape[0]))
        + "</div></body></html>")

out = ROOT / "docs" / "index.html"
out.parent.mkdir(exist_ok=True)
out.write_text(html)
print(f"written {out} ({out.stat().st_size/1024:.0f} KB); held={held_syms}; sharpe@costs={sharpe_at}")
