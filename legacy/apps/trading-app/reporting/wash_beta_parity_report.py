"""Wash-beta CF research + parity reporting (FT-023)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from core.runtime_config import RuntimeConfig
from integrations.strategy_bootstrap import (
    bootstrap_gudt_wash_beta,
    day_plans_to_json,
    load_gudt_probe_rows,
    wash_beta_params_from_config,
)
from reporting.gudt_wash_probe import DayWashContext, load_probe_contexts
from strategy_gudt_route_a.types import DayReplayPlan
from strategy_gudt_route_a.wash_beta import simulate_wash_beta_day, summarize_wash_beta


def _cf_picks_for_range(
    ctx_by_day: dict[str, DayWashContext],
    cfg: RuntimeConfig,
) -> list[dict[str, Any]]:
    params = wash_beta_params_from_config(cfg)
    picks: list[dict[str, Any]] = []
    for day in sorted(ctx_by_day):
        sim = simulate_wash_beta_day(ctx_by_day[day], params=params)
        if sim is None:
            continue
        picks.append({"day": day, "path": "wash_beta", **sim})
    return picks


def build_wash_beta_research_report(
    cfg: RuntimeConfig,
    *,
    code: str,
    cache_dir: Path,
    from_date: str,
    to_date: str,
    day_plans: dict[str, DayReplayPlan] | dict[str, Any] | None = None,
    probe_csv_override: Path | None = None,
) -> dict[str, Any]:
    rows = load_gudt_probe_rows(
        cfg,
        code=code,
        cache_dir=cache_dir,
        from_date=from_date,
        to_date=to_date,
        probe_csv_override=probe_csv_override,
    )
    day_strs = sorted({r["day"] for r in rows})
    ctx_by_day = load_probe_contexts(code, day_strs, cache_dir=cache_dir)
    picks = _cf_picks_for_range(ctx_by_day, cfg)
    picks = [p for p in picks if from_date <= p["day"] <= to_date]
    summary = summarize_wash_beta(picks)
    return {
        "strategy": "gudt_wash_beta",
        "from_date": from_date,
        "to_date": to_date,
        "summary": summary,
        "picks": picks,
        "n_ctx": len(ctx_by_day),
    }


def build_wash_beta_parity_report(
    cfg: RuntimeConfig,
    *,
    code: str,
    cache_dir: Path,
    from_date: str,
    to_date: str,
    day_plans: dict[str, DayReplayPlan] | dict[str, Any] | None = None,
    probe_csv_override: Path | None = None,
    plans_source: str = "bootstrap",
) -> dict[str, Any]:
    research = build_wash_beta_research_report(
        cfg,
        code=code,
        cache_dir=cache_dir,
        from_date=from_date,
        to_date=to_date,
        probe_csv_override=probe_csv_override,
    )
    cf_picks = {p["day"]: p for p in research["picks"]}

    if day_plans is None:
        import datetime as dt

        dates = [
            dt.date.fromisoformat(d)
            for d in sorted(cf_picks)
            if from_date <= d <= to_date
        ]
        boot = bootstrap_gudt_wash_beta(
            cfg,
            code=code,
            dates=dates,
            cache_dir=cache_dir,
            quiet_gudt_skip=True,
            probe_csv_override=probe_csv_override,
        )
        plans_raw = boot["day_plans"]
        plans = day_plans_to_json(plans_raw)
    else:
        sample = next(iter(day_plans.values()), {})
        if isinstance(sample, DayReplayPlan):
            plans = day_plans_to_json(day_plans)  # type: ignore[arg-type]
        else:
            plans = dict(day_plans)

    mismatches: list[dict[str, Any]] = []
    for day, pick in cf_picks.items():
        plan = plans.get(day)
        if plan is None:
            mismatches.append({"day": day, "reason": "missing_plan"})
            continue
        if plan.get("skipped"):
            mismatches.append({"day": day, "reason": "plan_skipped"})
            continue
        if str(plan.get("path")) != "wash_beta":
            mismatches.append({"day": day, "reason": "path_mismatch"})
        meta_net = float((plan.get("meta") or {}).get("net", 0))
        if abs(meta_net - float(pick["net"])) > 0.01:
            mismatches.append(
                {"day": day, "reason": "net_mismatch", "cf": pick["net"], "plan": meta_net}
            )

    traded_days = [
        d for d, p in plans.items() if from_date <= d <= to_date and not p.get("skipped")
    ]
    failures: list[str] = []
    if len(cf_picks) != len(traded_days):
        failures.append(
            f"day_count cf={len(cf_picks)} kernel_plans={len(traded_days)}"
        )
    for m in mismatches:
        failures.append(f"{m.get('day')}: {m.get('reason')}")

    return {
        "strategy": "gudt_wash_beta",
        "plans_source": plans_source,
        "from_date": from_date,
        "to_date": to_date,
        "summary": {
            "cf": research["summary"],
            "kernel_plan_days": len(traded_days),
        },
        "mismatches": mismatches,
        "failures": failures,
        "pass": len(failures) == 0,
    }


def emit_wash_beta_backtest_reports(
    cfg: RuntimeConfig,
    *,
    code: str,
    dates: list[Any],
    cache_dir: Path,
    day_plans: dict[str, DayReplayPlan],
    kernel_metrics: dict[str, Any],
    research_path: Path,
    parity_path: Path,
    probe_csv_override: Path | None = None,
) -> dict[str, Any]:
    from_date = min(d.isoformat() for d in dates)
    to_date = max(d.isoformat() for d in dates)
    research = build_wash_beta_research_report(
        cfg,
        code=code,
        cache_dir=cache_dir,
        from_date=from_date,
        to_date=to_date,
        day_plans=day_plans,
        probe_csv_override=probe_csv_override,
    )
    parity = build_wash_beta_parity_report(
        cfg,
        code=code,
        cache_dir=cache_dir,
        from_date=from_date,
        to_date=to_date,
        day_plans=day_plans,
        probe_csv_override=probe_csv_override,
        plans_source="backtest",
    )
    research_path.parent.mkdir(parents=True, exist_ok=True)
    research_path.write_text(json.dumps(research, indent=2), encoding="utf-8")
    parity_path.write_text(json.dumps(parity, indent=2), encoding="utf-8")
    return {"research": research, "parity": parity, "kernel": kernel_metrics}


def write_json_report(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
