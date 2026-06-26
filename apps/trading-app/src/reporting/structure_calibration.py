"""P6-SMC-CAL: Offline harness for structure vs trend vs no-filter counterfactuals.

Pure functions with synthetic A-class support. B-class replays UAT ``momentum_armed``
events against tick_cache kbars (recompute ``compute_structure`` as-of) and tick_cache
forward PnL under three mutually-exclusive regime scenarios.

Core metrics (mirror P6-1-CAL):
- veto_rate: fraction of armed candidates vetoed by the active filter.
- delta_expectancy: E[forward_pnl | allowed] - E[forward_pnl_if_entered | vetoed].
  Friction-adjusted variants subtract round-trip friction per hypothetical entry.

SYNTHETIC GUARD: toy numbers are for harness correctness only. Real Go/No-Go on
``structure_filter_enabled`` requires ≥5 UAT days + B-class replay + CAL-8 sign-off.

See:
- docs/features/smc-structure-filter/SPEC.md §8.1
- docs/features/smc-structure-filter/PLAN.md Phase 2
- reporting.trend_calibration (pattern reference)
"""

from __future__ import annotations

import csv
import datetime
import json
import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

from reporting.forward_pnl import ForwardPnlPolicy, load_tick_series, make_replay_forward_pnl, policy_summary
from reporting.performance_metrics import FrictionSettings, friction_per_round_trip
from reporting.uat_report import parse_decision_audits, parse_log_audits_and_fills, read_log_lines
from storage.kbar_loader import KBarRecord, iter_kbars_in_range
from storage.legacy_cache_migrate import ensure_legacy_kbars_migrated
from storage.tick_loader import DEFAULT_CACHE_DIR
from strategy_vwap_momentum.structure import (
    STRUCTURE_ALGO_VERSION,
    StructureParams,
    StructureState,
    compute_structure,
    filter_closed_bars_1m,
    regime_allows_entry,
    session_slice_bars_1m,
)
from strategy_vwap_momentum.trend import compute_trend
from trading_engine.calendar.taifex import select_recent_trading_days_closes
from trading_engine.core.audit.decision_audit import DecisionAudit
from trading_engine.core.audit.signal_audit import SignalAudit


CONVERSION_WINDOW_SEC = 30
COUNTERFACTUAL_SCENARIOS = ("no_filter", "structure_only", "trend_only")
DEFAULT_STRUCTURE_MIN_STRENGTH_GRID = [0.0, 0.3, 0.5, 0.8, 1.0, 1.5]

_STRUCTURE_EVENT_FIELDS = [
    "episode_id",
    "ts",
    "direction",
    "trigger_price",
    "atr",
    "structure_algo_version",
    "structure_bias",
    "structure_strength",
    "structure_in_discount",
    "structure_in_premium",
    "structure_fvg_low",
    "structure_fvg_high",
    "structure_fvg_side",
    "structure_last_bos",
    "structure_last_bos_ts",
    "structure_sweep_reclaim",
    "structure_sweep_side",
    "structure_range_high",
    "structure_range_low",
    "structure_range_mid",
    "structure_as_of_bar_ts",
    "trend_dir",
    "trend_strength",
]

_ARMED_JOIN_FIELDS = _STRUCTURE_EVENT_FIELDS + [
    "converted_30s",
    "entry_ts",
    "scenario",
    "counterfactual_allowed",
    "veto_reason",
    "forward_pnl_gross",
    "forward_pnl_net",
]


@dataclass(frozen=True)
class ArmedCandidate:
    episode_id: str
    ts: int
    direction: str
    price: float
    atr: float
    vwap: float = 0.0


@dataclass(frozen=True)
class TrendHarnessConfig:
    mode: str = "ema"
    timeframe_min: int = 5
    ema_period: int = 20
    slope_min: float = 0.0
    min_strength: float = 0.0


def parse_momentum_armed(decisions: Iterable[DecisionAudit]) -> list[ArmedCandidate]:
    """Extract armed candidates from parsed DECISION_AUDIT rows."""
    out: list[ArmedCandidate] = []
    for d in decisions:
        if d.event_type != "momentum_armed":
            continue
        price = float(d.trigger_price or d.price or 0.0)
        out.append(
            ArmedCandidate(
                episode_id=str(d.episode_id or ""),
                ts=int(d.ts),
                direction=str(d.direction or "Long"),
                price=price,
                atr=float(d.atr or 0.0),
                vwap=float(d.vwap or 0.0),
            )
        )
    out.sort(key=lambda c: c.ts)
    return out


def structure_state_to_row(
    candidate: ArmedCandidate,
    state: StructureState,
    *,
    trend_dir: str = "",
    trend_strength: float = 0.0,
) -> dict[str, Any]:
    bos_ts = ""
    if state.last_bos_ts is not None:
        bos_ts = state.last_bos_ts.isoformat()
    as_of_bar = ""
    if state.as_of_bar_ts is not None:
        as_of_bar = state.as_of_bar_ts.isoformat()
    return {
        "episode_id": candidate.episode_id,
        "ts": candidate.ts,
        "direction": candidate.direction,
        "trigger_price": candidate.price,
        "atr": candidate.atr,
        "structure_algo_version": state.algo_version,
        "structure_bias": state.bias,
        "structure_strength": state.strength,
        "structure_in_discount": state.in_discount,
        "structure_in_premium": state.in_premium,
        "structure_fvg_low": state.active_fvg_low,
        "structure_fvg_high": state.active_fvg_high,
        "structure_fvg_side": state.active_fvg_side,
        "structure_last_bos": state.last_bos,
        "structure_last_bos_ts": bos_ts,
        "structure_sweep_reclaim": state.sweep_reclaim,
        "structure_sweep_side": state.sweep_side,
        "structure_range_high": state.range_high,
        "structure_range_low": state.range_low,
        "structure_range_mid": state.range_mid,
        "structure_as_of_bar_ts": as_of_bar,
        "trend_dir": trend_dir,
        "trend_strength": trend_strength,
    }


def compute_structure_snapshot(
    bars_1m: Sequence[KBarRecord],
    *,
    atr: float,
    as_of_ts: int,
    params: StructureParams | None = None,
) -> StructureState:
    """Recompute structure at decision time (no live cache)."""
    return compute_structure(
        bars_1m,
        atr=atr,
        params=params,
        as_of_ts=as_of_ts,
        used_long_lookback=False,
    )


def _closes_for_trend(
    bars_1m: Sequence[KBarRecord],
    as_of_ts: int,
) -> list[float]:
    """Closes for trend counterfactual — mirrors live ``select_recent_trading_days_closes``."""
    exchange_dt = datetime.datetime.fromtimestamp(as_of_ts)
    closed = filter_closed_bars_1m(bars_1m, exchange_dt)
    recent = select_recent_trading_days_closes(closed, exchange_dt)
    if recent:
        return recent
    session_bars = session_slice_bars_1m(
        closed, exchange_dt, used_long_lookback=False
    )
    return [float(b.Close) for b in session_bars]


def compute_trend_snapshot(
    bars_1m: Sequence[KBarRecord],
    *,
    atr: float,
    as_of_ts: int,
    trend_cfg: TrendHarnessConfig | None = None,
) -> tuple[str, float]:
    cfg = trend_cfg or TrendHarnessConfig()
    closes = _closes_for_trend(bars_1m, as_of_ts)
    return compute_trend(
        closes,
        mode=cfg.mode,
        timeframe_min=cfg.timeframe_min,
        ema_period=cfg.ema_period,
        slope_min=cfg.slope_min,
        min_strength=cfg.min_strength,
        atr=atr,
    )


def counterfactual_regime_allows(
    scenario: str,
    *,
    structure_state: StructureState,
    trend_dir: str,
    momentum_dir: str,
    price: float,
    structure_params: StructureParams,
) -> tuple[bool, str]:
    """Apply one of three counterfactual filter configs (mutually exclusive)."""
    if scenario == "no_filter":
        return True, ""
    if scenario == "structure_only":
        sp = StructureParams(
            structure_filter_enabled=True,
            trend_filter_enabled=False,
            structure_timeframe_min=structure_params.structure_timeframe_min,
            structure_swing_lookback=structure_params.structure_swing_lookback,
            structure_min_strength=structure_params.structure_min_strength,
        )
        return regime_allows_entry(
            params=sp,
            trend_dir=trend_dir,
            state=structure_state,
            momentum_dir=momentum_dir,
            price=price,
        )
    if scenario == "trend_only":
        tp = StructureParams(
            structure_filter_enabled=False,
            trend_filter_enabled=True,
        )
        return regime_allows_entry(
            params=tp,
            trend_dir=trend_dir,
            state=structure_state,
            momentum_dir=momentum_dir,
            price=price,
        )
    raise ValueError(f"unknown counterfactual scenario: {scenario}")


def entry_ts_within_window(
    armed_ts: int,
    episode_id: str,
    signals: Iterable[SignalAudit],
    *,
    window_sec: int = CONVERSION_WINDOW_SEC,
) -> int | None:
    """Return entry signal ts if episode converted within window, else None."""
    deadline = armed_ts + window_sec
    best: int | None = None
    for sig in signals:
        if sig.intent != "entry":
            continue
        if sig.episode_id != episode_id:
            continue
        ts = int(sig.ts)
        if armed_ts <= ts <= deadline:
            if best is None or ts < best:
                best = ts
    return best


def _invoke_forward_pnl(
    fwd: Callable[..., float],
    candidate: ArmedCandidate,
) -> float:
    try:
        return float(fwd(candidate.price, int(candidate.ts), candidate.direction))
    except TypeError:
        return float(fwd(candidate.price, int(candidate.ts)))


def apply_friction(gross: float, friction_per_trade: float) -> float:
    return round(gross - friction_per_trade, 4)


def compute_regime_veto_calibration(
    candidates: Sequence[ArmedCandidate],
    *,
    scenario: str,
    bars_1m: Sequence[KBarRecord],
    structure_params: StructureParams | None = None,
    trend_cfg: TrendHarnessConfig | None = None,
    get_forward_pnl: Callable[..., float] | None = None,
    forward_policy: ForwardPnlPolicy | None = None,
    friction: FrictionSettings | None = None,
    b_class: bool = False,
) -> dict[str, Any]:
    """Counterfactual veto calibration for one scenario on armed candidates."""
    sp = structure_params or StructureParams()
    tc = trend_cfg or TrendHarnessConfig()
    friction_per_trade = friction_per_round_trip(friction or FrictionSettings())

    veto_rows: list[ArmedCandidate] = []
    allowed_rows: list[ArmedCandidate] = []

    for cand in candidates:
        state = compute_structure_snapshot(
            bars_1m, atr=cand.atr, as_of_ts=cand.ts, params=sp
        )
        trend_dir, _ = compute_trend_snapshot(
            bars_1m, atr=cand.atr, as_of_ts=cand.ts, trend_cfg=tc
        )
        allowed, _reason = counterfactual_regime_allows(
            scenario,
            structure_state=state,
            trend_dir=trend_dir,
            momentum_dir=cand.direction,
            price=cand.price,
            structure_params=sp,
        )
        if allowed:
            allowed_rows.append(cand)
        else:
            veto_rows.append(cand)

    def _default_fwd(_price: float, _ts: int) -> float:
        return 0.0

    fwd = get_forward_pnl or _default_fwd
    using_custom_fwd = get_forward_pnl is not None

    veto_gross: list[float] = []
    veto_net: list[float] = []
    for rec in veto_rows:
        g = _invoke_forward_pnl(fwd, rec)
        veto_gross.append(g)
        veto_net.append(apply_friction(g, friction_per_trade))

    allowed_gross: list[float] = []
    allowed_net: list[float] = []
    for rec in allowed_rows:
        g = _invoke_forward_pnl(fwd, rec)
        allowed_gross.append(g)
        allowed_net.append(apply_friction(g, friction_per_trade))

    n_veto = len(veto_rows)
    n_allowed = len(allowed_rows)
    total = n_veto + n_allowed
    veto_rate = (n_veto / total) if total else 0.0

    mean_veto_gross = statistics.mean(veto_gross) if veto_gross else 0.0
    mean_allowed_gross = statistics.mean(allowed_gross) if allowed_gross else 0.0
    mean_veto_net = statistics.mean(veto_net) if veto_net else 0.0
    mean_allowed_net = statistics.mean(allowed_net) if allowed_net else 0.0

    delta_gross = mean_allowed_gross - mean_veto_gross
    delta_net = mean_allowed_net - mean_veto_net

    if b_class and forward_policy is not None:
        notes = (
            f"B-class replay forward policy: {policy_summary(forward_policy)}. "
            f"Friction per trade: {friction_per_trade} pts. "
            "Use for Go/No-Go only with ≥5 UAT days and human sign-off (CAL-8). "
            f"structure_min_strength=0.0 is strictest (most vetoes)."
        )
    elif using_custom_fwd:
        notes = (
            "Replay forward PnL supplied. Document policy per run; "
            "multi-day stability still required before opening structure_filter_enabled."
        )
    else:
        notes = (
            "SYNTHETIC GUARD: toy numbers only. Real delta/veto_rate for Go/No-Go "
            "require UAT replay + documented forward policy (P6-SMC-CAL)."
        )

    return {
        "scenario": scenario,
        "veto_rate": round(veto_rate, 4),
        "n_veto": n_veto,
        "n_allowed": n_allowed,
        "mean_forward_if_vetoed": round(mean_veto_gross, 4),
        "mean_forward_allowed": round(mean_allowed_gross, 4),
        "delta_expectancy": round(delta_gross, 4),
        "mean_forward_if_vetoed_net": round(mean_veto_net, 4),
        "mean_forward_allowed_net": round(mean_allowed_net, 4),
        "delta_expectancy_net": round(delta_net, 4),
        "friction_per_trade": friction_per_trade,
        "structure_min_strength": sp.structure_min_strength,
        "trend_min_strength": tc.min_strength,
        "structure_algo_version": STRUCTURE_ALGO_VERSION,
        "notes": notes,
    }


def run_counterfactual_comparison(
    candidates: Sequence[ArmedCandidate],
    *,
    bars_1m: Sequence[KBarRecord],
    structure_params: StructureParams | None = None,
    trend_cfg: TrendHarnessConfig | None = None,
    get_forward_pnl: Callable[..., float] | None = None,
    forward_policy: ForwardPnlPolicy | None = None,
    friction: FrictionSettings | None = None,
    b_class: bool = False,
) -> dict[str, Any]:
    """Run all three counterfactual scenarios and compute relative deltas."""
    results: dict[str, Any] = {}
    for scenario in COUNTERFACTUAL_SCENARIOS:
        results[scenario] = compute_regime_veto_calibration(
            candidates,
            scenario=scenario,
            bars_1m=bars_1m,
            structure_params=structure_params,
            trend_cfg=trend_cfg,
            get_forward_pnl=get_forward_pnl,
            forward_policy=forward_policy,
            friction=friction,
            b_class=b_class,
        )

    struct_delta = results["structure_only"]["delta_expectancy_net"]
    trend_delta = results["trend_only"]["delta_expectancy_net"]
    none_delta = results["no_filter"]["delta_expectancy_net"]
    results["comparison"] = {
        "delta_structure_vs_trend": round(struct_delta - trend_delta, 4),
        "delta_structure_vs_no_filter": round(struct_delta - none_delta, 4),
        "structure_veto_rate": results["structure_only"]["veto_rate"],
        "trend_veto_rate": results["trend_only"]["veto_rate"],
        "phase3_gate": (struct_delta > 0 and (struct_delta - trend_delta) > 0),
        "phase3_gate_note": (
            "Phase 3 hint: structure_only delta_expectancy_net > 0 AND incremental vs trend. "
            "Human CAL-8 + ≥5 UAT days still required."
        ),
    }
    return results


def build_structure_event_rows(
    candidates: Sequence[ArmedCandidate],
    bars_1m: Sequence[KBarRecord],
    *,
    structure_params: StructureParams | None = None,
    trend_cfg: TrendHarnessConfig | None = None,
) -> list[dict[str, Any]]:
    """Structure snapshots at each armed decision point."""
    sp = structure_params or StructureParams()
    tc = trend_cfg or TrendHarnessConfig()
    rows: list[dict[str, Any]] = []
    for cand in candidates:
        state = compute_structure_snapshot(
            bars_1m, atr=cand.atr, as_of_ts=cand.ts, params=sp
        )
        trend_dir, trend_strength = compute_trend_snapshot(
            bars_1m, atr=cand.atr, as_of_ts=cand.ts, trend_cfg=tc
        )
        rows.append(
            structure_state_to_row(
                cand,
                state,
                trend_dir=trend_dir,
                trend_strength=trend_strength,
            )
        )
    return rows


def build_armed_join_rows(
    candidates: Sequence[ArmedCandidate],
    bars_1m: Sequence[KBarRecord],
    signals: Iterable[SignalAudit],
    *,
    scenario: str = "structure_only",
    structure_params: StructureParams | None = None,
    trend_cfg: TrendHarnessConfig | None = None,
    get_forward_pnl: Callable[..., float] | None = None,
    friction: FrictionSettings | None = None,
) -> list[dict[str, Any]]:
    """Armed events joined with structure + 30s conversion + counterfactual outcome."""
    sp = structure_params or StructureParams()
    tc = trend_cfg or TrendHarnessConfig()
    friction_per_trade = friction_per_round_trip(friction or FrictionSettings())
    rows: list[dict[str, Any]] = []

    def _default_fwd(_price: float, _ts: int) -> float:
        return 0.0

    fwd = get_forward_pnl or _default_fwd

    for cand in candidates:
        state = compute_structure_snapshot(
            bars_1m, atr=cand.atr, as_of_ts=cand.ts, params=sp
        )
        trend_dir, trend_strength = compute_trend_snapshot(
            bars_1m, atr=cand.atr, as_of_ts=cand.ts, trend_cfg=tc
        )
        allowed, veto_reason = counterfactual_regime_allows(
            scenario,
            structure_state=state,
            trend_dir=trend_dir,
            momentum_dir=cand.direction,
            price=cand.price,
            structure_params=sp,
        )
        entry_ts = entry_ts_within_window(cand.ts, cand.episode_id, signals)
        gross = _invoke_forward_pnl(fwd, cand)
        row = structure_state_to_row(
            cand,
            state,
            trend_dir=trend_dir,
            trend_strength=trend_strength,
        )
        row.update(
            {
                "converted_30s": entry_ts is not None,
                "entry_ts": entry_ts or "",
                "scenario": scenario,
                "counterfactual_allowed": allowed,
                "veto_reason": veto_reason,
                "forward_pnl_gross": round(gross, 4),
                "forward_pnl_net": apply_friction(gross, friction_per_trade),
            }
        )
        rows.append(row)
    return rows


def write_csv(path: Path, fieldnames: Sequence[str], rows: Sequence[Mapping[str, Any]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(fieldnames), extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})
    return len(rows)


def run_b_class_structure_calibration(
    *,
    log_lines: list[str] | None = None,
    log_paths: list[Path] | None = None,
    code: str,
    dates: list[datetime.date],
    cache_dir: Path | str = DEFAULT_CACHE_DIR,
    forward_policy: ForwardPnlPolicy | None = None,
    structure_params: StructureParams | None = None,
    trend_cfg: TrendHarnessConfig | None = None,
    friction: FrictionSettings | None = None,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """B-class: parse UAT log + kbar recompute + tick replay → counterfactual metrics."""
    if log_lines is None:
        if not log_paths:
            raise ValueError("run_b_class_structure_calibration requires log_lines or log_paths")
        log_lines = read_log_lines([Path(p) for p in log_paths])

    decisions = parse_decision_audits(log_lines)
    signals, _fills = parse_log_audits_and_fills(log_lines)
    candidates = parse_momentum_armed(decisions)

    if not dates:
        raise ValueError("at least one date required")

    ensure_legacy_kbars_migrated(Path(cache_dir))

    start = min(dates)
    end = max(dates)
    bars_1m = iter_kbars_in_range(code, start, end, cache_dir=Path(cache_dir))

    pol = forward_policy or ForwardPnlPolicy()
    series = load_tick_series(code, dates, cache_dir=Path(cache_dir))

    base: dict[str, Any] = {
        "code": code,
        "dates": [d.isoformat() for d in dates],
        "cache_dir": str(cache_dir),
        "forward_policy": policy_summary(pol),
        "n_armed": len(candidates),
        "kbar_count": len(bars_1m),
        "structure_algo_version": STRUCTURE_ALGO_VERSION,
    }

    if not candidates:
        base["status"] = "no_armed"
        base["notes"] = "No momentum_armed events in log."
        return base

    if not bars_1m:
        base["status"] = "no_kbars"
        base["notes"] = "B-class blocked: no kbars in tick_cache for requested dates."
        base["counterfactuals"] = None
        return base

    event_rows = build_structure_event_rows(
        candidates,
        bars_1m,
        structure_params=structure_params,
        trend_cfg=trend_cfg,
    )

    get_forward_pnl = None
    tick_count = 0
    if series.timestamps:
        get_forward_pnl = make_replay_forward_pnl(series, pol)
        tick_count = len(series)
    else:
        base["tick_warning"] = "tick_cache empty; forward PnL metrics will be zero."

    counterfactuals = run_counterfactual_comparison(
        candidates,
        bars_1m=bars_1m,
        structure_params=structure_params,
        trend_cfg=trend_cfg,
        get_forward_pnl=get_forward_pnl,
        forward_policy=pol,
        friction=friction,
        b_class=bool(series.timestamps),
    )

    join_rows: dict[str, list[dict[str, Any]]] = {}
    for scenario in COUNTERFACTUAL_SCENARIOS:
        join_rows[scenario] = build_armed_join_rows(
            candidates,
            bars_1m,
            signals,
            scenario=scenario,
            structure_params=structure_params,
            trend_cfg=trend_cfg,
            get_forward_pnl=get_forward_pnl,
            friction=friction,
        )

    if output_dir is not None:
        out = Path(output_dir)
        write_csv(out / "structure_events.csv", _STRUCTURE_EVENT_FIELDS, event_rows)
        for scenario, rows in join_rows.items():
            write_csv(
                out / f"structure_armed_join_{scenario}.csv",
                _ARMED_JOIN_FIELDS,
                rows,
            )
        # Primary join file (structure_only per PLAN)
        write_csv(out / "structure_armed_join.csv", _ARMED_JOIN_FIELDS, join_rows["structure_only"])

    base["status"] = "ok" if series.timestamps else "ok_no_ticks"
    base["tick_count"] = tick_count
    base["counterfactuals"] = counterfactuals
    base["structure_events_count"] = len(event_rows)
    base["conversion_30s_rate"] = round(
        sum(1 for r in join_rows["structure_only"] if r.get("converted_30s")) / len(candidates),
        4,
    ) if candidates else 0.0
    return base


def armed_candidates_from_decision_dicts(
    decisions: Iterable[Mapping[str, Any]],
) -> list[ArmedCandidate]:
    """Build armed candidates from parsed DECISION_AUDIT JSON dicts."""
    audits = [
        DecisionAudit(
            event_type=str(d.get("event_type", "")),
            ts=int(d.get("ts", 0)),
            episode_id=str(d.get("episode_id", "")),
            direction=str(d.get("direction", "Long")),
            trigger_price=float(d.get("trigger_price", d.get("price", 0.0))),
            atr=float(d.get("atr", 0.0)),
            vwap=float(d.get("vwap", 0.0)),
        )
        for d in decisions
        if d.get("event_type") == "momentum_armed"
    ]
    return parse_momentum_armed(audits)


def run_structure_sensitivity_sweep(
    *,
    log_lines: list[str] | None = None,
    log_paths: list[Path] | None = None,
    code: str,
    dates: list[datetime.date],
    cache_dir: Path | str = DEFAULT_CACHE_DIR,
    forward_policy: ForwardPnlPolicy | None = None,
    friction: FrictionSettings | None = None,
    min_strength_grid: list[float] | None = None,
    output_path: Path | None = None,
) -> list[dict[str, Any]]:
    """CAL grid: walk structure_min_strength on fixed log + kbar + tick replay."""
    grid = min_strength_grid or DEFAULT_STRUCTURE_MIN_STRENGTH_GRID
    rows: list[dict[str, Any]] = []
    for ms in grid:
        sp = StructureParams(structure_min_strength=float(ms))
        result = run_b_class_structure_calibration(
            log_lines=log_lines,
            log_paths=log_paths,
            code=code,
            dates=dates,
            cache_dir=cache_dir,
            forward_policy=forward_policy,
            structure_params=sp,
            friction=friction,
        )
        cf = result.get("counterfactuals") or {}
        struct_only = cf.get("structure_only") or {}
        comp = cf.get("comparison") or {}
        rows.append(
            {
                "params": {"structure_min_strength": ms},
                "status": result.get("status"),
                "veto_metrics": struct_only,
                "comparison": comp,
                "delta_structure_vs_trend": comp.get("delta_structure_vs_trend"),
            }
        )

    if output_path is not None:
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w", encoding="utf-8") as f:
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")

    return rows


def make_synthetic_armed_scenario(
    prices: Sequence[float],
    armed_at: Sequence[int],
    *,
    direction: str = "Long",
    atr: float = 10.0,
) -> list[ArmedCandidate]:
    """Toy armed candidates for A-class harness verification."""
    out: list[ArmedCandidate] = []
    for i, idx in enumerate(armed_at):
        if 0 <= idx < len(prices):
            out.append(
                ArmedCandidate(
                    episode_id=f"syn-{i}",
                    ts=idx,
                    direction=direction,
                    price=float(prices[idx]),
                    atr=atr,
                )
            )
    return out