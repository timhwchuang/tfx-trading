"""ATR trail skew exit simulator (FT-018 · atr_trail_skew_900s)."""

from __future__ import annotations

from typing import Any

from reporting.forward_pnl import _direction_sign


def simulate_atr_trail_skew_exit(
    *,
    direction: str,
    entry_price: float,
    entry_ts: int,
    atr: float,
    ticks: list[tuple[int, float, int, int]],
    hard_stop_atr_k: float,
    be_trigger_atr_k: float | None,
    trail_arm_atr_k: float,
    trail_dist_atr_k: float,
    hard_tp_atr_k: float | None = 4.0,
    max_hold_sec: int = 900,
    min_atr_pts: float = 25.0,
    initial_stop_price: float | None = None,
) -> dict[str, Any]:
    """Walk tick path; BE → trail → hard TP per SPEC §5.0b state machine.

    ``be_trigger_atr_k=None`` disables breakeven arming (FT-018b wash probe).
    ``initial_stop_price`` overrides ATR-based hard stop when set (when at or below
    entry for long). Values above entry are treated as drive-low structural floors
    that only bind after price trades at/above the floor; stop fills use market price.
    """
    atr_eff = max(atr, min_atr_pts) if atr > 0 else min_atr_pts
    sign = _direction_sign(direction)
    is_long = direction in ("Long", "Buy", "buy", "long")

    struct_floor: float | None = None
    if is_long:
        atr_stop = entry_price - hard_stop_atr_k * atr_eff
        if initial_stop_price is not None:
            if initial_stop_price > entry_price:
                # Drive-low floor: only bind after price trades at/above the floor.
                struct_floor = initial_stop_price
                effective_stop = atr_stop
            else:
                effective_stop = initial_stop_price
        else:
            effective_stop = atr_stop
        peak = entry_price
    else:
        atr_stop = entry_price + hard_stop_atr_k * atr_eff
        if initial_stop_price is not None:
            if initial_stop_price < entry_price:
                struct_floor = initial_stop_price
                effective_stop = atr_stop
            else:
                effective_stop = initial_stop_price
        else:
            effective_stop = atr_stop
        peak = entry_price

    be_armed = False
    trail_armed = False
    end_ts = entry_ts + max_hold_sec
    mfe = 0.0
    mae = 0.0
    last_price = entry_price
    last_ts = entry_ts

    def _favorable_ext() -> float:
        if is_long:
            return peak - entry_price
        return entry_price - peak

    def _exit_payload(
        gross: float,
        *,
        exit_reason: str,
        hold_sec: int,
        exit_price: float,
    ) -> dict[str, Any]:
        return {
            "gross_pnl": round(gross, 2),
            "exit_reason": exit_reason,
            "hold_sec": hold_sec,
            "exit_price": round(exit_price, 2),
            "mfe": round(mfe, 2),
            "mae": round(mae, 2),
            "be_armed": be_armed,
            "trail_armed": trail_armed,
        }

    for ts, price, _vol, _tt in ticks:
        if ts < entry_ts:
            continue
        if ts > end_ts:
            break

        last_price = price
        last_ts = ts
        delta = sign * (price - entry_price)
        mfe = max(mfe, delta)
        mae = max(mae, -delta)

        if is_long:
            peak = max(peak, price)
        else:
            peak = min(peak, price)

        fav = _favorable_ext()

        if be_trigger_atr_k is not None and fav >= be_trigger_atr_k * atr_eff:
            be_armed = True
            if is_long:
                effective_stop = max(effective_stop, entry_price)
            else:
                effective_stop = min(effective_stop, entry_price)

        if fav >= trail_arm_atr_k * atr_eff:
            trail_armed = True

        if trail_armed:
            if is_long:
                trail_stop = peak - trail_dist_atr_k * atr_eff
                effective_stop = max(effective_stop, trail_stop)
            else:
                trail_stop = peak + trail_dist_atr_k * atr_eff
                effective_stop = min(effective_stop, trail_stop)

        if is_long and struct_floor is not None and peak >= struct_floor:
            effective_stop = max(effective_stop, struct_floor)
        elif not is_long and struct_floor is not None and peak <= struct_floor:
            effective_stop = min(effective_stop, struct_floor)

        stopped = False
        exit_price = price
        if is_long and price <= effective_stop:
            exit_price = price
            stopped = True
        elif not is_long and price >= effective_stop:
            exit_price = price
            stopped = True

        if stopped:
            gross = sign * (exit_price - entry_price)
            if be_armed and abs(exit_price - entry_price) < 0.01:
                reason = "breakeven"
            elif trail_armed:
                reason = "trail_stop"
            else:
                reason = "stop_loss"
            return _exit_payload(
                gross,
                exit_reason=reason,
                hold_sec=ts - entry_ts,
                exit_price=exit_price,
            )

        if hard_tp_atr_k is not None and fav >= hard_tp_atr_k * atr_eff:
            if is_long:
                tp_price = entry_price + hard_tp_atr_k * atr_eff
            else:
                tp_price = entry_price - hard_tp_atr_k * atr_eff
            gross = hard_tp_atr_k * atr_eff
            return _exit_payload(
                gross,
                exit_reason="take_profit",
                hold_sec=ts - entry_ts,
                exit_price=tp_price,
            )

    gross = sign * (last_price - entry_price)
    return _exit_payload(
        gross,
        exit_reason="horizon",
        hold_sec=max(0, last_ts - entry_ts),
        exit_price=last_price,
    )
