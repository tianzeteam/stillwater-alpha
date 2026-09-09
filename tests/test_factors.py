import numpy as np
import pandas as pd
import pytest

from factors import panel, panels, volatility_factors


def _rows_for(sym, ts_list, close_fn, field=2):
    """Bitget candle row layout: [ts, open, close, high, low, base_vol, quote_vol, usdt_vol]."""
    out = []
    for i, ts in enumerate(ts_list):
        c = close_fn(i, sym)
        row = [str(ts), str(c), str(c), str(c * 1.01), str(c * 0.99), "10.0", "1000.0", "1000.0"]
        row[field] = str(c) if field == 2 else row[field]
        out.append(row)
    return out


def test_panel_dedups_and_keeps_last():
    ts = [1704067200000, 1704067200000 + 3600 * 1000, 1704153600000]  # same UTC day twice
    cache = {"S_A": _rows_for("S_A", ts, lambda i, s: 100.0 + i)}
    df = panel(cache, 2, min_days=1)
    assert len(df) == 2                                # two distinct days
    assert df["S_A"].iloc[0] == 101.0                  # later candle of the same day wins
    assert df["S_A"].iloc[1] == 102.0

def test_panel_filters_symbols_below_min_days():
    ts = list(range(1704067200000, 1704067200000 + 10 * 86400 * 1000, 86400 * 1000))
    cache = {
        "S_LONG": _rows_for("S_LONG", ts, lambda i, s: 100.0),
        "S_SHORT": _rows_for("S_SHORT", ts[:5], lambda i, s: 50.0),
    }
    df = panel(cache, 2, min_days=8)
    assert list(df.columns) == ["S_LONG"]


def test_panels_align_symbols_across_fields():
    ts = list(range(1704067200000, 1704067200000 + 10 * 86400 * 1000, 86400 * 1000))
    cache = {"S_A": _rows_for("S_A", ts, lambda i, s: 100.0 + i)}
    P = panels(cache, min_days=8)
    for name in ("open", "close", "high", "low", "quote_vol"):
        assert name in P
        assert P[name].shape == P["close"].shape
    # field 6 is quote volume
    assert (P["quote_vol"]["S_A"] == 1000.0).all()


def test_volatility_factors_values_and_direction():
    idx = pd.date_range("2026-01-01", periods=60, freq="D")
    rng = np.random.default_rng(7)
    # S_CALM: small noise; S_WILD: big noise -> rolling std must rank S_WILD higher
    calm = pd.Series(0.001 * rng.standard_normal(60), index=idx, name="S_CALM")
    wild = pd.Series(0.05 * rng.standard_normal(60), index=idx, name="S_WILD")
    rets = pd.concat([calm, wild], axis=1)
    F = volatility_factors(rets)
    assert set(F) == {"vol_10", "vol_20", "vol_40", "dnvol_20"}
    last = F["vol_20"].iloc[-1]
    assert last["S_WILD"] > last["S_CALM"]
    # downside vol: calm side's down days are tiny -> dnvol well below total vol
    assert F["dnvol_20"]["S_CALM"].iloc[-1] <= F["vol_20"]["S_CALM"].iloc[-1]
    # all values non-negative (they are raw vols; direction is applied downstream)
    assert (F["vol_40"].dropna() >= 0).all().all()
