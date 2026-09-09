"""Factor and panel construction from cached candles."""
import numpy as np
import pandas as pd


def panel(cache: dict, field_idx: int, min_days: int = 200) -> pd.DataFrame:
    """candle row -> DataFrame indexed by UTC date, columns=symbols."""
    frames = {}
    for sym, rows in cache.items():
        idx = pd.to_datetime([int(r[0]) for r in rows], unit="ms").normalize()
        s = pd.Series([float(r[field_idx]) for r in rows], index=idx, name=sym)
        frames[sym] = s[~s.index.duplicated(keep="last")]
    df = pd.DataFrame(frames).sort_index()
    return df[df.columns[df.notna().sum() >= min_days]]


def panels(cache: dict, min_days: int = 200) -> dict:
    """returns dict with close/high/low/quote_vol panels (aligned symbols)."""
    o = panel(cache, 1, min_days=min_days)
    out = {
        "open": o,
        "close": panel(cache, 2, min_days=min_days)[o.columns],
        "high": panel(cache, 3, min_days=min_days)[o.columns],
        "low": panel(cache, 4, min_days=min_days)[o.columns],
        "quote_vol": panel(cache, 6, min_days=min_days)[o.columns],
    }
    return out


def volatility_factors(rets: pd.DataFrame) -> dict:
    """Volatility family (long LOW vol). All values are raw vols; direction applied in backtest."""
    return {
        "vol_10": rets.rolling(10).std(),
        "vol_20": rets.rolling(20).std(),
        "vol_40": rets.rolling(40).std(),
        "dnvol_20": rets.where(rets < 0, 0).rolling(20).std(),
    }
