"""Phase 5: Walk-forward parameter sweep over backtest DAILY_SUMMARY KPIs."""

from __future__ import annotations

import itertools
import json
import logging
from pathlib import Path
from typing import Any

from backtest.engine import BacktestEngine
from config import (
    SWEEP_DD_PENALTY,
    SWEEP_MAX_GRID_COMBOS,
    SWEEP_MAX_GRID_KEYS,
    SWEEP_SCORE_METRIC,
    SWEEP_SL_PENALTY,
)
from core.runtime_config import default_runtime_config
from reporting.performance_metrics import aggregate_daily_performance, sweep_score_from_kpi
from reporting.forward_pnl import ForwardPnlPolicy, load_tick_series, make_replay_forward_pnl
from reporting.structure_calibration import (
    armed_candidates_from_decision_dicts,
    compute_regime_veto_calibration,
)
from reporting.trend_calibration import compute_trend_veto_calibration
from storage.kbar_loader import iter_kbars_in_range
from storage.legacy_cache_migrate import ensure_legacy_kbars_migrated
from storage.tick_loader import DEFAULT_CACHE_DIR
from strategy_vwap_momentum.structure import StructureParams
from trading_engine.core.runtime_config import normalize_overlay_key
from strategy_vwap_momentum import apply_strategy_params, restore_strategy_params
from sweep.determinism_check import _run_with_audit_capture
from sweep.holdout_guard import assert_dates_unsealed
from sweep.sweep_progress import SweepProgressTracker, slim_sweep_row

DEFAULT_PENALTY = 50.0
MAX_GRID_COMBOS = SWEEP_MAX_GRID_COMBOS
MAX_GRID_KEYS = SWEEP_MAX_GRID_KEYS
logger = logging.getLogger(__name__)

# param_sweep KPI only needs DAILY_SUMMARY unless trend/structure grid keys need audits.
_CAPTURE_DAILY_SUMMARY = ("DAILY_SUMMARY ",)

# Backward-compatible aliases for tests
_apply_params = apply_strategy_params
_restore_params = restore_strategy_params


def _has_trend_params(params: dict[str, Any]) -> bool:
    return any(
        str(k).startswith("trend_") or str(k).upper().startswith("TREND_")
        for k in params
    )


def _has_structure_params(params: dict[str, Any]) -> bool:
    return any(
        str(k).startswith("structure_") or str(k).upper().startswith("STRUCTURE_")
        for k in params
    )


def _regime_params_conflict(params: dict[str, Any]) -> bool:
    normalized: dict[str, Any] = {}
    for key, value in params.items():
        normalized[normalize_overlay_key(key)] = value
    return bool(normalized.get("STRUCTURE_FILTER_ENABLED")) and bool(
        normalized.get("TREND_FILTER_ENABLED")
    )


def _capture_prefixes_for_params(params: dict[str, Any]) -> tuple[str, ...]:
    prefixes = list(_CAPTURE_DAILY_SUMMARY)
    if _has_trend_params(params):
        prefixes.append("SIGNAL_AUDIT ")
    if _has_structure_params(params):
        prefixes.append("DECISION_AUDIT ")
    return tuple(prefixes)


def _run_backtest_summaries(
    code: str,
    dates: list,
    cache_dir: Path,
    runtime_config=None,
    *,
    progress: SweepProgressTracker | None = None,
    phase: str = "",
    capture_prefixes: tuple[str, ...] | None = None,
    bulk_days: bool = True,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Run backtest under capture handler.
    Returns (daily_summaries, signal_audits, decision_audits).
    """
    if progress is not None and dates and not bulk_days:
        progress.phase_start(phase, day_total=len(dates))
        summaries: list[dict[str, Any]] = []
        signals: list[dict[str, Any]] = []
        decisions: list[dict[str, Any]] = []
        for day_index, day in enumerate(dates, start=1):
            s, sig, dec = _run_backtest_summaries(
                code,
                [day],
                cache_dir,
                runtime_config=runtime_config,
                capture_prefixes=capture_prefixes,
                bulk_days=True,
            )
            summaries.extend(s)
            signals.extend(sig)
            decisions.extend(dec)
            progress.day_complete(day_index, len(dates), day, phase)
        return summaries, signals, decisions

    if progress is not None and dates and bulk_days:
        progress.phase_start(phase, day_total=len(dates))

    def _run() -> None:
        engine = BacktestEngine(
            code, dates, cache_dir=cache_dir, runtime_config=runtime_config
        )
        engine.run()

    records = _run_with_audit_capture(_run, capture_prefixes=capture_prefixes)
    summaries: list[dict[str, Any]] = []
    signals: list[dict[str, Any]] = []
    decisions: list[dict[str, Any]] = []
    for label, payload in records:
        if label == "DAILY_SUMMARY":
            try:
                summaries.append(json.loads(payload))
            except json.JSONDecodeError as exc:
                logger.warning("param_sweep: skip malformed DAILY_SUMMARY: %s", exc)
        elif label == "SIGNAL_AUDIT":
            try:
                signals.append(json.loads(payload))
            except json.JSONDecodeError as exc:
                logger.warning("param_sweep: skip malformed SIGNAL_AUDIT: %s", exc)
        elif label == "DECISION_AUDIT":
            try:
                decisions.append(json.loads(payload))
            except json.JSONDecodeError as exc:
                logger.warning("param_sweep: skip malformed DECISION_AUDIT: %s", exc)
    return summaries, signals, decisions


def _aggregate_kpi(summaries: list[dict[str, Any]]) -> dict[str, Any]:
    if not summaries:
        return {
            "daily_pnl_points": 0.0,
            "quick_stop_loss_rate": None,
            "trade_count": 0,
            "day_count": 0,
            "performance_aggregate": aggregate_daily_performance([]),
            "_summaries": [],
        }
    total_pnl = sum(
        float(s.get("pnl", {}).get("daily_pnl_points", 0.0)) for s in summaries
    )
    total_quick_sl = sum(
        int(s.get("quick_stop_loss", {}).get("count", 0) or 0) for s in summaries
    )
    total_exits = sum(
        int(s.get("fills", {}).get("exit_count", 0) or 0) for s in summaries
    )
    weighted_rate = (
        total_quick_sl / total_exits if total_exits > 0 else None
    )
    perf_agg = aggregate_daily_performance(summaries)
    kpi = {
        "daily_pnl_points": round(total_pnl, 2),
        "quick_stop_loss_rate": weighted_rate,
        "trade_count": total_exits,
        "day_count": len(summaries),
        "performance_aggregate": perf_agg,
        "_summaries": summaries,
    }
    kpi["valid_score"] = sweep_score_from_kpi(
        kpi,
        metric=SWEEP_SCORE_METRIC,
        dd_penalty=SWEEP_DD_PENALTY,
        sl_penalty=SWEEP_SL_PENALTY,
    )
    return kpi


def valid_score(valid_kpi: dict[str, Any], *, penalty: float = DEFAULT_PENALTY) -> float:
    if "valid_score" in valid_kpi:
        return float(valid_kpi["valid_score"])
    rate = valid_kpi.get("quick_stop_loss_rate") or 0.0
    return float(valid_kpi.get("daily_pnl_points", 0.0)) - penalty * rate


def _resolve_forward_pnl(
    code: str,
    dates_valid: list,
    cache_path: Path,
    forward_policy: ForwardPnlPolicy | None,
):
    if forward_policy is None:
        return None
    series = load_tick_series(code, dates_valid, cache_dir=cache_path)
    if not series.timestamps:
        return None
    return make_replay_forward_pnl(series, forward_policy)


def grid_combo_count(grid: dict[str, list]) -> int:
    if not grid:
        return 0
    count = 1
    for values in grid.values():
        count *= len(values)
    return count


def _partition_combos(
    keys: list[str], combos: list[tuple]
) -> tuple[list[tuple[int, dict[str, Any]]], list[tuple[int, dict[str, Any]]]]:
    """Split cartesian combos into runnable vs regime-conflict skips."""
    runnable: list[tuple[int, dict[str, Any]]] = []
    skipped: list[tuple[int, dict[str, Any]]] = []
    for combo_idx, combo in enumerate(combos, start=1):
        params = dict(zip(keys, combo))
        if _regime_params_conflict(params):
            skipped.append((combo_idx, params))
        else:
            runnable.append((combo_idx, params))
    return runnable, skipped


def validate_sweep_inputs(
    grid: dict[str, list],
    dates_train: list,
    dates_valid: list,
) -> None:
    """Raise before mutating sweep progress/result artifacts."""
    assert_dates_unsealed(list(dates_train) + list(dates_valid))
    if not dates_train:
        raise ValueError("dates_train is empty; need at least one train day")
    if not dates_valid:
        raise ValueError("dates_valid is empty; need at least one valid day")
    if not grid:
        raise ValueError("grid is empty")
    for key, values in grid.items():
        if not values:
            raise ValueError(f"grid key {key!r} has no values")
    if len(grid) > MAX_GRID_KEYS:
        raise ValueError(
            f"grid has {len(grid)} keys; max {MAX_GRID_KEYS} per FT-003 SPEC §4.4"
        )
    combo_count = grid_combo_count(grid)
    if combo_count == 0:
        raise ValueError("grid yields zero combos")
    if combo_count > MAX_GRID_COMBOS:
        raise ValueError(
            f"grid has {combo_count} combos; max {MAX_GRID_COMBOS} per FT-003 SPEC §4.4"
        )


def assert_sweep_has_runnable_combos(grid: dict[str, list]) -> None:
    """CLI gate before truncating sweep artifacts; ``sweep()`` may still skip combos."""
    keys = list(grid.keys())
    combos = list(itertools.product(*(grid[k] for k in keys)))
    runnable, _ = _partition_combos(keys, combos)
    if not runnable:
        raise ValueError("grid has no runnable combos (all regime-conflict skips)")


def sweep(
    grid: dict[str, list],
    dates_train: list,
    dates_valid: list,
    code: str,
    cache_dir=DEFAULT_CACHE_DIR,
    *,
    penalty: float = DEFAULT_PENALTY,
    output_path: Path | None = None,
    forward_policy: ForwardPnlPolicy | None = None,
    progress: SweepProgressTracker | None = None,
    bulk_days: bool = True,
) -> list[dict[str, Any]]:
    """Cartesian grid sweep; ranking uses valid (out-of-sample) KPI only."""
    validate_sweep_inputs(grid, dates_train, dates_valid)
    cache_path = Path(cache_dir)
    ensure_legacy_kbars_migrated(cache_path)
    replay_fwd = _resolve_forward_pnl(code, dates_valid, cache_path, forward_policy)
    keys = list(grid.keys())
    combos = list(itertools.product(*(grid[k] for k in keys)))
    combo_total = len(combos)
    runnable, skipped = _partition_combos(keys, combos)
    results: list[dict[str, Any]] = []

    if progress is not None:
        for combo_idx, params in skipped:
            progress.combo_skipped(
                combo_idx,
                combo_total,
                params,
                reason="regime_conflict",
            )
            logger.warning(
                "param_sweep: skip mutually exclusive regime combo %s", params
            )
    else:
        for _combo_idx, params in skipped:
            logger.warning(
                "param_sweep: skip mutually exclusive regime combo %s", params
            )

    run_total = len(runnable)
    for run_index, (combo_idx, params) in enumerate(runnable, start=1):
        logger.info(
            "param_sweep combo %d/%d (run %d/%d) train=%d valid=%d %s",
            combo_idx,
            combo_total,
            run_index,
            run_total,
            len(dates_train),
            len(dates_valid),
            params,
        )
        if progress is not None:
            progress.combo_start(
                combo_idx,
                combo_total,
                params,
                run_index=run_index,
                run_total=run_total,
                train_days=len(dates_train),
                valid_days=len(dates_valid),
            )
        cfg = default_runtime_config()
        saved = apply_strategy_params(params, cfg)
        capture_prefixes = _capture_prefixes_for_params(params)
        try:
            train_summaries, _train_signals, _train_decisions = _run_backtest_summaries(
                code,
                dates_train,
                cache_path,
                runtime_config=cfg,
                progress=progress,
                phase="train",
                capture_prefixes=capture_prefixes,
                bulk_days=bulk_days,
            )
            valid_summaries, valid_signals, valid_decisions = _run_backtest_summaries(
                code,
                dates_valid,
                cache_path,
                runtime_config=cfg,
                progress=progress,
                phase="valid",
                capture_prefixes=capture_prefixes,
                bulk_days=bulk_days,
            )
            train_kpi = _aggregate_kpi(train_summaries)
            valid_kpi = _aggregate_kpi(valid_summaries)
            # P6-1-CAL-3/4/6: if trend params present, feed captured SIGNAL_AUDITs (reason=trend_veto)
            # from the valid run into the harness instead of hardcoded [].
            # This makes veto_metrics a real (if still synthetic-toy fwd for A-class) conditional
            # expectation instead of an empty-shell always-0 structure.
            # B-class will supply better get_forward_pnl from replay + real UAT logs.
            veto_metrics: dict[str, Any] | None = None
            structure_veto_metrics: dict[str, Any] | None = None
            if _has_trend_params(params):
                try:
                    veto_audits = [
                        s
                        for s in valid_signals
                        if str(s.get("reason", "")).lower() in ("trend_veto", "trend veto")
                        or "trend_veto" in str(s)
                    ]
                    allowed_audits = [
                        s
                        for s in valid_signals
                        if s.get("intent") == "entry"
                        and str(s.get("reason", "")).lower() not in ("trend_veto", "trend veto")
                    ]
                    veto_metrics = compute_trend_veto_calibration(
                        veto_audits,
                        allowed_audits=allowed_audits or None,
                        get_forward_pnl=replay_fwd,
                        forward_policy=forward_policy,
                        b_class=replay_fwd is not None,
                    )
                except Exception as exc:
                    logger.warning(
                        "param_sweep: trend veto harness failed for %s: %s",
                        params,
                        exc,
                    )
                    veto_metrics = {"note": "harness call failed (synthetic path)"}
            if _has_structure_params(params):
                try:
                    ms = float(
                        params.get("structure_min_strength")
                        or params.get("STRUCTURE_MIN_STRENGTH")
                        or cfg.structure_min_strength
                    )
                    sp = StructureParams(structure_min_strength=ms)
                    candidates = armed_candidates_from_decision_dicts(valid_decisions)
                    if dates_valid:
                        bars_1m = iter_kbars_in_range(
                            code,
                            min(dates_valid),
                            max(dates_valid),
                            cache_dir=cache_path,
                        )
                    else:
                        bars_1m = []
                    if candidates and bars_1m:
                        structure_veto_metrics = compute_regime_veto_calibration(
                            candidates,
                            scenario="structure_only",
                            bars_1m=bars_1m,
                            structure_params=sp,
                            get_forward_pnl=replay_fwd,
                            forward_policy=forward_policy,
                            b_class=replay_fwd is not None,
                        )
                    else:
                        structure_veto_metrics = {
                            "note": "structure harness skipped (no armed or kbars)"
                        }
                except Exception as exc:
                    logger.warning(
                        "param_sweep: structure veto harness failed for %s: %s",
                        params,
                        exc,
                    )
                    structure_veto_metrics = {"note": "structure harness call failed"}
            row = {
                "params": params,
                "train_kpi": train_kpi,
                "valid_kpi": valid_kpi,
                "valid_score": valid_score(valid_kpi, penalty=penalty),
            }
            if veto_metrics is not None:
                row["veto_metrics"] = veto_metrics
            if structure_veto_metrics is not None:
                row["structure_veto_metrics"] = structure_veto_metrics
            results.append(row)
            if progress is not None:
                progress.combo_done(row)
        finally:
            restore_strategy_params(saved, cfg)

    results.sort(key=lambda row: row["valid_score"], reverse=True)

    if output_path is not None:
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        tmp = out.with_name(out.name + ".tmp")
        with tmp.open("w", encoding="utf-8") as f:
            for row in results:
                f.write(json.dumps(slim_sweep_row(row), ensure_ascii=False) + "\n")
        tmp.replace(out)

    return results
