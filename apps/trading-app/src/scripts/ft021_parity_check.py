"""FT-021: parity check — counterfactual stack vs kernel baseline day ledger."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from pathlib import Path
from typing import Any

from config import load_config
from core.runtime_config import TradingAppRuntimeConfig, _to_engine_settings, default_runtime_config
from integrations.gudt_replay_planner import build_replay_plans_for_range
from strategy_gudt_route_a import GudtRouteAParams
from strategy_gudt_route_a.stack import summarize_route_a_stack
from strategy_gudt_route_a.stack_params import stack_params_from_gudt
from reporting.gudt_wash_probe import (
    BPrimeCompositeParams,
    WashProbeTuning,
    load_probe_contexts,
    read_probe_csv,
    run_probe_range,
    summarize_b_prime_composite,
)

HOLDOUTS = (
    ("H1_2026", "2026-01-01", "2026-05-31"),
    ("UAT_2m", "2026-05-01", "2026-06-30"),
    ("full", "2025-05-01", "2026-06-30"),
)

H1_2026_TARGET = 236.0

FULL_NET_TARGET = 683.0
FULL_NET_TOL = 15.0
EXTEND_DAYS_TARGET = 4
FLIP_DAYS_TARGET = 1


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _slice_net(picks: list[dict[str, Any]], f: str, t: str) -> float:
    return round(sum(float(p["net"]) for p in picks if f <= p["day"] <= t), 2)


def _load_rows(root: Path, args: argparse.Namespace) -> list[dict[str, Any]]:
    reports = root / "workspaces" / "gudt-baseline" / "reports"
    csv_path = args.from_csv or reports / "gudt_wash_probe_merged_202505_202606.csv"
    if csv_path.is_file():
        rows = read_probe_csv(csv_path)
        return [r for r in rows if args.from_date <= r["day"] <= args.to_date]
    pad_from = (dt.date.fromisoformat(args.from_date) - dt.timedelta(days=45)).isoformat()
    rows = run_probe_range(
        code=args.code,
        from_date=pad_from,
        to_date=args.to_date,
        cache_dir=args.cache_dir,
        tuning=WashProbeTuning(),
    )
    return [r for r in rows if args.from_date <= r["day"] <= args.to_date]


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


def _plans_payload(plans: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for day, p in plans.items():
        if hasattr(p, "meta"):
            out[day] = {
                "path": p.path,
                "skipped": p.skipped,
                "meta": p.meta,
                "events": [
                    {"ts": e.ts, "leg": e.leg} for e in getattr(p, "events", [])
                ],
            }
        else:
            out[day] = p
    return out


def main(argv: list[str] | None = None) -> int:
    root = _repo_root()
    ws = root / "workspaces" / "gudt-route-a-baseline"
    parser = argparse.ArgumentParser(description="FT-021 parity check")
    parser.add_argument("--from", dest="from_date", default="2025-05-01")
    parser.add_argument("--to", dest="to_date", default="2026-06-30")
    parser.add_argument("--code", default="TMFR1")
    parser.add_argument("--cache-dir", type=Path, default=root / "tick_cache")
    parser.add_argument("--config", type=Path, default=ws / "config" / "config.yaml")
    parser.add_argument("--from-csv", type=Path, default=None)
    parser.add_argument("--plans", type=Path, default=ws / "reports" / "day_plans.json")
    parser.add_argument("--out", type=Path, default=ws / "reports" / "parity_report.json")
    args = parser.parse_args(argv)

    if args.config.is_file():
        os.environ["CONFIG_PATH"] = str(args.config.resolve())
        cfg = TradingAppRuntimeConfig(_to_engine_settings(load_config(args.config)))
    else:
        cfg = default_runtime_config()
    params = stack_params_from_gudt(GudtRouteAParams.from_runtime_config(cfg))

    rows = _load_rows(root, args)
    days = sorted({r["day"] for r in rows})
    ctx_by_day = load_probe_contexts(args.code, days, cache_dir=args.cache_dir)
    summary = summarize_route_a_stack(rows, ctx_by_day=ctx_by_day, params=params)
    picks = summary["picks"]
    cf_by_day = {p["day"]: p for p in picks}

    br5 = summarize_b_prime_composite(
        rows,
        ctx_by_day=ctx_by_day,
        params=BPrimeCompositeParams(
            pre_break_br_min=0.35, pre_break_br_p0_only=True, flip_min_ext_open=999.0
        ),
    )
    br5_picks = {p["day"]: p for p in br5["picks"]}

    plans: dict[str, Any] = {}
    if args.plans.is_file():
        plans = json.loads(args.plans.read_text(encoding="utf-8"))
    else:
        replay_plans = build_replay_plans_for_range(rows, ctx_by_day, params=params)
        plans = _plans_payload(replay_plans)

    slices = {label: _slice_net(picks, f, t) for label, f, t in HOLDOUTS}
    br5_slices = {label: _slice_net(br5["picks"], f, t) for label, f, t in HOLDOUTS}

    failures: list[str] = []
    full_net = float(summary["net_total"])
    if abs(full_net - FULL_NET_TARGET) > FULL_NET_TOL:
        failures.append(f"full_net {full_net} not within ±{FULL_NET_TOL} of {FULL_NET_TARGET}")

    if int(summary["extend_days"]) != EXTEND_DAYS_TARGET:
        failures.append(f"extend_days {summary['extend_days']} != {EXTEND_DAYS_TARGET}")

    if int(summary["flip_days"]) != FLIP_DAYS_TARGET:
        failures.append(f"flip_days {summary['flip_days']} != {FLIP_DAYS_TARGET}")

    h1_2026 = slices["H1_2026"]
    br5_h1_2026 = br5_slices["H1_2026"]
    if h1_2026 < br5_h1_2026:
        failures.append(f"H1 2026 regression: stack {h1_2026} < br5 {br5_h1_2026}")
    if abs(h1_2026 - H1_2026_TARGET) > FULL_NET_TOL:
        failures.append(f"H1 2026 {h1_2026} not within ±{FULL_NET_TOL} of {H1_2026_TARGET}")

    uat_stack = slices["UAT_2m"]
    uat_br5 = br5_slices["UAT_2m"]
    if uat_stack <= uat_br5:
        failures.append(f"UAT 2m not better than br5: {uat_stack} vs {uat_br5}")

    decision_mm = _decision_mismatches(cf_by_day, plans)
    if decision_mm:
        failures.append(f"decision_mismatches n={len(decision_mm)}")

    report = {
        "from": args.from_date,
        "to": args.to_date,
        "cf_net_total": full_net,
        "cf_extend_days": summary["extend_days"],
        "cf_flip_days": summary["flip_days"],
        "cf_confirm_veto": summary["confirm_veto"],
        "slices": slices,
        "br5_slices": br5_slices,
        "targets": {
            "full_net": FULL_NET_TARGET,
            "full_net_tol": FULL_NET_TOL,
            "extend_days": EXTEND_DAYS_TARGET,
            "flip_days": FLIP_DAYS_TARGET,
        },
        "decision_mismatches": decision_mm,
        "pass": not failures,
        "failures": failures,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(json.dumps(report, indent=2))
    if failures:
        print("PARITY FAIL:", "; ".join(failures), file=sys.stderr)
        return 1
    print("PARITY PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
