"""FVG mid trail skew exit simulator (FT-019 · fvg_mid_trail_skew_900s)."""

from __future__ import annotations

from typing import Any

from reporting.forward_pnl import _direction_sign


def simulate_fvg_mid_trail_skew_exit(
    *,
    direction: str,
    entry_price: float,
    entry_ts: int,
    fvg_mid: float,
    atr: float,
    ticks: list[tuple[int, float, int, int]],
    be_risk_k: float = 1.0,
    trail_arm_risk_k: float = 2.0,
    trail_arm_atr_k: float = 1.5,
    trail_dist_atr_k: float = 0.5,
    hard_tp_risk_k: float | None = 4.0,
    max_hold_sec: int = 900,
    min_atr_pts: float = 25.0,
) -> dict[str, Any]:
    """Walk tick path; initial stop=fvg_mid · BE/trail anchored on risk_unit."""
    atr_eff = max(atr, min_atr_pts) if atr > 0 else min_atr_pts
    sign = _direction_sign(direction)
    is_long = direction in ("Long", "Buy", "buy", "long")

    if is_long:
        risk_unit = entry_price - fvg_mid
        if risk_unit <= 0:
            return {
                "gross_pnl": 0.0,
                "exit_reason": "invalid_risk_unit",
                "hold_sec": 0,
                "exit_price": entry_price,
                "mfe": 0.0,
                "mae": 0.0,
                "be_armed": False,
                "trail_armed": False,
                "risk_unit": round(risk_unit, 2),
            }
        effective_stop = fvg_mid
        peak = entry_price
    else:
        risk_unit = fvg_mid - entry_price
        if risk_unit <= 0:
            return {
                "gross_pnl": 0.0,
                "exit_reason": "invalid_risk_unit",
                "hold_sec": 0,
                "exit_price": entry_price,
                "mfe": 0.0,
                "mae": 0.0,
                "be_armed": False,
                "trail_armed": False,
                "risk_unit": round(risk_unit, 2),
            }
        effective_stop = fvg_mid
        peak = entry_price

    be_armed = False
    trail_armed = False
    end_ts = entry_ts + max_hold_sec
    mfe = 0.0
    mae = 0.0
    last_price = entry_price
    last_ts = entry_ts

    risk_trail_threshold = trail_arm_risk_k * risk_unit
    atr_trail_threshold = trail_arm_atr_k * atr_eff

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
            "risk_unit": round(risk_unit, 2),
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

        if fav >= be_risk_k * risk_unit:
            be_armed = True
            if is_long:
                effective_stop = max(effective_stop, entry_price)
            else:
                effective_stop = min(effective_stop, entry_price)

        if not trail_armed:
            if fav >= risk_trail_threshold or fav >= atr_trail_threshold:
                trail_armed = True

        if trail_armed:
            if is_long:
                trail_stop = peak - trail_dist_atr_k * atr_eff
                effective_stop = max(effective_stop, trail_stop)
            else:
                trail_stop = peak + trail_dist_atr_k * atr_eff
                effective_stop = min(effective_stop, trail_stop)

        stopped = False
        exit_price = price
        if is_long and price <= effective_stop:
            exit_price = effective_stop
            stopped = True
        elif not is_long and price >= effective_stop:
            exit_price = effective_stop
            stopped = True

        if stopped:
            gross = sign * (exit_price - entry_price)
            if be_armed and abs(exit_price - entry_price) < 0.01:
                reason = "breakeven"
            elif trail_armed:
                reason = "trail_stop"
            elif abs(exit_price - fvg_mid) < 0.01:
                reason = "fvg_mid_stop"
            else:
                reason = "stop_loss"
            return _exit_payload(
                gross,
                exit_reason=reason,
                hold_sec=ts - entry_ts,
                exit_price=exit_price,
            )

        if hard_tp_risk_k is not None and fav >= hard_tp_risk_k * risk_unit:
            if is_long:
                tp_price = entry_price + hard_tp_risk_k * risk_unit
            else:
                tp_price = entry_price - hard_tp_risk_k * risk_unit
            gross = hard_tp_risk_k * risk_unit
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
