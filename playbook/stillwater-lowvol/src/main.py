"""Entry point for the Stillwater Low-Vol Rotation Playbook.

Historical runs fetch 1d rToken klines from the managed data path, engineer
the volatility / liquidity features, run the managed replay engine, and emit
a summary signal. Live runs recompute the same weekly selection from fresh
bars and emit per-symbol signals through the managed follow-trade boundary.
"""
import json
import math
from pathlib import Path
from typing import Any

from getagent import backtest, data, runtime

from . import features

SYMBOLS_FALLBACK = ["RQQQUSDT", "RSPYUSDT", "RTSMUSDT", "RVOOUSDT"]
DAY_MS = 86_400_000


def _sanitize(value: Any) -> Any:
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def _sanitize_metrics(metrics: dict[str, Any]) -> dict[str, Any]:
    return {key: _sanitize(val) for key, val in metrics.items()}


def _cfg() -> dict[str, Any]:
    return runtime.manifest.get("strategy_config", {}) or {}


def _symbols(cfg: dict[str, Any]) -> list[str]:
    syms = [str(s).upper() for s in (cfg.get("trading_symbols") or SYMBOLS_FALLBACK)]
    return syms or SYMBOLS_FALLBACK


def _declared_instrument_ids(spec: dict[str, Any]) -> set[str]:
    out: set[str] = set()
    if not isinstance(spec, dict):
        return out
    instruments = list(spec.get("instruments") or [])
    if spec.get("instrument"):
        instruments.append(spec["instrument"])
    for inst in instruments:
        if not isinstance(inst, dict):
            continue
        raw = inst.get("raw_symbol") or str(inst.get("id", "")).split(".")[0]
        out.add(str(raw).upper())
    return out


def _equity_points(
    result: Any, starting_balance: float, net_pnl: float
) -> list[tuple[str, float]]:
    """Extract a real replay equity series; fall back to the two endpoints."""
    points: list[tuple[str, float]] = []
    try:
        reports = (result.raw or {}).get("reports") or {}
        account_report = reports.get("account") or []
        for row in account_report:
            ts = str(row.get("timestamp") or row.get("time") or "")
            total = row.get("total") or row.get("total_balance")
            if ts and total is not None:
                points.append((ts, float(total)))
    except Exception:
        points = []
    if not points and starting_balance > 0:
        points = [("start", starting_balance), ("end", starting_balance + net_pnl)]
    return points


def _write_outputs(result: Any, net_pnl: float, starting_balance: float) -> None:
    out_dir = Path("/workspace/output")
    out_dir.mkdir(parents=True, exist_ok=True)

    raw: dict[str, Any] = {}
    try:
        raw = dict(result.raw or {})
    except Exception:
        raw = {}

    # engine summary is account-basis; overwrite with strategy-basis numbers
    raw["net_pnl"] = round(net_pnl, 4)
    raw["starting_balance"] = starting_balance
    if starting_balance > 0:
        raw["total_return_pct"] = round(net_pnl / starting_balance * 100.0, 4)

    (out_dir / "backtest_report.json").write_text(json.dumps(raw, default=str))

    lines = ["timestamp,value,nav"]
    for ts, value in _equity_points(result, starting_balance, net_pnl):
        nav = (value / starting_balance) if starting_balance > 0 else 1.0
        lines.append(f"{ts},{round(value, 4)},{round(nav, 6)}")
    (out_dir / "equity_curve.csv").write_text("\n".join(lines) + "\n")


def _run_historical() -> None:
    import pandas as pd  # noqa: F401  (used inside build_feature_frame lambdas)

    cfg = _cfg()
    symbols = _symbols(cfg)
    top_n = int(cfg.get("top_n", 3) or 3)
    vol_lookback = int(cfg.get("vol_lookback", 40) or 40)
    gate_lookback = int(cfg.get("gate_lookback", 20) or 20)
    # generous fetch so the replay window starts with warmed-up features
    total_days = 420

    per_symbol: dict[str, Any] = {}
    for sym in symbols:
        frame = features.fetch_daily_bars(sym, total_days)
        if frame is not None and not frame.empty:
            per_symbol[sym] = frame

    if not per_symbol:
        runtime.emit_signal(
            action="watch",
            symbol=symbols[0],
            confidence=0.0,
            metrics={"rows": 0},
            meta={"reason": "no historical bars returned"},
        )
        return

    per_symbol = features.add_selection_columns(per_symbol, vol_lookback, gate_lookback)

    spec = runtime.backtest_spec or {}
    declared = _declared_instrument_ids(spec)
    loaded = {
        sym: frame
        for sym, frame in per_symbol.items()
        if (not declared or sym in declared) and frame is not None and not frame.empty
    }

    ohlcv_data = {}
    for sym, frame in loaded.items():
        ohlcv_data[f"{sym}.BITGET"] = backtest.build_feature_frame(
            frame,
            base_datetime_index="date",
        )

    # inject the precomputed, lookahead-free selection schedule into the
    # strategy config so the replay engine executes it deterministically.
    schedule = features.build_schedule(per_symbol, top_n)

    # hand the lookahead-free selection schedule to the replay strategy via
    # the workspace filesystem (the sandbox resolves backtest.yaml itself;
    # mutating the resolved spec is neither needed nor allowed).
    try:
        out_dir = Path("/workspace/output")
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "selection_schedule.json").write_text(
            json.dumps(
                {
                    "schedule": {str(k): list(v) for k, v in schedule.items()},
                    "symbols": sorted(loaded.keys()),
                    "starting_balance": 10000.0,
                }
            )
        )
    except Exception:
        pass

    result = backtest.run(ohlcv_data=ohlcv_data, spec=spec)

    summary = result.summary or {}
    try:
        net_pnl = float(summary.get("net_pnl", 0) or 0)
    except (TypeError, ValueError):
        net_pnl = 0.0
    try:
        starting_balance = float(summary.get("starting_balance") or 0)
    except (TypeError, ValueError):
        starting_balance = 0.0

    _write_outputs(result, net_pnl, starting_balance)

    action = "long" if net_pnl > 0 else "watch"
    metrics = _sanitize_metrics(
        {
            "total_return_pct": result.total_return_pct,
            "net_pnl": net_pnl,
            "starting_balance": starting_balance,
            "sharpe_ratio": result.sharpe_ratio,
            "max_drawdown_pct": result.max_drawdown_pct,
            "win_rate": result.win_rate,
            "total_trades": result.total_trades,
            "profit_factor": result.profit_factor,
            "symbols_requested": len(symbols),
            "symbols_loaded": len(loaded),
            "skipped_symbols": sorted(set(symbols) - set(loaded.keys())),
            "weekly_selections": len(schedule),
            "weekly_selections_nonempty": sum(1 for v in schedule.values() if v),
            "gate": "degraded" if features.gate_degraded(per_symbol) else "ok",
        }
    )
    debug_meta = {}
    try:
        dbg = Path("/workspace/output/debug.json")
        if dbg.exists():
            debug_meta = {"debug": json.loads(dbg.read_text())}
    except Exception:
        debug_meta = {}

    runtime.emit_signal(
        action=action,
        symbol=",".join(symbols[:3]),
        confidence=_sanitize(result.win_rate) or 0.0,
        metrics=metrics,
        meta={
            "strategy": "stillwater-lowvol",
            "schedule_preview": {k: v for k, v in list(schedule.items())[-3:]},
            **debug_meta,
        },
    )


def _run_live() -> None:
    cfg = _cfg()
    symbols = _symbols(cfg)
    top_n = int(cfg.get("top_n", 3) or 3)
    vol_lookback = int(cfg.get("vol_lookback", 40) or 40)
    gate_lookback = int(cfg.get("gate_lookback", 20) or 20)
    margin_budget = str(cfg.get("margin_budget", "50") or "50")

    # live needs vol + gate history; one 90d fetch per symbol suffices and
    # stays inside the endpoint's per-request clamp.
    per_symbol: dict[str, Any] = {}
    stale: list[str] = []
    for sym in symbols:
        frame = features.fetch_daily_bars(sym, 90)
        if frame is None or frame.empty:
            continue
        if features.stale_ms(frame, DAY_MS) > 2 * DAY_MS:
            stale.append(sym)
            continue
        per_symbol[sym] = frame

    per_symbol = features.add_selection_columns(per_symbol, vol_lookback, gate_lookback)
    if not per_symbol:
        runtime.emit_signal(
            action="hold",
            symbol=",".join(symbols),
            confidence=0.0,
            metrics={"rows": 0},
            meta={"reason": "insufficient closed bars"},
        )
        return

    asof = max(df.index.max() for df in per_symbol.values())
    selected = features.select_targets(per_symbol, asof, top_n)
    previous = runtime.get_emitted_signals() or []
    previous_selected: set[str] = set()
    if previous:
        meta = getattr(previous[-1], "meta", None) or {}
        sel = meta.get("selected")
        if isinstance(sel, list):
            previous_selected = {str(s).upper() for s in sel}

    if not selected:
        runtime.emit_signal(
            action="hold",
            symbol=",".join(symbols),
            confidence=0.0,
            metrics={"candidates": len(per_symbol)},
            meta={"reason": "no name passed the liquidity gate", "selected": []},
        )
        return

    budget = float(margin_budget) if _is_number(margin_budget) else 50.0
    per_name_budget = f"{budget / len(selected):.2f}"

    for sym in per_symbol.keys():
        if sym in selected:
            continue
        runtime.emit_signal_or_follow(
            action="close",
            symbol=sym,
            confidence=0.0,
            metrics={"selected": list(selected)},
            meta={"selected": list(selected), "reason": "rotated out"},
            execute_trade=lambda s=sym: _execute_spot_close(symbol=s),
        )
    for sym in selected:
        if sym in previous_selected:
            # already positioned from the previous cycle; entry skipped here
            continue
        runtime.emit_signal_or_follow(
            action="long",
            symbol=sym,
            confidence=0.8,
            metrics={"selected": list(selected), "per_name_budget": per_name_budget},
            meta={"selected": list(selected), "reason": "lowest-vol selection"},
            execute_trade=lambda s=sym: _execute_spot_entry(
                symbol=s, budget=per_name_budget
            ),
        )


def _is_number(value: Any) -> bool:
    try:
        float(value)
        return True
    except (TypeError, ValueError):
        return False


def _execute_spot_entry(*, symbol: str, budget: str) -> dict[str, Any]:
    from getagent import trade

    qty_plan = trade.helpers.compute_qty(
        symbol=symbol,
        market="spot",
        budget_amount=budget,
    )
    result = trade.spot.open_market_buy(symbol=symbol, qty=qty_plan.qty)
    if not trade.is_success(result):
        raise RuntimeError(f"spot open failed: {result}")
    return {"qty": str(qty_plan.qty), "result": result}


def _execute_spot_close(*, symbol: str) -> dict[str, Any]:
    from getagent import trade

    result = trade.spot.close_position(symbol=symbol)
    if not trade.is_success(result):
        raise RuntimeError(f"spot close failed: {result}")
    return {"result": result}


def run() -> None:
    if runtime.is_historical():
        _run_historical()
        return
    if runtime.is_live():
        _run_live()
        return
    raise ValueError(f"unsupported evaluation_mode={runtime.evaluation_mode!r}")


if __name__ == "__main__":
    run()
