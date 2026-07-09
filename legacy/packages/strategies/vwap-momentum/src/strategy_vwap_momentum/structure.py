"""SMC structure filter (FT-002) — frozen algorithm v0.1.

Computes higher-timeframe market structure from 1m OHLCV bars for entry gating.
See docs/features/smc-structure-filter/SPEC.md §4.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass
from typing import Any, Protocol, Sequence

from strategy_vwap_momentum.trend import trend_allows_entry

STRUCTURE_ALGO_VERSION = 1
SESSION_OPEN = datetime.time(8, 45)


class OhlcBar(Protocol):
    ts: datetime.datetime
    Open: float
    High: float
    Low: float
    Close: float
    Volume: int


@dataclass(frozen=True)
class StructureParams:
    structure_filter_enabled: bool = False
    trend_filter_enabled: bool = False
    structure_timeframe_min: int = 5
    structure_swing_lookback: int = 2
    structure_min_strength: float = 0.0


@dataclass(frozen=True)
class StructureState:
    algo_version: int = STRUCTURE_ALGO_VERSION
    bias: str = "Neutral"
    strength: float = 0.0
    in_discount: bool = False
    in_premium: bool = False
    active_fvg_low: float | None = None
    active_fvg_high: float | None = None
    active_fvg_side: str | None = None
    last_bos: str | None = None
    last_bos_ts: datetime.datetime | None = None
    sweep_reclaim: bool = False
    sweep_side: str | None = None
    range_high: float = 0.0
    range_low: float = 0.0
    range_mid: float = 0.0
    as_of_bar_ts: datetime.datetime | None = None


@dataclass(frozen=True)
class Bar5m:
    ts: datetime.datetime
    Open: float
    High: float
    Low: float
    Close: float
    Volume: int


@dataclass
class _FvgZone:
    side: str  # "bullish" | "bearish"
    fvg_low: float
    fvg_high: float
    created_ts: datetime.datetime
    mitigated: bool = False


def validate_regime_config(params: StructureParams) -> None:
    if params.structure_filter_enabled and params.trend_filter_enabled:
        raise ValueError(
            "structure_filter_enabled and trend_filter_enabled are mutually exclusive"
        )


def trading_session_date(exchange_dt: datetime.datetime) -> datetime.date:
    if exchange_dt.time() < SESSION_OPEN:
        return exchange_dt.date() - datetime.timedelta(days=1)
    return exchange_dt.date()


def session_start(session_date: datetime.date) -> datetime.datetime:
    return datetime.datetime.combine(session_date, SESSION_OPEN)


def filter_closed_bars_1m(
    bars: Sequence[OhlcBar],
    exchange_dt: datetime.datetime,
) -> list[OhlcBar]:
    out: list[OhlcBar] = []
    for bar in bars:
        close_at = bar.ts + datetime.timedelta(minutes=1)
        if close_at <= exchange_dt:
            out.append(bar)
    out.sort(key=lambda b: b.ts)
    return out


def session_slice_bars_1m(
    bars: Sequence[OhlcBar],
    exchange_dt: datetime.datetime,
    *,
    used_long_lookback: bool,
) -> list[OhlcBar]:
    """Keep bars from current session (>=08:45 on session date) through exchange_dt."""
    sess_date = trading_session_date(exchange_dt)
    start = session_start(sess_date)
    # Always restrict structure to current session (§4.3). used_long_lookback is
    # reserved for StructureRefreshPort (Phase 3): when True, caller may pass
    # multi-day kbars; we still strip to session here.
    del used_long_lookback
    return [b for b in bars if b.ts >= start and b.ts <= exchange_dt]


def _bucket_start(ts: datetime.datetime, timeframe_min: int) -> datetime.datetime:
    minute = (ts.minute // timeframe_min) * timeframe_min
    return ts.replace(minute=minute, second=0, microsecond=0)


def resample_time_buckets(
    bars_1m: Sequence[OhlcBar],
    timeframe_min: int,
    exchange_dt: datetime.datetime,
) -> list[Bar5m]:
    if timeframe_min <= 0 or not bars_1m:
        return []

    buckets: dict[datetime.datetime, list[OhlcBar]] = {}
    for bar in bars_1m:
        key = _bucket_start(bar.ts, timeframe_min)
        buckets.setdefault(key, []).append(bar)

    out: list[Bar5m] = []
    for key in sorted(buckets.keys()):
        bucket_close = key + datetime.timedelta(minutes=timeframe_min)
        if bucket_close > exchange_dt:
            continue
        chunk = sorted(buckets[key], key=lambda b: b.ts)
        out.append(
            Bar5m(
                ts=key,
                Open=float(chunk[0].Open),
                High=max(float(b.High) for b in chunk),
                Low=min(float(b.Low) for b in chunk),
                Close=float(chunk[-1].Close),
                Volume=sum(int(b.Volume) for b in chunk),
            )
        )
    return out


def _compute_session_range(bars_1m: Sequence[OhlcBar]) -> tuple[float, float, float]:
    if not bars_1m:
        return 0.0, 0.0, 0.0
    hi = max(float(b.High) for b in bars_1m)
    lo = min(float(b.Low) for b in bars_1m)
    return hi, lo, (hi + lo) / 2.0


def _is_swing_high_candidate(bars: Sequence[Bar5m], i: int, lookback: int) -> bool:
    if i < lookback or i + lookback >= len(bars):
        return False
    pivot = bars[i].High
    for k in range(1, lookback + 1):
        if bars[i - k].High >= pivot or bars[i + k].High >= pivot:
            return False
    return True


def _is_swing_low_candidate(bars: Sequence[Bar5m], i: int, lookback: int) -> bool:
    if i < lookback or i + lookback >= len(bars):
        return False
    pivot = bars[i].Low
    for k in range(1, lookback + 1):
        if bars[i - k].Low <= pivot or bars[i + k].Low <= pivot:
            return False
    return True


def _swing_holds_high(bars: Sequence[Bar5m], i: int, pivot_high: float, lag: int) -> bool:
    for k in range(1, lag + 1):
        if bars[i + k].High > pivot_high:
            return False
    return True


def _swing_holds_low(bars: Sequence[Bar5m], i: int, pivot_low: float, lag: int) -> bool:
    for k in range(1, lag + 1):
        if bars[i + k].Low < pivot_low:
            return False
    return True


def _detect_fvgs(bars: Sequence[Bar5m]) -> list[_FvgZone]:
    zones: list[_FvgZone] = []
    for i in range(2, len(bars)):
        b0, _b1, b2 = bars[i - 2], bars[i - 1], bars[i]
        if b0.High < b2.Low:
            zones.append(
                _FvgZone(
                    side="bullish",
                    fvg_low=float(b0.High),
                    fvg_high=float(b2.Low),
                    created_ts=b2.ts,
                )
            )
        elif b0.Low > b2.High:
            zones.append(
                _FvgZone(
                    side="bearish",
                    fvg_low=float(b2.High),
                    fvg_high=float(b0.Low),
                    created_ts=b2.ts,
                )
            )
    return zones


def _apply_fvg_mitigation(zones: list[_FvgZone], bars: Sequence[Bar5m]) -> None:
    for zone in zones:
        if zone.mitigated:
            continue
        for bar in bars:
            if bar.ts <= zone.created_ts:
                continue
            if bar.Low <= zone.fvg_low and bar.High >= zone.fvg_high:
                zone.mitigated = True
                break


def _select_active_fvg(
    zones: list[_FvgZone],
    bias: str,
) -> _FvgZone | None:
    if bias == "Neutral":
        return None
    side = "bullish" if bias == "Long" else "bearish"
    active = [z for z in zones if not z.mitigated and z.side == side]
    if not active:
        return None
    return max(active, key=lambda z: z.created_ts)


def _analyze_bars_5m(
    bars: Sequence[Bar5m],
    lookback: int,
) -> tuple[
    str | None,
    datetime.datetime | None,
    bool,
    str | None,
    float | None,
    float | None,
]:
    """Return last_bos, last_bos_ts, sweep_reclaim, sweep_side, last_sh, last_sl."""
    last_bos: str | None = None
    last_bos_ts: datetime.datetime | None = None
    sweep_reclaim = False
    sweep_side: str | None = None

    last_confirmed_high: float | None = None
    last_confirmed_low: float | None = None
    last_confirmed_high_ts: datetime.datetime | None = None
    last_confirmed_low_ts: datetime.datetime | None = None

    lag = lookback
    n = len(bars)

    for j in range(n):
        for i in range(max(0, j - lag), j):
            confirm_idx = i + lag
            if confirm_idx != j:
                continue
            if _is_swing_high_candidate(bars, i, lookback):
                if _swing_holds_high(bars, i, bars[i].High, lag):
                    last_confirmed_high = bars[i].High
                    last_confirmed_high_ts = bars[j].ts
            if _is_swing_low_candidate(bars, i, lookback):
                if _swing_holds_low(bars, i, bars[i].Low, lag):
                    last_confirmed_low = bars[i].Low
                    last_confirmed_low_ts = bars[j].ts

        bar = bars[j]
        if last_confirmed_high is not None and last_confirmed_high_ts is not None:
            if (
                bar.ts > last_confirmed_high_ts
                and bar.Close > last_confirmed_high
            ):
                last_bos = "bullish"
                last_bos_ts = bar.ts
            if bar.High > last_confirmed_high and bar.Close < last_confirmed_high:
                sweep_reclaim = True
                sweep_side = "bearish"

        if last_confirmed_low is not None and last_confirmed_low_ts is not None:
            if bar.ts > last_confirmed_low_ts and bar.Close < last_confirmed_low:
                last_bos = "bearish"
                last_bos_ts = bar.ts
            if bar.Low < last_confirmed_low and bar.Close > last_confirmed_low:
                sweep_reclaim = True
                sweep_side = "bullish"

    return (
        last_bos,
        last_bos_ts,
        sweep_reclaim,
        sweep_side,
        last_confirmed_high,
        last_confirmed_low,
    )


def compute_structure(
    bars_1m: Sequence[OhlcBar],
    *,
    atr: float,
    params: StructureParams | None = None,
    exchange_dt: datetime.datetime | None = None,
    as_of_ts: int | None = None,
    used_long_lookback: bool = False,
) -> StructureState:
    """Compute SMC structure state (algo v1). Pure function — no I/O."""
    p = params or StructureParams()
    if exchange_dt is None:
        if as_of_ts is not None:
            exchange_dt = datetime.datetime.fromtimestamp(as_of_ts)
        elif bars_1m:
            exchange_dt = max(b.ts for b in bars_1m) + datetime.timedelta(minutes=1)
        else:
            return StructureState()

    closed = filter_closed_bars_1m(bars_1m, exchange_dt)
    session_bars = session_slice_bars_1m(
        closed, exchange_dt, used_long_lookback=used_long_lookback
    )

    range_high, range_low, range_mid = _compute_session_range(session_bars)
    bars_5m = resample_time_buckets(
        session_bars, p.structure_timeframe_min, exchange_dt
    )
    if not bars_5m:
        return StructureState(
            range_high=range_high,
            range_low=range_low,
            range_mid=range_mid,
        )

    lookback = max(1, int(p.structure_swing_lookback))
    last_bos, last_bos_ts, sweep_reclaim, sweep_side, _, _ = _analyze_bars_5m(
        bars_5m, lookback
    )

    zones = _detect_fvgs(bars_5m)
    _apply_fvg_mitigation(zones, bars_5m)

    px = float(bars_5m[-1].Close)
    in_discount = False
    in_premium = False
    if session_bars:
        if px < range_mid:
            in_discount = True
        elif px > range_mid:
            in_premium = True

    if last_bos == "bullish":
        candidate_bias = "Long"
    elif last_bos == "bearish":
        candidate_bias = "Short"
    else:
        candidate_bias = "Neutral"

    strength = 0.0
    bias = candidate_bias
    if candidate_bias != "Neutral" and atr > 1e-6:
        eff = abs(px - range_mid) / atr
        # §4.10: min_strength=0 requires eff > 0 (zero displacement → Neutral).
        if p.structure_min_strength == 0.0:
            if eff <= 0.0:
                bias = "Neutral"
                strength = 0.0
            else:
                strength = eff
        elif eff < p.structure_min_strength:
            bias = "Neutral"
            strength = 0.0
        else:
            strength = eff

    active = _select_active_fvg(zones, bias)

    return StructureState(
        algo_version=STRUCTURE_ALGO_VERSION,
        bias=bias,
        strength=strength,
        in_discount=in_discount,
        in_premium=in_premium,
        active_fvg_low=None if active is None else active.fvg_low,
        active_fvg_high=None if active is None else active.fvg_high,
        active_fvg_side=None if active is None else active.side,
        last_bos=last_bos,
        last_bos_ts=last_bos_ts,
        sweep_reclaim=sweep_reclaim,
        sweep_side=sweep_side,
        range_high=range_high,
        range_low=range_low,
        range_mid=range_mid,
        as_of_bar_ts=bars_5m[-1].ts,
    )


def structure_allows_entry(
    *,
    enabled: bool,
    state: StructureState,
    momentum_dir: str,
    price: float,
) -> bool:
    if not enabled:
        return True
    if state.bias == "Neutral":
        return True
    if state.bias != momentum_dir:
        return False
    in_fvg = False
    if (
        state.active_fvg_low is not None
        and state.active_fvg_high is not None
        and state.active_fvg_low <= price <= state.active_fvg_high
    ):
        in_fvg = True
    if momentum_dir == "Long":
        return state.in_discount or in_fvg
    if momentum_dir == "Short":
        return state.in_premium or in_fvg
    return True


def regime_allows_entry(
    *,
    params: StructureParams,
    trend_dir: str,
    state: StructureState,
    momentum_dir: str,
    price: float,
) -> tuple[bool, str]:
    """Unified battlefield gate. Returns (allowed, veto_reason)."""
    validate_regime_config(params)
    if params.structure_filter_enabled:
        if structure_allows_entry(
            enabled=True,
            state=state,
            momentum_dir=momentum_dir,
            price=price,
        ):
            return True, ""
        return False, "structure_veto"
    if params.trend_filter_enabled:
        if trend_allows_entry(
            enabled=True,
            trend_dir=trend_dir,
            momentum_dir=momentum_dir,
        ):
            return True, ""
        return False, "trend_veto"
    return True, ""


def structure_state_from_market_fields(
    *,
    bias: str,
    strength: float,
    in_discount: bool,
    in_premium: bool,
    fvg_low: float | None,
    fvg_high: float | None,
    sweep_reclaim: bool = False,
) -> StructureState:
    """Rebuild StructureState from MarketSnapshot fields (live refresh cache)."""
    return StructureState(
        bias=bias,
        strength=strength,
        in_discount=in_discount,
        in_premium=in_premium,
        active_fvg_low=fvg_low,
        active_fvg_high=fvg_high,
        sweep_reclaim=sweep_reclaim,
    )


def structure_params_from_strategy(params: Any) -> StructureParams:
    """Build StructureParams from StrategyParams-like object (optional attrs)."""
    return StructureParams(
        structure_filter_enabled=bool(
            getattr(params, "structure_filter_enabled", False)
        ),
        trend_filter_enabled=bool(getattr(params, "trend_filter_enabled", False)),
        structure_timeframe_min=int(
            getattr(params, "structure_timeframe_min", 5)
        ),
        structure_swing_lookback=int(
            getattr(params, "structure_swing_lookback", 2)
        ),
        structure_min_strength=float(
            getattr(params, "structure_min_strength", 0.0)
        ),
    )