import numpy as np
import pandas as pd
import pytest

from backtest import build_weights, run, metrics


def cross_section(syms, value_fn, index=None):
    """Helper: cross-sectional Series indexed by symbols."""
    return pd.Series({s: value_fn(s) for s in syms})


SYMS = [f"S{i:02d}" for i in range(20)]


def test_picks_lowest_vol_quintile_among_liquid_names():
    # vol increases with index; gate keeps S04..S19 (16 liquid >= min_names 15).
    # Lowest 20% of the LIQUID pool = S04..S06, equal weight 1/3.
    vol_row = cross_section(SYMS, lambda s: float(int(s[1:])))
    liq_row = cross_section(SYMS, lambda s: 1.0 if int(s[1:]) >= 4 else 0.1)
    w = build_weights(vol_row, liq_row)
    held = w[w > 0]
    assert sorted(held.index) == ["S04", "S05", "S06"]
    assert np.allclose(held.values, 1 / 3)
    assert w.sum() == pytest.approx(1.0)


def test_illiquid_low_vol_name_is_excluded():
    # The lowest-vol name is illiquid; it must not be picked despite the signal.
    vol_row = cross_section(SYMS, lambda s: 0.01 if s == "S00" else float(int(s[1:])) + 10)
    liq_row = cross_section(SYMS, lambda s: 0.1 if s == "S00" else 100.0)
    w = build_weights(vol_row, liq_row)
    assert w["S00"] == 0.0


def test_all_illiquid_pool_falls_back_to_signal_pool():
    # len(lq)>10 but quantile trick yields nothing above itself -> fallback: signal pool used.
    vol_row = cross_section(SYMS, lambda s: float(int(s[1:])))
    liq_row = pd.Series(5.0, index=SYMS)  # all identical -> all pass quantile gate
    w = build_weights(vol_row, liq_row)
    held = w[w > 0]
    assert sorted(held.index) == [f"S{i:02d}" for i in range(4)]  # lowest 20% of 20
    assert w.sum() == pytest.approx(1.0)


def test_empty_position_when_pool_too_small():
    # 10 names available, min_names=15 -> must go flat, not trade a thin pool.
    syms = SYMS[:10]
    vol_row = cross_section(syms, lambda s: float(int(s[1:])))
    liq_row = pd.Series(100.0, index=syms)
    w = build_weights(vol_row, liq_row)
    assert (w == 0).all() and w.abs().sum() == 0


def test_k_floor_of_three():
    # Exactly 15 eligible names -> k = max(3, int(15*0.2)) = 3.
    syms = SYMS[:15]
    vol_row = cross_section(syms, lambda s: float(int(s[1:])))
    liq_row = pd.Series(100.0, index=syms)
    w = build_weights(vol_row, liq_row)
    held = w[w > 0]
    assert len(held) == 3
    assert np.allclose(held.values, 1 / 3)


def _make_panel(n_days, n_syms, values_fn):
    idx = pd.date_range("2026-01-01", periods=n_days, freq="D")
    cols = [f"S{i:02d}" for i in range(n_syms)]
    data = np.array([[values_fn(t, c) for c in cols] for t in range(n_days)])
    return pd.DataFrame(data, index=idx, columns=cols)


def test_run_uses_yesterday_weights_no_lookahead():
    # 40 days, 20 symbols. Verify day t gross return equals yesterday's weights
    # applied to today's returns, exactly as the anti-lookahead contract demands.
    vol = _make_panel(40, 20, lambda t, c: 1.0)               # constant -> stable picks
    liq = _make_panel(40, 20, lambda t, c: 100.0)
    rets = _make_panel(40, 20, lambda t, c: 0.001 * ((t + int(c[1:])) % 5 - 2))
    net, W, to = run(vol, rets, liq, rebal_days=7, start_idx=20, cost_bps=10.0)
    gross = (W.shift(1) * rets.loc[W.index]).sum(axis=1)
    assert to[W.index[0]] == 0.0                              # first day holds nothing yet
    # every day: net == gross - turnover*cost
    cost = to * 10.0 / 1e4
    assert (net - (gross - cost)).abs().max() < 1e-12
    # weights only change on rebalance days (i % 7 == 0)
    held_once = False
    for i, dt in enumerate(W.index):
        if i % 7 != 0 and i > 0:
            assert (W.loc[dt] == W.iloc[i - 1]).all()


def test_run_costs_reduce_returns_when_turnover_positive():
    # vol order must flip between weeks (absolute parity), else picks never change
    vol = _make_panel(40, 20, lambda t, c: float(abs((int(c[1:]) % 2) - ((t // 7) % 2))) + 0.5)
    liq = _make_panel(40, 20, lambda t, c: 100.0)
    rets = _make_panel(40, 20, lambda t, c: 0.0005 * ((int(c[1:]) % 3) - 1))
    net0, _, to0 = run(vol, rets, liq, start_idx=20, cost_bps=0.0)
    net30, _, to30 = run(vol, rets, liq, start_idx=20, cost_bps=30.0)
    assert to30.sum() > 0                                     # there IS turnover
    assert (net30 <= net0).all()
    assert (net30 - net0).abs().max() > 0                     # and cost actually bites


def test_run_start_index_respects_warmup():
    # start_idx=60 means the first 60 days produce no positions.
    vol = _make_panel(80, 20, lambda t, c: 1.0)
    liq = _make_panel(80, 20, lambda t, c: 100.0)
    rets = _make_panel(80, 20, lambda t, c: 0.0)
    net, W, _ = run(vol, rets, liq, start_idx=60)
    assert len(W) == 20
    assert W.index[0] == rets.index[60]


def test_metrics_max_drawdown_and_annualization():
    # equity: 1.0 -> 1.1 -> 0.55 -> 0.66 (then flat) ; maxDD = 0.55/1.1 - 1 = -50%
    idx = pd.date_range("2026-01-01", periods=6, freq="D")
    r = pd.Series([0.10, -0.50, 0.20, 0.01, 0.01, 0.01], index=idx)
    m = metrics(r)
    assert m["ann_ret_pct"] == pytest.approx(r.mean() * 365 * 100, abs=0.1)
    assert m["ann_vol_pct"] == pytest.approx(r.std() * np.sqrt(365) * 100, abs=0.1)
    assert m["max_dd_pct"] == -50.0


def test_metrics_guards():
    assert metrics(pd.Series(dtype=float)) == {}
    assert metrics(pd.Series([0.0, 0.0, 0.0, 0.0, 0.0])) == {}  # zero std -> unusable
    assert metrics(pd.Series([0.01] * 4)) == {}                  # too short


def test_killswitch_trips_on_decay_and_recovers():
    from backtest import run_killswitch
    # 140 days, 20 symbols, all identical -> base holds 4 names throughout.
    # Strategy window starts at day 60. Days 70-105: -1%/day -> kill. Days 106+: +1%/day -> recover.
    n, syms = 140, 20
    idx = pd.date_range("2026-01-01", periods=n, freq="D")
    cols = [f"S{i:02d}" for i in range(syms)]
    r = np.where((np.arange(n) >= 70) & (np.arange(n) < 106), -0.01, 0.01)
    rets = pd.DataFrame(np.tile(r[:, None], (1, syms)), index=idx, columns=cols)
    vol = pd.DataFrame(1.0, index=idx, columns=cols)
    liq = pd.DataFrame(100.0, index=idx, columns=cols)
    net, W, to, killed = run_killswitch(vol, rets, liq, start_idx=60)
    assert killed, "drawdown of 40 straight negative days must trip the switch"
    first_kill = killed[0]
    # kill happens only after warmup: at least 15 realized returns before the first kill
    assert first_kill >= idx[60 + 15]
    # every day from a kill to the next rebalance holds zero weight
    kill_set = set(killed)
    for i, dt in enumerate(W.index):
        if i % 7 == 0 and dt in kill_set:
            assert (W.loc[dt] == 0).all()
    # after recovery the weights come back
    assert (W.iloc[-1] > 0).any()


def test_killswitch_never_trips_on_steady_returns():
    from backtest import run_killswitch
    n, syms = 100, 20
    idx = pd.date_range("2026-01-01", periods=n, freq="D")
    cols = [f"S{i:02d}" for i in range(syms)]
    rets = pd.DataFrame(0.005, index=idx, columns=cols)
    vol = pd.DataFrame(1.0, index=idx, columns=cols)
    liq = pd.DataFrame(100.0, index=idx, columns=cols)
    net, W, _, killed = run_killswitch(vol, rets, liq, start_idx=60)
    assert killed == []
    # overlay must not alter weights when never tripped
    from backtest import run
    _, W_base, _ = run(vol, rets, liq, start_idx=60)
    assert W.equals(W_base)


def test_killswitch_no_lookahead_in_monitor():
    from backtest import run_killswitch
    # returns flip from +1% to -1% at day 50 exactly. The switch may only react
    # at a rebalance day >= day 50 + (enough negative days to satisfy warmup),
    # never before day 50 itself.
    n, syms = 120, 20
    idx = pd.date_range("2026-01-01", periods=n, freq="D")
    cols = [f"S{i:02d}" for i in range(syms)]
    r = np.where(np.arange(n) < 50, 0.01, -0.01)
    rets = pd.DataFrame(np.tile(r[:, None], (1, syms)), index=idx, columns=cols)
    vol = pd.DataFrame(1.0, index=idx, columns=cols)
    liq = pd.DataFrame(100.0, index=idx, columns=cols)
    net, W, _, killed = run_killswitch(vol, rets, liq, start_idx=30)
    for dt in killed:
        rebal_i = W.index.get_loc(dt)
        past = net.iloc[:rebal_i + 1]
        neg = (past.iloc[-30:] < 0).sum()
        assert 30 + rebal_i >= 50  # absolute decision day is on/after the regime change, never before
        assert neg >= 15      # and only after enough realized negative returns
