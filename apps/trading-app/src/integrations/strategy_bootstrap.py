"""Per-strategy session bootstrap (replay plans, etc.) before strategy construction."""

from __future__ import annotations

import datetime
import json
import logging
from pathlib import Path
from typing import Any, Literal

from core.runtime_config import RuntimeConfig
from integrations.gudt_replay_planner import build_replay_plans_for_range
from integrations.gudt_wash_beta_planner import build_wash_beta_plans_for_range
from observability import DailyObservability
from reporting.gudt_wash_probe import (
    DayWashContext,
    WashProbeTuning,
    load_probe_contexts,
    read_probe_csv,
    run_probe_range,
)
from strategy_gudt_route_a import GudtRouteAParams
from strategy_gudt_route_a.stack_params import stack_params_from_gudt
from strategy_gudt_route_a.types import DayReplayPlan

BootstrapMode = Literal["backtest", "live"]

GUDT_REPLAY_STRATEGIES = frozenset({"gudt_route_a", "gudt_wash_beta"})

logger = logging.getLogger(__name__)

_APP_SRC = Path(__file__).resolve().parent.parent
_REPO_ROOT = _APP_SRC.parent.parent.parent


def _load_probe_rows(
    cfg: RuntimeConfig,
    *,
    code: str,
    cache_dir: Path,
    from_date: str,
    to_date: str,
    probe_csv_override: Path | None = None,
) -> list[dict[str, Any]]:
    if bool(getattr(cfg, "gudt_probe_from_ticks", False)):
        pad_from = (
            datetime.date.fromisoformat(from_date) - datetime.timedelta(days=45)
        ).isoformat()
        rows = run_probe_range(
            code=code,
            from_date=pad_from,
            to_date=to_date,
            cache_dir=cache_dir,
            tuning=WashProbeTuning(),
        )
        return [r for r in rows if from_date <= r["day"] <= to_date]

    if probe_csv_override is not None:
        csv_path = probe_csv_override
    else:
        csv_raw = str(getattr(cfg, "gudt_probe_csv", "") or "").strip()
        csv_path = (
            Path(csv_raw)
            if csv_raw
            else _REPO_ROOT
            / "workspaces/gudt-baseline/reports/gudt_wash_probe_merged_202505_202606.csv"
        )
    if csv_path.is_file():
        rows = read_probe_csv(csv_path)
        return [r for r in rows if from_date <= r["day"] <= to_date]

    pad_from = (
        datetime.date.fromisoformat(from_date) - datetime.timedelta(days=45)
    ).isoformat()
    rows = run_probe_range(
        code=code,
        from_date=pad_from,
        to_date=to_date,
        cache_dir=cache_dir,
        tuning=WashProbeTuning(),
    )
    return [r for r in rows if from_date <= r["day"] <= to_date]


def _attach_skip_reason(
    plan: DayReplayPlan,
    *,
    day: str,
    ctx_by_day: dict[str, DayWashContext],
    probe_days: set[str],
) -> None:
    if not plan.skipped:
        return
    if day in ctx_by_day:
        plan.meta.setdefault("skip_reason", "router_skip")
    elif day in probe_days:
        plan.meta.setdefault("skip_reason", "probe_error")
    else:
        plan.meta.setdefault("skip_reason", "not_gudt_day")


def wash_beta_params_from_config(cfg: RuntimeConfig) -> WashBetaParams:
    from strategy_gudt_route_a.wash_beta import WashBetaParams

    return WashBetaParams(
        friction_points=float(getattr(cfg, "gudt_friction_points", 5.0)),
        session_start=cfg.session_start,
        force_flatten_time=cfg.session_force_flatten_time,
    )


def _log_gudt_skip(
    day: str,
    plan: DayReplayPlan,
    ctx: DayWashContext | None,
    *,
    strategy: str = "gudt_route_a",
) -> None:
    reason = str((plan.meta or {}).get("skip_reason", "not_gudt_day"))
    suffix = ""
    if ctx is not None and ctx.atr:
        ext_open = (ctx.drive_high - ctx.open_0845) / ctx.atr
        suffix = (
            f" gap_pts={ctx.gap_pts:.1f} atr={ctx.atr:.1f}"
            f" ext_open={ext_open:.2f}"
            f" prior_close={ctx.prior_close:.1f}"
        )
    logger.info(
        "gudt_skip day=%s strategy=%s skip_reason=%s action=skip%s",
        day,
        strategy,
        reason,
        suffix,
    )


def day_plans_to_json(plans: dict[str, DayReplayPlan]) -> dict[str, Any]:
    return {
        day: {
            "path": p.path,
            "skipped": p.skipped,
            "events": [
                {
                    "ts": e.ts,
                    "action": e.action,
                    "price": e.price,
                    "leg": e.leg,
                    "reason": e.reason,
                }
                for e in p.events
            ],
            "meta": p.meta,
        }
        for day, p in plans.items()
    }


def write_day_plans_json(path: Path, plans: dict[str, DayReplayPlan]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(day_plans_to_json(plans), indent=2),
        encoding="utf-8",
    )


def bootstrap_gudt_route_a(
    cfg: RuntimeConfig,
    *,
    code: str,
    dates: list[datetime.date],
    cache_dir: Path,
    mode: BootstrapMode = "backtest",
    obs: DailyObservability | None = None,
    plans_out: Path | None = None,
    quiet_gudt_skip: bool = False,
    probe_csv_override: Path | None = None,
) -> dict[str, Any]:
    """Build GUDT replay ``day_plans`` for backtest (live staged bootstrap: Phase 4)."""
    del obs
    if mode == "live":
        logger.info(
            "gudt_route_a live bootstrap: empty day_plans at startup; "
            "GudtLiveBootstrapCoordinator stages intraday plan"
        )
        return {"day_plans": {}}

    if not dates:
        return {"day_plans": {}}

    from_date = min(dates).isoformat()
    to_date = max(dates).isoformat()
    day_filter = {d.isoformat() for d in dates}

    rows = _load_probe_rows(
        cfg,
        code=code,
        cache_dir=cache_dir,
        from_date=from_date,
        to_date=to_date,
        probe_csv_override=probe_csv_override,
    )
    day_strs = sorted({r["day"] for r in rows if r["day"] in day_filter})
    ctx_by_day = load_probe_contexts(code, day_strs, cache_dir=cache_dir)
    params = stack_params_from_gudt(GudtRouteAParams.from_runtime_config(cfg))
    all_plans = build_replay_plans_for_range(rows, ctx_by_day, params=params)
    day_plans = {day: plan for day, plan in all_plans.items() if day in day_filter}
    probe_days = {r["day"] for r in rows}

    for day in sorted(day_filter):
        if day not in day_plans:
            day_plans[day] = DayReplayPlan(
                day=day,
                path="skip",
                skipped=True,
                meta={"skip_reason": "not_gudt_day"},
            )

    skip_count = 0
    for day, plan in sorted(day_plans.items()):
        _attach_skip_reason(
            plan, day=day, ctx_by_day=ctx_by_day, probe_days=probe_days
        )
        if plan.skipped:
            skip_count += 1
            if not quiet_gudt_skip:
                _log_gudt_skip(day, plan, ctx_by_day.get(day))

    if not quiet_gudt_skip and skip_count:
        logger.info(
            "gudt_bootstrap backtest skip_summary strategy=gudt_route_a skipped_days=%d total_days=%d",
            skip_count,
            len(day_plans),
        )

    if plans_out is not None:
        write_day_plans_json(plans_out, day_plans)

    return {"day_plans": day_plans}


def bootstrap_gudt_wash_beta(
    cfg: RuntimeConfig,
    *,
    code: str,
    dates: list[datetime.date],
    cache_dir: Path,
    mode: BootstrapMode = "backtest",
    obs: DailyObservability | None = None,
    plans_out: Path | None = None,
    quiet_gudt_skip: bool = False,
    probe_csv_override: Path | None = None,
) -> dict[str, Any]:
    """Build wash-beta replay day_plans (open long → session flatten)."""
    del obs
    if mode == "live":
        logger.info(
            "gudt_wash_beta live bootstrap: empty day_plans at startup; "
            "GudtLiveBootstrapCoordinator stages intraday plan"
        )
        return {"day_plans": {}}

    if not dates:
        return {"day_plans": {}}

    from_date = min(dates).isoformat()
    to_date = max(dates).isoformat()
    day_filter = {d.isoformat() for d in dates}

    rows = _load_probe_rows(
        cfg,
        code=code,
        cache_dir=cache_dir,
        from_date=from_date,
        to_date=to_date,
        probe_csv_override=probe_csv_override,
    )
    day_strs = sorted({r["day"] for r in rows if r["day"] in day_filter})
    ctx_by_day = load_probe_contexts(code, day_strs, cache_dir=cache_dir)
    wb_params = wash_beta_params_from_config(cfg)
    all_plans = build_wash_beta_plans_for_range(rows, ctx_by_day, params=wb_params)
    day_plans = {day: plan for day, plan in all_plans.items() if day in day_filter}
    probe_days = {r["day"] for r in rows}

    for day in sorted(day_filter):
        if day not in day_plans:
            day_plans[day] = DayReplayPlan(
                day=day,
                path="skip",
                skipped=True,
                meta={"skip_reason": "not_gudt_day"},
            )

    skip_count = 0
    for day, plan in sorted(day_plans.items()):
        _attach_skip_reason(
            plan, day=day, ctx_by_day=ctx_by_day, probe_days=probe_days
        )
        if plan.skipped:
            skip_count += 1
            if not quiet_gudt_skip:
                _log_gudt_skip(
                    day, plan, ctx_by_day.get(day), strategy="gudt_wash_beta"
                )

    if not quiet_gudt_skip and skip_count:
        logger.info(
            "gudt_bootstrap backtest skip_summary strategy=gudt_wash_beta "
            "skipped_days=%d total_days=%d",
            skip_count,
            len(day_plans),
        )

    if plans_out is not None:
        write_day_plans_json(plans_out, day_plans)

    return {"day_plans": day_plans}


def resolve_strategy_bootstrap(
    name: str,
    cfg: RuntimeConfig,
    *,
    code: str,
    dates: list[datetime.date],
    cache_dir: Path,
    mode: BootstrapMode = "backtest",
    obs: DailyObservability | None = None,
    probe_csv_override: Path | None = None,
) -> dict[str, Any]:
    """Return extra kwargs for ``load_named_strategy``."""
    if name == "gudt_route_a":
        return bootstrap_gudt_route_a(
            cfg,
            code=code,
            dates=dates,
            cache_dir=cache_dir,
            mode=mode,
            obs=obs,
            probe_csv_override=probe_csv_override,
        )
    if name == "gudt_wash_beta":
        return bootstrap_gudt_wash_beta(
            cfg,
            code=code,
            dates=dates,
            cache_dir=cache_dir,
            mode=mode,
            obs=obs,
            probe_csv_override=probe_csv_override,
        )
    return {}


__all__ = [
    "BootstrapMode",
    "bootstrap_gudt_route_a",
    "bootstrap_gudt_wash_beta",
    "day_plans_to_json",
    "GUDT_REPLAY_STRATEGIES",
    "load_gudt_probe_rows",
    "resolve_strategy_bootstrap",
    "wash_beta_params_from_config",
    "write_day_plans_json",
]

load_gudt_probe_rows = _load_probe_rows
