"""GUDT Route A research + parity reporting (FT-022 Phase 5)."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any, Literal

from core.runtime_config import RuntimeConfig
from integrations.strategy_bootstrap import bootstrap_gudt_route_a, day_plans_to_json, load_gudt_probe_rows
from reporting.gudt_wash_probe import (
    BPrimeCompositeParams,
    DayWashContext,
    WashProbeTuning,
    load_probe_contexts,
    run_probe_range,
)
from strategy_gudt_route_a import GudtRouteAParams
from strategy_gudt_route_a.stack import summarize_route_a_stack
from strategy_gudt_route_a.stack_params import stack_params_from_gudt
from strategy_gudt_route_a.types import DayReplayPlan

HOLDOUTS = (
    ("H1_2026", "2026-01-01", "2026-05-31"),
    ("UAT_2m", "2026-05-01", "2026-06-30"),
    ("full", "2025-05-01", "2026-06-30"),
)

H1_2026_TARGET = 1290.0
FULL_NET_TARGET = 1781.0
FULL_NET_TOL = 15.0
EXTEND_DAYS_TARGET = 4
FLIP_DAYS_TARGET = 2


def _slice_net(picks: list[dict[str, Any]], f: str, t: str) -> float:
    return round(sum(float(p["net"]) for p in picks if f <= p["day"] <= t), 2)


def _plans_payload(plans: dict[str, DayReplayPlan] | dict[str, Any]) -> dict[str, dict[str, Any]]:
    if not plans:
        return {}
    sample = next(iter(plans.values()))
    if isinstance(sample, DayReplayPlan):
        return day_plans_to_json(plans)  # type: ignore[arg-type]
    return dict(plans)


def _decision_mismatches(
    cf_picks: dict[str, dict[str, Any]],
    plans: dict[str, Any],
) -> list[dict[str, Any]]:
    mismatches: list[dict[str, Any]] = []
    for day, pick in cf_picks.items():
        plan = plans.get(day)
        if plan is None:
            mismatches.append({"day": day, "reason": "missing_plan"})
            continue
        if bool(pick.get("route_a_extended")) != bool((plan.get("meta") or {}).get("route_a_extended")):
            mismatches.append({"day": day, "reason": "extend_mismatch"})
        if str(pick.get("hedge", "none")) != str((plan.get("meta") or {}).get("hedge", "none")):
            mismatches.append({"day": day, "reason": "hedge_mismatch"})
        cf_confirm = pick.get("dist_confirm")
        pl_confirm = (plan.get("meta") or {}).get("dist_confirm")
        if cf_confirm != pl_confirm:
            mismatches.append(
                {"day": day, "reason": "confirm_mismatch", "cf": cf_confirm, "plan": pl_confirm}
            )
    return mismatches


def _skip_stats(plans: dict[str, Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for plan in plans.values():
        if not plan.get("skipped"):
            continue
        reason = str((plan.get("meta") or {}).get("skip_reason", "unknown"))
        counts[reason] = counts.get(reason, 0) + 1
    return counts


def load_probe_rows_for_range(
    cfg: RuntimeConfig,
    *,
    code: str,
    cache_dir: Path,
    from_date: str,
    to_date: str,
    probe_csv_override: Path | None = None,
) -> list[dict[str, Any]]:
    return load_gudt_probe_rows(
        cfg,
        code=code,
        cache_dir=cache_dir,
        from_date=from_date,
        to_date=to_date,
        probe_csv_override=probe_csv_override,
    )


def bootstrap_plans_for_range(
    cfg: RuntimeConfig,
    *,
    code: str,
    cache_dir: Path,
    from_date: str,
    to_date: str,
    probe_csv_override: Path | None = None,
    quiet_gudt_skip: bool = True,
) -> dict[str, DayReplayPlan]:
    pad_from = (dt.date.fromisoformat(from_date) - dt.timedelta(days=45)).isoformat()
    if bool(getattr(cfg, "gudt_probe_from_ticks", False)):
        rows = run_probe_range(
            code=code,
            from_date=pad_from,
            to_date=to_date,
            cache_dir=cache_dir,
            tuning=WashProbeTuning(),
        )
        rows = [r for r in rows if from_date <= r["day"] <= to_date]
    else:
        rows = load_probe_rows_for_range(
            cfg,
            code=code,
            cache_dir=cache_dir,
            from_date=from_date,
            to_date=to_date,
            probe_csv_override=probe_csv_override,
        )
    dates = sorted({dt.date.fromisoformat(r["day"]) for r in rows})
    if not dates:
        return {}
    out = bootstrap_gudt_route_a(
        cfg,
        code=code,
        dates=dates,
        cache_dir=cache_dir,
        mode="backtest",
        quiet_gudt_skip=quiet_gudt_skip,
        probe_csv_override=probe_csv_override,
    )
    return out["day_plans"]


def build_research_report(
    cfg: RuntimeConfig,
    *,
    code: str,
    cache_dir: Path,
    from_date: str,
    to_date: str,
    day_plans: dict[str, DayReplayPlan] | dict[str, Any] | None = None,
    probe_csv_override: Path | None = None,
) -> dict[str, Any]:
    """CF ledger + skip statistics for ``gudt_route_a``."""
    rows = load_probe_rows_for_range(
        cfg,
        code=code,
        cache_dir=cache_dir,
        from_date=from_date,
        to_date=to_date,
        probe_csv_override=probe_csv_override,
    )
    days = sorted({r["day"] for r in rows})
    ctx_by_day: dict[str, DayWashContext] = load_probe_contexts(code, days, cache_dir=cache_dir)
    params = stack_params_from_gudt(GudtRouteAParams.from_runtime_config(cfg))
    summary = summarize_route_a_stack(rows, ctx_by_day=ctx_by_day, params=params)

    if day_plans is None:
        day_plans = bootstrap_plans_for_range(
            cfg,
            code=code,
            cache_dir=cache_dir,
            from_date=from_date,
            to_date=to_date,
            probe_csv_override=probe_csv_override,
        )
    plans_json = _plans_payload(day_plans)

    return {
        "strategy": "gudt_route_a",
        "from": from_date,
        "to": to_date,
        "cf_net_total": float(summary["net_total"]),
        "cf_n": int(summary["n"]),
        "cf_extend_days": int(summary["extend_days"]),
        "cf_flip_days": int(summary["flip_days"]),
        "cf_confirm_veto": int(summary["confirm_veto"]),
        "slices": {label: _slice_net(summary["picks"], f, t) for label, f, t in HOLDOUTS},
        "picks": summary["picks"],
        "skip_stats": _skip_stats(plans_json),
        "plan_days": len(plans_json),
        "traded_plan_days": sum(1 for p in plans_json.values() if not p.get("skipped")),
    }


def build_parity_report(
    cfg: RuntimeConfig,
    *,
    code: str,
    cache_dir: Path,
    from_date: str,
    to_date: str,
    day_plans: dict[str, DayReplayPlan] | dict[str, Any] | None = None,
    probe_csv_override: Path | None = None,
    kernel_metrics: dict[str, Any] | None = None,
    plans_source: Literal["bootstrap", "file"] = "bootstrap",
) -> dict[str, Any]:
    """CF vs bootstrap plan decisions + oracle targets (``ft021_parity_check``)."""
    research = build_research_report(
        cfg,
        code=code,
        cache_dir=cache_dir,
        from_date=from_date,
        to_date=to_date,
        day_plans=day_plans,
        probe_csv_override=probe_csv_override,
    )
    rows = load_probe_rows_for_range(
        cfg,
        code=code,
        cache_dir=cache_dir,
        from_date=from_date,
        to_date=to_date,
        probe_csv_override=probe_csv_override,
    )
    days = sorted({r["day"] for r in rows})
    ctx_by_day = load_probe_contexts(code, days, cache_dir=cache_dir)
    params = stack_params_from_gudt(GudtRouteAParams.from_runtime_config(cfg))
    summary = summarize_route_a_stack(rows, ctx_by_day=ctx_by_day, params=params)
    picks = summary["picks"]
    cf_by_day = {p["day"]: p for p in picks}

    from reporting.gudt_wash_probe import summarize_b_prime_composite

    br5 = summarize_b_prime_composite(
        rows,
        ctx_by_day=ctx_by_day,
        params=BPrimeCompositeParams(
            pre_break_br_min=0.35, pre_break_br_p0_only=True, flip_min_ext_open=999.0
        ),
    )
    br5_slices = {label: _slice_net(br5["picks"], f, t) for label, f, t in HOLDOUTS}

    if day_plans is None:
        day_plans = bootstrap_plans_for_range(
            cfg,
            code=code,
            cache_dir=cache_dir,
            from_date=from_date,
            to_date=to_date,
            probe_csv_override=probe_csv_override,
        )
    plans = _plans_payload(day_plans)
    decision_mm = _decision_mismatches(cf_by_day, plans)
    failures = parity_failures(research, br5_slices=br5_slices, decision_mismatches=decision_mm)

    kernel_pnl = None
    if kernel_metrics is not None:
        kernel_pnl = float(kernel_metrics.get("daily_pnl_points", 0.0))

    return {
        "from": from_date,
        "to": to_date,
        "plans_source": plans_source,
        "cf_net_total": research["cf_net_total"],
        "cf_extend_days": research["cf_extend_days"],
        "cf_flip_days": research["cf_flip_days"],
        "cf_confirm_veto": research["cf_confirm_veto"],
        "slices": research["slices"],
        "br5_slices": br5_slices,
        "kernel_daily_pnl_points": kernel_pnl,
        "targets": {
            "full_net": FULL_NET_TARGET,
            "full_net_tol": FULL_NET_TOL,
            "extend_days": EXTEND_DAYS_TARGET,
            "flip_days": FLIP_DAYS_TARGET,
        },
        "decision_mismatches": decision_mm,
        "skip_stats": research["skip_stats"],
        "pass": not failures,
        "failures": failures,
    }


def parity_failures(
    research: dict[str, Any],
    *,
    br5_slices: dict[str, float],
    decision_mismatches: list[dict[str, Any]],
) -> list[str]:
    failures: list[str] = []
    full_net = float(research["cf_net_total"])
    if abs(full_net - FULL_NET_TARGET) > FULL_NET_TOL:
        failures.append(f"full_net {full_net} not within ±{FULL_NET_TOL} of {FULL_NET_TARGET}")

    if int(research["cf_extend_days"]) != EXTEND_DAYS_TARGET:
        failures.append(
            f"extend_days {research['cf_extend_days']} != {EXTEND_DAYS_TARGET}"
        )

    if int(research["cf_flip_days"]) != FLIP_DAYS_TARGET:
        failures.append(f"flip_days {research['cf_flip_days']} != {FLIP_DAYS_TARGET}")

    slices = research["slices"]
    h1_2026 = float(slices["H1_2026"])
    if abs(h1_2026 - H1_2026_TARGET) > FULL_NET_TOL:
        failures.append(f"H1 2026 {h1_2026} not within ±{FULL_NET_TOL} of {H1_2026_TARGET}")

    uat_stack = float(slices["UAT_2m"])
    uat_br5 = float(br5_slices["UAT_2m"])
    if uat_stack <= uat_br5:
        failures.append(f"UAT 2m not better than br5: {uat_stack} vs {uat_br5}")

    if decision_mismatches:
        failures.append(f"decision_mismatches n={len(decision_mismatches)}")

    return failures


def write_json_report(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def emit_gudt_backtest_reports(
    cfg: RuntimeConfig,
    *,
    code: str,
    dates: list[dt.date],
    cache_dir: Path,
    day_plans: dict[str, DayReplayPlan],
    kernel_metrics: dict[str, Any] | None,
    research_path: Path,
    parity_path: Path,
    probe_csv_override: Path | None = None,
) -> dict[str, Any]:
    """Write ``research.json`` and ``parity.json`` after a GUDT backtest."""
    if not dates:
        return {}
    from_date = min(dates).isoformat()
    to_date = max(dates).isoformat()
    research = build_research_report(
        cfg,
        code=code,
        cache_dir=cache_dir,
        from_date=from_date,
        to_date=to_date,
        day_plans=day_plans,
        probe_csv_override=probe_csv_override,
    )
    parity = build_parity_report(
        cfg,
        code=code,
        cache_dir=cache_dir,
        from_date=from_date,
        to_date=to_date,
        day_plans=day_plans,
        probe_csv_override=probe_csv_override,
        kernel_metrics=kernel_metrics,
        plans_source="bootstrap",
    )
    write_json_report(research_path, research)
    write_json_report(parity_path, parity)
    return {"research": research, "parity": parity}


__all__ = [
    "EXTEND_DAYS_TARGET",
    "FLIP_DAYS_TARGET",
    "FULL_NET_TARGET",
    "FULL_NET_TOL",
    "HOLDOUTS",
    "bootstrap_plans_for_range",
    "build_parity_report",
    "build_research_report",
    "emit_gudt_backtest_reports",
    "parity_failures",
    "write_json_report",
]
