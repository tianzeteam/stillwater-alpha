"""Bitget rToken data layer — fetch & cache daily OHLCV via the official Bitget V3 SDK.

Vendored SDK lives at third_party/bitget (see third_party/README.md). Public
market-data endpoints only; credentials are empty strings.
"""
import contextlib
import io
import json
import os
import sys
import time
from pathlib import Path

_THIRD_PARTY = Path(__file__).resolve().parent.parent / "third_party"
if str(_THIRD_PARTY) not in sys.path:
    sys.path.insert(0, str(_THIRD_PARTY))

from bitget.bitget_api import BitgetApi  # noqa: E402  (official SDK, vendored)

STOCKS = """
AAPL MSFT NVDA AMZN GOOGL META TSLA AVGO AMD QCOM MU ARM SMCI MRVL TSM INTC ORCL CRM ADBE NFLX DIS
COST WMT MCD NKE PFE JNJ UNH ABBV MRK TMO LLY JPM BAC GS MS V MA PYPL SQ XYZ COIN HOOD SOFI SCHW BLK
UBER ABNB DASH LYFT SHOP SNOW CRWD ZS DDOG NET MDB PLTR IONQ RGTI QBTS RIOT MARA MSTR TOST
BA LMT RTX GE CAT DE F GM SLB XOM CVX COP OXY HAL BKR
BABA BIDU NTES BILI JD PDD TME BEKE
SONY TM GSK SHEL RIO BHP VALE
""".split()
ETFS = "SPY QQQ QQQM IWM TLT SOXX EWY DIA GLD SLV VTI VOO ARKK SCHD JEPI JEPQ XLK XLF XLE XLI XLV SMH RSP SSO SH SDS TQQQ SQQQ VIG IEF HYG LQD AGG TIP GDX XBI IBB".split()

# verified as not listed on Bitget spot (2026-09-08); avoid wasted retries
UNLISTED = {"RBEKEUSDT", "RBHPUSDT", "RCATUSDT", "RGDXUSDT", "RLQDUSDT", "RLYFTUSDT", "RRSPUSDT",
            "RSDSUSDT", "RSHUSDT", "RSQUSDT", "RSSOUSDT", "RTMEUSDT", "RVIGUSDT", "RXLEUSDT",
            "RXLFUSDT", "RXLIUSDT"}

SYMBOLS = [s for s in (f"R{t}USDT" for t in sorted(set(STOCKS + ETFS))) if s not in UNLISTED]
MIN_DAYS = 60

SPOT_CANDLES_PATH = "/api/v2/spot/market/candles"
RETRY_DELAYS = (0, 3, 10, 30)


def make_client() -> BitgetApi:
    """Public market data needs no credentials; the SDK still signs with empty keys."""
    return BitgetApi("", "", "")


def fetch_symbol(client, sym: str, limit: int = 300):
    """Daily candles via the official SDK. Returns list of rows or None on repeated failure.

    The SDK prints every response body — silence it (116 symbols would spam stdout).
    Network/proxy failures on this host are intermittent, hence the long backoff chain.
    """
    for attempt, delay in enumerate(RETRY_DELAYS):
        if delay:
            time.sleep(delay)
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                d = client.get(SPOT_CANDLES_PATH,
                               {"symbol": sym, "granularity": "1day", "limit": str(limit)})
            if isinstance(d, dict) and d.get("code") == "00000":
                return d.get("data") or []
        except Exception as exc:  # SDK raises BitgetAPIException/requests errors
            if attempt == len(RETRY_DELAYS) - 1:
                print(f"  {sym} failed after {len(RETRY_DELAYS)} attempts: {exc}", file=sys.stderr)
    return None


def load_cache(path: str, client_factory=make_client, force: bool = False) -> dict:
    """Fetch all symbols with resume-from-cache; returns {sym: [candle rows]}."""
    cache = {}
    if os.path.exists(path) and not force:
        cache = json.load(open(path))
    todo = [s for s in SYMBOLS if s not in cache or len(cache[s]) < MIN_DAYS]
    if not todo:
        return cache
    client = client_factory()
    for i, sym in enumerate(todo):
        rows = fetch_symbol(client, sym)
        ok = rows and len(rows) >= MIN_DAYS
        if ok:
            cache[sym] = rows
        json.dump(cache, open(path, "w"))
        print(f"[{i + 1}/{len(todo)}] {sym}: {'ok ' + str(len(rows)) if ok else 'FAIL'}", flush=True)
        time.sleep(0.15)
    return cache
