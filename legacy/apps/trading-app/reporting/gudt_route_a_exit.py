"""FT-018b Route A checkpoint extension exits — EMA stack take-profit."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Any, Literal

from reporting.gudt_wash_probe import (
    SEALED_BE,
    SEALED_HARD_TP,
    SEALED_K_SL,
    SEALED_MAX_HOLD,
    SEALED_TRAIL_ARM,
    SEALED_TRAIL_DIST,
    DayWashContext,
    ProbeEntry,
    ext_open_atr,
    _simulate_exit,
)
from reporting.simulate_atr_trail_skew_exit import simulate_atr_trail_skew_exit
from storage.kbar_loader import KBarRecord
from strategy_vwap_momentum.trend import ema

ExtensionExit = Literal[
    "trail",
    "ema3",
    "ema5",
    "ema_either",
    "ema_both",
    "trail_or_ema_either",
]

CHECKPOINT_SEC = SEALED_MAX_HOLD
EXT_MAX_HOLD_SEC = 3600


@dataclass(frozen=True)
class EmaStackParams:
    fast: int = 9
    slow: int = 21
    tf_min: int = 3


@dataclass(frozen=True)
class RouteAParams:
    ext_open_min: float = 5.0
    checkpoint_sec: int = CHECKPOINT_SEC
    ext_max_hold_sec: int = EXT_MAX_HOLD_SEC
    extension_exit: ExtensionExit = "trail"
    trail_dist_atr_k: float = 1.0
    ema: EmaStackParams = EmaStackParams()


def _bucket_closes(bars: list[KBarRecord], tf_min: int, up_to_ts: int) -> list[float]:
    """Time-bucket 1m closes into ``tf_min`` bars through ``up_to_ts`` (inclusive)."""
    buckets: dict[dt.datetime, float] = {}
    for bar in bars:
        ts = int(bar.ts.timestamp())
        if ts > up_to_ts:
            break
        minute = bar.ts.replace(second=0, microsecond=0)
        bucket = minute - dt.timedelta(minutes=minute.minute % tf_min)
        buckets[bucket] = float(bar.Close)
    return [buckets[k] for k in sorted(buckets)]


def bull_stack(closes: list[float], *, fast: int, slow: int) -> bool | None:
    """Long bull alignment: close > EMA_fast > EMA_slow. None if insufficient bars."""
    need = slow + 2
    if len(closes) < need:
        return None
    ef = ema(closes, fast)
    es = ema(closes, slow)
    if ef is None or es is None:
        return None
    last = closes[-1]
    return last > ef > es


def ema_stack_broken(
    bars: list[KBarRecord],
    up_to_ts: int,
    *,
    tf_min: int,
    fast: int,
    slow: int,
) -> bool | None:
    """True when bull stack is broken on ``tf_min`` bars (None = not enough data)."""
    closes = _bucket_closes(bars, tf_min, up_to_ts)
    intact = bull_stack(closes, fast=fast, slow=slow)
    if intact is None:
        return None
    return not intact


def _extension_exit_signal(
    bars: list[KBarRecord],
    bar_close_ts: int,
    *,
    params: RouteAParams,
    armed: bool,
) -> str | None:
    """Return exit reason tag when EMA stack says exit; None to keep holding."""
    ep = params.ema
    b3 = ema_stack_broken(bars, bar_close_ts, tf_min=3, fast=ep.fast, slow=ep.slow)
    b5 = ema_stack_broken(bars, bar_close_ts, tf_min=5, fast=ep.fast, slow=ep.slow)
    mode = params.extension_exit
    if mode == "trail":
        return None
    if mode == "ema3":
        return "ema3_break" if b3 else None
    if mode == "ema5":
        return "ema5_break" if b5 else None
    if mode == "ema_either":
        if b3 or b5:
            return "ema_either_break"
        return None
    if mode == "ema_both":
        if b3 is False and b5 is False:
            return "ema_both_break"
        return None
    if mode == "trail_or_ema_either":
        if not armed:
            return None
        if b3 or b5:
            return "ema_trail_or_either"
        return None
    return None


def qualifies_for_extension(entry: ProbeEntry, ctx: DayWashContext, *, params: RouteAParams) -> bool:
    if ext_open_atr(ctx) <= params.ext_open_min:
        return False
    sealed = _simulate_exit(entry, ctx, "sealed")
    return (
        sealed["exit_reason"] == "horizon"
        and float(sealed["gross_pnl"]) > 0
        and int(sealed.get("hold_sec") or 0) >= params.checkpoint_sec - 30
    )


def simulate_route_a_exit(
    entry: ProbeEntry,
    ctx: DayWashContext,
    *,
    params: RouteAParams | None = None,
) -> dict[str, Any]:
    """Route A: sealed through checkpoint; qualifying days extend with ``extension_exit``."""
    params = params or RouteAParams()
    sealed = _simulate_exit(entry, ctx, "sealed")
    if not qualifies_for_extension(entry, ctx, params=params):
        return {**sealed, "route_a": "sealed", "extended": False}

    bars = ctx.session_bars or []
    atr = ctx.atr
    atr_eff = max(atr, 25.0) if atr > 0 else 25.0
    entry_px = entry.entry_price
    entry_ts = entry.entry_ts
    cp_ts = entry_ts + params.checkpoint_sec
    end_ts = entry_ts + params.ext_max_hold_sec

    if params.extension_exit == "trail":
        ext = simulate_atr_trail_skew_exit(
            direction="Long",
            entry_price=entry_px,
            entry_ts=entry_ts,
            atr=atr,
            ticks=ctx.ticks,
            hard_stop_atr_k=SEALED_K_SL,
            be_trigger_atr_k=None,
            trail_arm_atr_k=SEALED_TRAIL_ARM,
            trail_dist_atr_k=params.trail_dist_atr_k,
            hard_tp_atr_k=None,
            max_hold_sec=params.ext_max_hold_sec,
        )
        return {**ext, "route_a": "extended_trail", "extended": True}

  # Phase 1: sealed path through checkpoint (may arm BE/trail)
    peak = entry_px
    effective_stop = entry_px - SEALED_K_SL * atr_eff
    be_armed = False
    trail_armed = False
    mfe = 0.0
    mae = 0.0
    last_px = entry_px
    last_ts = entry_ts

    for ts, price, _, _ in ctx.ticks:
        if ts < entry_ts:
            continue
        if ts > cp_ts:
            break
        last_px, last_ts = price, ts
        fav = price - entry_px
        adv = entry_px - price
        mfe = max(mfe, fav)
        mae = max(mae, adv)
        peak = max(peak, price)
        if SEALED_BE is not None and fav >= SEALED_BE * atr_eff:
            be_armed = True
            effective_stop = max(effective_stop, entry_px)
        if fav >= SEALED_TRAIL_ARM * atr_eff:
            trail_armed = True
            effective_stop = max(effective_stop, peak - SEALED_TRAIL_DIST * atr_eff)
        if SEALED_HARD_TP is not None and fav >= SEALED_HARD_TP * atr_eff:
            return {
                "gross_pnl": round(SEALED_HARD_TP * atr_eff, 2),
                "exit_reason": "take_profit",
                "hold_sec": ts - entry_ts,
                "exit_price": round(entry_px + SEALED_HARD_TP * atr_eff, 2),
                "route_a": "sealed_pre_cp",
                "extended": False,
            }
        if price <= effective_stop:
            gross = price - entry_px
            reason = "trail_stop" if trail_armed else ("breakeven" if be_armed else "stop_loss")
            return {
                "gross_pnl": round(gross, 2),
                "exit_reason": reason,
                "hold_sec": ts - entry_ts,
                "exit_price": round(price, 2),
                "route_a": "sealed_pre_cp",
                "extended": False,
            }

    # Phase 2: extension leg — hard stop + optional trail + EMA stack exit on 1m closes
    ext_stop = entry_px - SEALED_K_SL * atr_eff
    ext_peak = max(peak, last_px)
    ext_trail_armed = False
    seen_bar_ts: set[int] = set()

    for ts, price, _, _ in ctx.ticks:
        if ts <= cp_ts:
            continue
        if ts > end_ts:
            break
        last_px, last_ts = price, ts
        fav = price - entry_px
        mfe = max(mfe, fav)
        mae = max(mae, entry_px - price)
        ext_peak = max(ext_peak, price)
        if fav >= SEALED_TRAIL_ARM * atr_eff:
            ext_trail_armed = True
            ext_stop = max(ext_stop, ext_peak - params.trail_dist_atr_k * atr_eff)
        if price <= ext_stop:
            gross = price - entry_px
            reason = "trail_stop" if ext_trail_armed else "stop_loss"
            return {
                "gross_pnl": round(gross, 2),
                "exit_reason": reason,
                "hold_sec": ts - entry_ts,
                "exit_price": round(price, 2),
                "route_a": "extended_stop",
                "extended": True,
            }
        bar_close_ts = ts - (ts % 60) + 60
        if bar_close_ts in seen_bar_ts:
            continue
        seen_bar_ts.add(bar_close_ts)
        if not bars:
            continue
        sig = _extension_exit_signal(
            bars,
            bar_close_ts,
            params=params,
            armed=ext_trail_armed or fav >= SEALED_BE * atr_eff,
        )
        if sig:
            gross = price - entry_px
            return {
                "gross_pnl": round(gross, 2),
                "exit_reason": sig,
                "hold_sec": ts - entry_ts,
                "exit_price": round(price, 2),
                "route_a": "extended_ema",
                "extended": True,
            }

    gross = last_px - entry_px
    return {
        "gross_pnl": round(gross, 2),
        "exit_reason": "horizon",
        "hold_sec": max(0, last_ts - entry_ts),
        "exit_price": round(last_px, 2),
        "route_a": "extended_horizon",
        "extended": True,
    }
