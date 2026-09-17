"""Shared data loading and feature engineering for the Stillwater Playbook.

Used by both the historical replay path and the live decision path. Only
`getagent.*` and the allowed scientific packages are imported here.

Frames are plain pandas DataFrames with a unique lowercase `date` column
(parsed to datetime), which is the canonical time field of the managed
kline endpoint. All feature engineering is column-based; frames are never
reindexed with side timestamps.
"""
from typing import Any

import numpy as np
import pandas as pd

from getagent import data

CHUNK_DAYS = 89  # the managed kline endpoint clamps each request to 90 days


def fetch_daily_bars(symbol: str, total_days: int) -> pd.DataFrame:
    """Concatenate 1d spot klines for one symbol across <=90d chunks.

    quote_volume is derived as volume * vwap (a USDT turnover proxy), since the
    managed spot kline response does not expose a native quote-volume column.
    """
    end = pd.Timestamp.now(tz="UTC")
    frames: list[pd.DataFrame] = []
    start = end - pd.Timedelta(days=total_days)
    cursor = start
    while cursor < end:
        seg_end = min(cursor + pd.Timedelta(days=CHUNK_DAYS), end)
        bars = data.crypto.spot.kline(
            symbol=symbol,
            interval="1d",
            exchange="bitget",
            start_time=int(cursor.timestamp() * 1000),
            end_time=int(seg_end.timestamp() * 1000),
            closed_only=True,
        )
        df = data.to_dataframe(bars)
        if df is not None and not df.empty:
            frames.append(df)
        cursor = seg_end + pd.Timedelta(days=1)

    if not frames:
        return pd.DataFrame()
    out = pd.concat(frames, ignore_index=True)
    out.columns = [str(c).lower() for c in out.columns]
    if "date" not in out.columns:
        if "time" in out.columns:
            out = out.rename(columns={"time": "date"})
        else:
            return pd.DataFrame()
    out["date"] = pd.to_datetime(out["date"], utc=True, errors="coerce")
    out = out.dropna(subset=["date"]).drop_duplicates(subset=["date"]).sort_values("date")
    out = out.reset_index(drop=True)
    if "volume" in out.columns and "vwap" in out.columns:
        out["quote_volume"] = pd.to_numeric(out["volume"], errors="coerce") * pd.to_numeric(
            out["vwap"], errors="coerce"
        )
    else:
        out["quote_volume"] = np.nan
    keep = [c for c in ("date", "open", "high", "low", "close", "volume", "vwap", "quote_volume") if c in out.columns]
    return out[keep]


def realized_vol(closes: pd.Series, lookback: int) -> pd.Series:
    """Rolling standard deviation of simple returns (decimal fraction)."""
    rets = pd.to_numeric(closes, errors="coerce").pct_change().clip(-0.6, 0.6)
    return rets.rolling(lookback).std()


def add_selection_columns(
    per_symbol: dict[str, pd.DataFrame], vol_lookback: int, gate_lookback: int
) -> dict[str, pd.DataFrame]:
    """Add vol40 and gate_ok columns per frame (column-based frames).

    gate_ok is True when the symbol's rolling median quote_volume is at or
    above the cross-sectional median of the configured basket on that date.
    If the quote-volume proxy has no usable coverage (managed klines may lack
    the vwap field), the gate degrades to pass-through and the caller must
    surface `gate: degraded` in metrics/meta.
    """
    qmed: dict[str, pd.Series] = {}
    for sym, df in per_symbol.items():
        if df is None or df.empty:
            continue
        qv = df.get("quote_volume")
        qmed[sym] = (
            pd.to_numeric(qv, errors="coerce").rolling(gate_lookback).median()
            if qv is not None
            else pd.Series(np.nan, index=df["date"])
        )

    gate_df = pd.DataFrame(qmed)
    gate = gate_df.median(axis=1)
    coverage = gate_df.notna().mean(axis=1)  # fraction of symbols with values
    usable = coverage > 0.5

    out: dict[str, pd.DataFrame] = {}
    for sym, df in per_symbol.items():
        if df is None or df.empty or sym not in qmed:
            continue
        indexed = df.set_index("date")
        indexed["vol40"] = realized_vol(indexed["close"], vol_lookback)
        day_usable = usable.reindex(indexed.index).fillna(False)
        if day_usable.all():
            indexed["gate_ok"] = (
                qmed[sym] >= gate.reindex(qmed[sym].index)
            ).fillna(False).astype(bool)
        else:
            # degraded liquidity data: gate disabled (pass-through), flagged
            indexed["gate_ok"] = True
        out[sym] = indexed.reset_index()
    return out


def gate_degraded(per_symbol: dict[str, pd.DataFrame]) -> bool:
    """True when the latest gate_ok values are all pass-through (degraded)."""
    flags = [df.get("gate_ok") for df in per_symbol.values() if df is not None and not df.empty]
    flags = [f for f in flags if f is not None]
    if not flags:
        return True
    last = pd.concat(flags, axis=1).iloc[-1]
    return bool(last.all()) and not bool(last.any() is False)


def select_targets(
    per_symbol: dict[str, pd.DataFrame], asof: Any, top_n: int
) -> list[str]:
    """Return the top_n lowest-vol symbols passing the gate as of `asof`."""
    scored: list[tuple[str, float]] = []
    for sym, df in per_symbol.items():
        if df is None or df.empty:
            continue
        frame = df.loc[df["date"] <= asof]
        if frame.empty:
            continue
        last = frame.iloc[-1]
        vol = last.get("vol40")
        gate = last.get("gate_ok", True)
        try:
            gate = bool(gate)
        except (TypeError, ValueError):
            gate = True
        if vol is None or not np.isfinite(float(vol)) or not gate:
            continue
        scored.append((sym, float(vol)))
    scored.sort(key=lambda t: t[1])
    return [sym for sym, _ in scored[:top_n]]


def build_schedule(per_symbol: dict[str, pd.DataFrame], top_n: int) -> dict[str, list[str]]:
    """Weekly selection schedule: date -> list of selected symbols.

    Evaluated every 7th common bar of the basket, using only data available
    up to that date (no lookahead).
    """
    if not per_symbol:
        return {}
    all_dates = sorted(
        set().union(*[set(df["date"]) for df in per_symbol.values() if df is not None and not df.empty])
    )
    schedule: dict[str, list[str]] = {}
    for step, ts in enumerate(all_dates, start=1):
        if step % 7 == 0:
            schedule[str(pd.Timestamp(ts).date())] = select_targets(per_symbol, ts, top_n)
    return schedule


def stale_ms(df: pd.DataFrame, interval_ms: int) -> int:
    """Milliseconds since the newest closed bar should have closed."""
    if df is None or df.empty or "date" not in df.columns:
        return 1 << 62
    last_open = pd.Timestamp(df["date"].max())
    now_ms = int(pd.Timestamp.now(tz="UTC").timestamp() * 1000)
    last_open_ms = int(pd.Timestamp(last_open).timestamp() * 1000)
    return now_ms - (last_open_ms + interval_ms)
