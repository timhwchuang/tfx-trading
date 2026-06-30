"""FT-018b: exit counterfactuals — conditional break/dl + fixed 9:15/9:30 entry."""

from __future__ import annotations

import argparse
import datetime as dt
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any

from reporting.armed_forward_counterfactual import FRICTION_POINTS
from reporting.gap_drive_continuation_counterfactual import _index_at_close_time
from reporting.gudt_wash_probe import (
    ProbeEntry,
    WashProbeTuning,
    WASH_STOP_BUFFER,
    _simulate_exit,
    load_probe_contexts,
    read_probe_csv,
    rule_pick_for_day,
    simulate_atr_trail_skew_exit,
    simulate_conditional_break_dl_exit,
    summarize_rule,
)

FIXED_ENTRY_TIMES = (dt.time(9, 15), dt.time(9, 30))


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _agg(nets: list[float]) -> dict[str, Any]:
    if not nets:
        return {"n": 0, "net_total": 0.0, "net_mean": 0.0, "win_rate": 0.0}
    return {
        "n": len(nets),
        "net_total": round(sum(nets), 2),
        "net_mean": round(statistics.mean(nets), 2),
        "win_rate": round(100.0 * sum(1 for n in nets if n > 0) / len(nets), 1),
    }


def _ft_entry_from_row(row: dict[str, Any]) -> ProbeEntry:
    return ProbeEntry(
        entry_mode="flow_turn",
        entry_ts=int(row["entry_ts"]),
        entry_price=float(row["entry_px"]),
        br_at_entry=float(row.get("br_at_entry") or 0),
        delta_br_at_entry=float(row.get("delta_br_at_entry") or 0),
        sell_ratio_at_entry=float(row.get("sell_ratio_at_entry") or 0),
        wash_depth=float(row.get("wash_depth") or 0),
        dip_below_dh=bool(row.get("dip_below_dh")),
    )


def _row_for(day_rows: list[dict[str, Any]], em: str, ex: str) -> dict[str, Any] | None:
    return next((r for r in day_rows if r["entry_mode"] == em and r["exit_mode"] == ex), None)


def _net(sim: dict[str, Any], friction: float = FRICTION_POINTS) -> float:
    return round(float(sim["gross_pnl"]) - friction, 2)


def summarize_bprime_conditional_ft(
    rows: list[dict[str, Any]],
    *,
    ctx_by_day: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    """B′ with ft leg: dl vs conditional-break/dl (p0 path unchanged)."""
    by_day: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        by_day[r["day"]].append(r)

    dl_nets: list[float] = []
    cond_nets: list[float] = []
    picks: list[dict[str, Any]] = []

    for day_rows in by_day.values():
        day = day_rows[0]["day"]
        base = rule_pick_for_day(day_rows, rule="B_prime", ft_exit="drive_low_struct")
        if base is None:
            continue
        ctx = ctx_by_day.get(day)
        if base["path"].startswith("flow_turn") and ctx is not None:
            ft_row = _row_for(day_rows, "flow_turn", "drive_low_struct")
            if ft_row is None:
                continue
            entry = _ft_entry_from_row(ft_row)
            sim_dl = _simulate_exit(entry, ctx, "drive_low_struct")
            sim_cond = simulate_conditional_break_dl_exit(
                entry_price=entry.entry_price,
                entry_ts=entry.entry_ts,
                atr=ctx.atr,
                ticks=ctx.ticks,
                drive_low=ctx.drive_low,
                first_break_ts=ctx.first_break_ts,
            )
            net_dl = _net(sim_dl)
            net_cond = _net(sim_cond)
            dl_nets.append(net_dl)
            cond_nets.append(net_cond)
            picks.append({
                "day": day,
                "path": base["path"],
                "dl_net": net_dl,
                "cond_net": net_cond,
                "delta": round(net_cond - net_dl, 2),
                "dl_exit": sim_dl["exit_reason"],
                "cond_exit": sim_cond["exit_reason"],
            })
        else:
            net = float(base["net"])
            dl_nets.append(net)
            cond_nets.append(net)

    return {
        "drive_low_struct": _agg(dl_nets),
        "conditional_break_dl": _agg(cond_nets),
        "delta_total": round(sum(cond_nets) - sum(dl_nets), 2),
        "picks": picks,
    }


def _fixed_entry_px_ts(ctx: Any, close_t: dt.time) -> tuple[float, int] | None:
    bars = ctx.session_bars
    if not bars:
        return None
    idx = _index_at_close_time(bars, close_t)
    if idx is None:
        return None
    bar = bars[idx]
    return float(bar.Close), int(bar.ts.timestamp())


def summarize_fixed_time_entries(
    days: list[str],
    *,
    ctx_by_day: dict[str, Any],
    close_t: dt.time,
    friction: float = FRICTION_POINTS,
) -> dict[str, Any]:
    """GUDT qualifying days: enter at 1m bar close (9:15 or 9:30)."""
    exits = ("sealed", "drive_low_struct", "conditional_break_dl")
    nets: dict[str, list[float]] = {ex: [] for ex in exits}
    rows_out: list[dict[str, Any]] = []

    for day in days:
        ctx = ctx_by_day.get(day)
        if ctx is None:
            continue
        px_ts = _fixed_entry_px_ts(ctx, close_t)
        if px_ts is None:
            continue
        entry_px, entry_ts = px_ts

        sim_sealed_r = simulate_atr_trail_skew_exit(
            direction="Long",
            entry_price=entry_px,
            entry_ts=entry_ts,
            atr=ctx.atr,
            ticks=ctx.ticks,
            hard_stop_atr_k=1.25,
            be_trigger_atr_k=0.75,
            trail_arm_atr_k=2.0,
            trail_dist_atr_k=0.6,
            hard_tp_atr_k=3.0,
            max_hold_sec=900,
        )
        sim_cond_r = simulate_conditional_break_dl_exit(
            entry_price=entry_px,
            entry_ts=entry_ts,
            atr=ctx.atr,
            ticks=ctx.ticks,
            drive_low=ctx.drive_low,
            first_break_ts=ctx.first_break_ts,
        )
        sim_dl_legacy = simulate_atr_trail_skew_exit(
            direction="Long",
            entry_price=entry_px,
            entry_ts=entry_ts,
            atr=ctx.atr,
            ticks=ctx.ticks,
            hard_stop_atr_k=1.25,
            be_trigger_atr_k=None,
            trail_arm_atr_k=2.0,
            trail_dist_atr_k=0.6,
            hard_tp_atr_k=3.0,
            max_hold_sec=900,
            initial_stop_price=ctx.drive_low - WASH_STOP_BUFFER,
        )

        n_sealed = round(float(sim_sealed_r["gross_pnl"]) - friction, 2)
        n_dl = round(float(sim_dl_legacy["gross_pnl"]) - friction, 2)
        n_cond = round(float(sim_cond_r["gross_pnl"]) - friction, 2)
        nets["sealed"].append(n_sealed)
        nets["drive_low_struct"].append(n_dl)
        nets["conditional_break_dl"].append(n_cond)
        rows_out.append({
            "day": day,
            "entry_t": close_t.isoformat(),
            "entry_px": entry_px,
            "sealed": n_sealed,
            "dl": n_dl,
            "cond_dl": n_cond,
        })

    return {
        "entry_time": close_t.isoformat(),
        **{ex: _agg(nets[ex]) for ex in exits},
        "rows": rows_out,
    }


def main(argv: list[str] | None = None) -> int:
    root = _repo_root()
    reports = root / "workspaces" / "gudt-baseline" / "reports"
    parser = argparse.ArgumentParser(description="FT-018b exit / fixed-entry counterfactuals")
    parser.add_argument("--code", default="TMFR1")
    parser.add_argument("--cache-dir", type=Path, default=root / "tick_cache")
    parser.add_argument("--from", dest="from_date", default="2025-05-01")
    parser.add_argument("--to", dest="to_date", default="2026-06-30")
    parser.add_argument(
        "--from-csv",
        type=Path,
        default=reports / "gudt_wash_probe_merged_202505_202606.csv",
    )
    parser.add_argument("--out-md", type=Path, default=None)
    args = parser.parse_args(argv)

    rows = read_probe_csv(args.from_csv)
    rows = [r for r in rows if args.from_date <= r["day"] <= args.to_date]
    days = sorted({r["day"] for r in rows})
    tuning = WashProbeTuning()
    ctx_by_day = load_probe_contexts(args.code, days, cache_dir=args.cache_dir, tuning=tuning)

    bprime = summarize_rule(rows, rule="B_prime", ft_exit="drive_low_struct")
    cond = summarize_bprime_conditional_ft(rows, ctx_by_day=ctx_by_day)

    fixed: dict[str, dict[str, Any]] = {}
    for t in FIXED_ENTRY_TIMES:
        fixed[t.isoformat()] = summarize_fixed_time_entries(
            days, ctx_by_day=ctx_by_day, close_t=t
        )

    # flow_turn baseline WR for comparison
    ft_dl_rows = [r for r in rows if r["entry_mode"] == "flow_turn" and r["exit_mode"] == "drive_low_struct"]
    ft_dl_nets = [float(r["net"]) for r in ft_dl_rows]

    lines = [
        f"# GUDT exit counterfactual {args.from_date}..{args.to_date}",
        "",
        "## B′ — conditional break/dl (ft leg only re-simulated)",
        "",
        f"| variant | n | net | mean | WR% |",
        f"|---------|--:|----:|-----:|----:|",
        f"| B′ + drive_low_struct (baseline) | {bprime['n']} | {bprime['net_total']:+.1f} | "
        f"{bprime['net_mean']:+.1f} | {bprime['win_rate']:.1f} |",
        f"| B′ + conditional break/dl | {cond['conditional_break_dl']['n']} | "
        f"{cond['conditional_break_dl']['net_total']:+.1f} | "
        f"{cond['conditional_break_dl']['net_mean']:+.1f} | "
        f"{cond['conditional_break_dl']['win_rate']:.1f} |",
        f"| Δ | | **{cond['delta_total']:+.1f}** | | |",
        "",
        "### ft days where conditional dl differs (|Δ|≥10)",
        "",
        "| day | dl | cond | Δ | dl exit | cond exit |",
        "|-----|---:|-----:|--:|---------|-----------|",
    ]
    for p in sorted(cond["picks"], key=lambda x: -abs(x["delta"])):
        if abs(p["delta"]) < 10:
            continue
        lines.append(
            f"| {p['day']} | {p['dl_net']:+.1f} | {p['cond_net']:+.1f} | {p['delta']:+.1f} | "
            f"{p['dl_exit']} | {p['cond_exit']} |"
        )

    lines.extend([
        "",
        "## Fixed-time entry (all GUDT qualifying days)",
        "",
        f"Reference: flow_turn+dl matrix n={len(ft_dl_nets)} WR={_agg(ft_dl_nets)['win_rate']:.1f}% "
        f"net={_agg(ft_dl_nets)['net_total']:+.1f}",
        "",
        "| entry | exit | n | net | mean | WR% |",
        "|-------|------|--:|----:|-----:|----:|",
    ])
    for t in FIXED_ENTRY_TIMES:
        s = fixed[t.isoformat()]
        for ex in ("sealed", "drive_low_struct", "conditional_break_dl"):
            a = s[ex]
            lines.append(
                f"| {t.strftime('%H:%M')} | {ex} | {a['n']} | {a['net_total']:+.1f} | "
                f"{a['net_mean']:+.1f} | {a['win_rate']:.1f} |"
            )

    out = args.out_md or reports / f"gudt_exit_counterfactual_{args.from_date}_{args.to_date}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"B' dl:      n={bprime['n']} net={bprime['net_total']:+.1f} WR={bprime['win_rate']:.1f}%")
    c = cond["conditional_break_dl"]
    print(f"B' cond_dl: n={c['n']} net={c['net_total']:+.1f} WR={c['win_rate']:.1f}% d={cond['delta_total']:+.1f}")
    for t in FIXED_ENTRY_TIMES:
        s = fixed[t.isoformat()]
        print(f"\nfixed {t.strftime('%H:%M')}:")
        for ex in ("sealed", "drive_low_struct", "conditional_break_dl"):
            a = s[ex]
            print(f"  {ex}: n={a['n']} net={a['net_total']:+.1f} WR={a['win_rate']:.1f}%")
    print(f"wrote -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
