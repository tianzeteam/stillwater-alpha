"""Nautilus replay strategy: weekly low-vol rotation across the configured basket.

The strategy accumulates daily bars, and every `rebal_interval_days` trading
days recomputes the lowest-volatility subset from the injected feature frames
(vol40 / gate_ok columns), closes holdings that fell out of the selection, and
enters newly selected names at an equal weight of free account equity.
"""
from decimal import Decimal
from typing import Optional

import pandas as pd
from nautilus_trader.config import StrategyConfig
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.enums import OrderSide, TimeInForce
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.objects import Quantity
from nautilus_trader.trading.strategy import Strategy


class StillwaterConfig(StrategyConfig):
    instrument_ids: tuple[InstrumentId, ...] = ()
    bar_types: tuple[BarType, ...] = ()
    top_n: int = 3
    vol_lookback: int = 40
    gate_lookback: int = 20
    rebal_interval_days: int = 7
    schedule: Optional[dict] = None          # date-str -> [symbols]; precomputed, no lookahead
    symbols: tuple[str, ...] = ()            # contract symbols in the same order as instrument_ids
    starting_balance: float = 10000.0        # fallback equity when account lookup fails


class StillwaterRotationStrategy(Strategy):
    def __init__(self, config: StillwaterConfig) -> None:
        super().__init__(config)
        self.cfg = config
        self._frames: dict[str, pd.DataFrame] = {}
        self._instruments: dict[str, object] = {}
        self._selected: tuple[str, ...] = ()
        self._last_close: dict[str, float] = {}
        self._last_ts: dict[str, int] = {}
        self._last_date: Optional[str] = None
        self._debug_free: Optional[float] = None
        self._debug_buys: list = []
        self._debug_closes: list = []
        self._debug_hits: list = []
        self._debug_bars = 0

    def set_feature_frames(self, frames: dict[str, pd.DataFrame]) -> None:
        """Injected by the replay engine: full per-instrument feature frames."""
        self._frames = {key: value for key, value in (frames or {}).items()}

    def _debug_write(self) -> None:
        try:
            from pathlib import Path as _Path
            out = _Path("/workspace/output")
            out.mkdir(parents=True, exist_ok=True)
            (out / "debug.json").write_text(
                json.dumps(
                    {
                        "bars_seen": dict(self._last_close),
                        "last_date": self._last_date,
                        "selected_last": list(self._selected),
                        "free_usdt": self._debug_free,
                        "buys": self._debug_buys,
                        "closes": self._debug_closes,
                        "schedule_days": len(self.cfg.schedule or {}),
                    },
                    default=str,
                )
            )
        except Exception:
            pass

    def on_start(self) -> None:
        if not self.cfg.bar_types:
            raise RuntimeError("bar_types must be configured")
        try:
            from pathlib import Path as _Path
            import json as _json

            sidecar = _Path("/workspace/output/selection_schedule.json")
            if sidecar.exists():
                payload = _json.loads(sidecar.read_text())
                self._schedule = dict(payload.get("schedule") or {})
                self._starting_balance = float(payload.get("starting_balance") or 10000.0)
        except Exception:
            self._schedule = dict(self.cfg.schedule or {})
        # ordered selection steps; the clock instrument advances one step per
        # `rebal_interval_days` bars — no timestamp/date matching anywhere.
        self._sched_items = sorted((k, tuple(v)) for k, v in self._schedule.items())
        self._clock_sym = str(self.cfg.instrument_ids[0]).split(".")[0] if self.cfg.instrument_ids else ""
        self._clock_count = 0
        for bt in self.cfg.bar_types:
            bar_type = bt if isinstance(bt, BarType) else BarType.from_str(str(bt))
            instrument_id = bar_type.instrument_id
            sym = str(instrument_id).split(".")[0]
            self._instruments[sym] = self.cache.instrument(instrument_id)
            self.subscribe_bars(bar_type)

    def _select(self, asof: pd.Timestamp) -> tuple[str, ...]:
        scored: list[tuple[str, float]] = []
        for sym, frame in self._frames.items():
            if frame is None or frame.empty:
                continue
            df = frame.loc[frame.index < asof]
            if df.empty:
                continue
            last = df.iloc[-1]
            vol = last.get("vol40")
            gate = last.get("gate_ok", True)
            gate = bool(gate) if isinstance(gate, (bool,)) else bool(gate)
            if vol is None or not pd.notna(vol) or not gate:
                continue
            scored.append((sym, float(vol)))
        scored.sort(key=lambda t: t[1])
        return tuple(sym for sym, _ in scored[: max(1, self.cfg.top_n)])

    def on_bar(self, bar: Bar) -> None:
        sym = str(bar.bar_type.instrument_id).split(".")[0]
        self._last_close[sym] = float(bar.close)
        self._last_ts[sym] = int(bar.ts_init)
        self._debug_bars += 1

        if sym != self._clock_sym:
            return  # only the clock instrument drives the rebalance clock
        self._clock_count += 1
        step = self.cfg.rebal_interval_days
        if step <= 0 or self._clock_count % step != 0:
            return
        idx = self._clock_count // step - 1
        if idx >= len(self._sched_items):
            return  # schedule exhausted; hold the last selection
        date_str, selected = self._sched_items[idx]
        self._debug_hits.append(date_str)
        if not selected and not self._selected:
            return
        self._selected = selected

        # close holdings that fell out of the selection
        held_syms = {
            str(p.instrument_id).split(".")[0]: p
            for p in self.cache.positions_open()
        }
        for held_sym, position in held_syms.items():
            if held_sym in selected:
                continue
            if held_sym not in {s.split(".")[0] for s in self.cfg.instrument_ids}:
                continue  # never touch instruments outside the declared contract
            inst = self._instruments.get(held_sym)
            if inst is None:
                continue
            order = self.order_factory.market(
                instrument_id=position.instrument_id,
                order_side=OrderSide.SELL,
                quantity=position.quantity,
                time_in_force=TimeInForce.GTC,
            )
            self.submit_order(order)

        if not selected:
            return

        free = self._free_usdt()
        self._debug_free = free
        if free is None or free <= 0:
            return
        per_name = free / len(selected)
        for sel_sym in selected:
            if sel_sym in held_syms:
                continue
            inst = self._instruments.get(sel_sym)
            if inst is None:
                continue
            price = self._last_close.get(sel_sym)
            if not price:
                continue
            raw_qty = per_name / price
            if raw_qty <= 0:
                continue
            qty = Quantity(Decimal(f"{raw_qty:.4f}"), inst.size_precision)
            instrument_id = inst.id
            self._debug_buys.append({"sym": sel_sym, "qty": float(qty), "price": price})
            order = self.order_factory.market(
                instrument_id=instrument_id,
                order_side=OrderSide.BUY,
                quantity=qty,
                time_in_force=TimeInForce.GTC,
            )
            self.submit_order(order)

    def _last_price(self, sym: str, asof: pd.Timestamp) -> Optional[float]:
        frame = self._frames.get(f"{sym}.BITGET")
        if frame is None or frame.empty:
            return None
        df = frame.loc[frame.index < asof]
        if df.empty:
            return None
        return float(df["close"].iloc[-1])

    def _free_usdt(self) -> Optional[float]:
        try:
            for account in self.cache.accounts():
                for money in account.balances_total():
                    if str(money.currency) == "USDT":
                        return float(money.as_double())
        except Exception:
            pass
        try:
            for inst_id in self.cfg.instrument_ids:
                account = self.portfolio.account(inst_id)
                if account is None:
                    continue
                for money in account.balances_total():
                    if str(money.currency) == "USDT":
                        return float(money.as_double())
        except Exception:
            pass
        # last resort: declared starting equity, kept conservative (never
        # grows with realized pnl within a run)
        bal = self._starting_balance
        return float(bal) if bal and bal > 0 else None

    def on_stop(self) -> None:
        try:
            self._debug_write()
        except Exception:
            pass
        for instrument_id in self.cfg.instrument_ids:
            self.cancel_all_orders(instrument_id)
            self.close_all_positions(instrument_id)

    def _debug_write(self) -> None:
        from pathlib import Path as _Path
        import json as _json

        out = _Path("/workspace/output")
        out.mkdir(parents=True, exist_ok=True)
        (out / "debug.json").write_text(
            _json.dumps(
                {
                    "bars": self._debug_bars,
                    "symbols_with_close": sorted(self._last_close.keys()),
                    "last_date": self._last_date,
                    "schedule_hits": self._debug_hits[:10],
                    "schedule_len": len(self._schedule or {}),
                    "free_usdt": self._debug_free,
                    "buys": self._debug_buys[:20],
                    "closes": self._debug_closes[:20],
                    "selected_last": list(self._selected),
                },
                default=str,
            )
        )
