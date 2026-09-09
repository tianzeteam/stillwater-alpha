import json, time, os, sys
import requests

BASE = os.path.expanduser("~/rtoken-research")
CACHE = f"{BASE}/data/closes_raw.json"
cache = json.load(open(CACHE)) if os.path.exists(CACHE) else {}

STOCKS = """
AAPL MSFT NVDA AMZN GOOGL META TSLA AVGO AMD QCOM MU ARM SMCI MRVL TSM INTC ORCL CRM ADBE NFLX DIS
COST WMT MCD NKE PFE JNJ UNH ABBV MRK TMO LLY JPM BAC GS MS V MA PYPL SQ XYZ COIN HOOD SOFI SCHW BLK
UBER ABNB DASH LYFT SHOP SNOW CRWD ZS DDOG NET MDB PLTR IONQ RGTI QBTS RIOT MARA MSTR TOST
BA LMT RTX GE CAT DE F GM SLB XOM CVX COP OXY HAL BKR
BABA BIDU NTES BILI JD PDD TME BEKE
SONY TM GSK SHEL RIO BHP VALE
""".split()
ETFS = "SPY QQQ QQQM IWM TLT SOXX EWY DIA GLD SLV VTI VOO ARKK SCHD JEPI JEPQ XLK XLF XLE XLI XLV SMH RSP SSO SH SDS TQQQ SQQQ VIG IEF HYG LQD AGG TIP GDX XBI IBB".split()
SYMBOLS = [f"R{t}USDT" for t in sorted(set(STOCKS + ETFS))]
todo = [s for s in SYMBOLS if s not in cache or len(cache[s]) < 60]

sess = requests.Session()
sess.headers.update({"User-Agent": "Mozilla/5.0 research/1.0"})
fails = []
for i, sym in enumerate(todo):
    rows = None
    for delay in (0, 3, 10, 30):
        if delay:
            time.sleep(delay)
        try:
            r = sess.get("https://api.bitget.com/api/v2/spot/market/candles",
                         params={"symbol": sym, "granularity": "1day", "limit": "300"}, timeout=20)
            d = r.json()
            if d.get("code") == "00000":
                rows = d.get("data") or []
                break
        except Exception:
            continue
    if rows and len(rows) >= 60:
        cache[sym] = rows
    else:
        fails.append(sym)
    json.dump(cache, open(CACHE, "w"))
    print(f"[{i+1}/{len(todo)}] {sym}: {'ok ' + str(len(rows)) if rows else 'FAIL'}", flush=True)
    time.sleep(0.15)

json.dump(cache, open(CACHE, "w"))
print(f"DONE cached={len(cache)} fails={fails}", flush=True)
