"""FT-018b: Route A checkpoint + 3m/5m EMA stack extension exit research."""

from __future__ import annotations

import argparse
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any

from reporting.armed_forward_counterfactual import FRICTION_POINTS
from reporting.gudt_route_a_exit import RouteAParams, qualifies_for_extension, simulate_route_a_exit
from reporting.gudt_wash_probe import (
    BPrimeCompositeParams,
    load_probe_contexts,
    read_probe_csv,
    summarize_b_prime_composite,
    _probe_entry_from_row,
    _row_for,
    _simulate_exit,
)

HOLDOUTS = (
    ("2025 H2", "2025-07-01", "2025-12-31"),
    ("2026 H1", "2026-01-01", "2026-05-31"),
    ("2026-06", "2026-06-01", "2026-06-30"),
    ("full", "2025-05-01", "2026-06-30"),
)

EXIT_MODES = (
    ("sealed15", None),
    ("ext_trail1.0", "trail"),
    ("ext_ema3_break", "ema3"),
    ("ext_ema5_break", "ema5"),
    ("ext_ema_either", "ema_either"),
    ("ext_ema_both", "ema_both"),
    ("ext_trail|ema_either", "trail_or_ema_either"),
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _p0_net(entry, ctx, mode: str | None) -> tuple[float, dict[str, Any]]:
    if mode is None:
        sim = _simulate_exit(entry, ctx, "sealed")
    else:
        sim = simulate_route_a_exit(
            entry, ctx, params=RouteAParams(extension_exit=mode)  # type: ignore[arg-type]
        )
    return float(sim["gross_pnl"]) - FRICTION_POINTS, sim


def stack_nets(
    picks: list[dict[str, Any]],
    *,
    by_day: dict[str, list[dict[str, Any]]],
    ctx_by_day: dict[str, Any],
    mode: str | None,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for pick in picks:
        day = pick["day"]
        ctx = ctx_by_day[day]
        dr = by_day[day]
        if pick["path"].startswith("p0"):
            row = _row_for(dr, "p0", "sealed")
            entry = _probe_entry_from_row(row)
            net, sim = _p0_net(entry, ctx, mode)
            ext = qualifies_for_extension(entry, ctx, params=RouteAParams())
            out.append({**pick, "net": net, "exit_reason": sim["exit_reason"], "extended": sim.get("extended", False), "ext_gate": ext})
        else:
            em = pick["path"].split("+")[0]
            ex = "drive_low_struct" if "drive_low" in pick["path"] else "flow_bailout"
            row = _row_for(dr, em if em in ("flow_turn", "reclaim_br", "p0") else "flow_turn", ex)
            if row is None:
                row = _row_for(dr, "flow_turn", ex)
            sim = _simulate_exit(_probe_entry_from_row(row), ctx, ex)
            net = float(sim["gross_pnl"]) - FRICTION_POINTS
            out.append({**pick, "net": net, "exit_reason": sim["exit_reason"], "extended": False, "ext_gate": False})
    return out


def main(argv: list[str] | None = None) -> int:
    root = _repo_root()
    reports = root / "workspaces" / "gudt-baseline" / "reports"
    parser = argparse.ArgumentParser(description="Route A EMA stack extension exit")
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
    by_day: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        by_day[r["day"]].append(r)
    ctx_by_day = load_probe_contexts("TMFR1", sorted(by_day), cache_dir=root / "tick_cache")
    br5 = BPrimeCompositeParams(
        pre_break_br_min=0.35, pre_break_br_p0_only=True, flip_min_ext_open=999.0
    )
    picks = summarize_b_prime_composite(rows, ctx_by_day=ctx_by_day, params=br5)["picks"]

    lines = [
        f"# Route A extension — EMA stack exit {args.from_date}..{args.to_date}",
        "",
        "Checkpoint: 15m sealed gross>0 + ext_open>5 → extend to 60m.",
        "EMA bull stack: close > EMA9 > EMA21 on 3m / 5m bars (1m session_bars).",
        "",
        "## Stack net by exit mode",
        "",
        "| mode | full | Δ vs sealed | H2 | H1 | Jun | ext days |",
        "|------|-----:|------------:|---:|---:|----:|---------:|",
    ]

    base_full = sum(p["net"] for p in stack_nets(picks, by_day=by_day, ctx_by_day=ctx_by_day, mode=None))
    best_label, best_net = "", base_full
    ext_day_rows: list[dict[str, Any]] = []

    for label, mode in EXIT_MODES:
        all_p = stack_nets(picks, by_day=by_day, ctx_by_day=ctx_by_day, mode=mode)
        full = sum(p["net"] for p in all_p)
        ext_n = sum(1 for p in all_p if p.get("extended"))
        parts = []
        for hn, f, t in HOLDOUTS:
            s = sum(p["net"] for p in all_p if f <= p["day"] <= t)
            parts.append(f"{s:+.0f}")
        lines.append(
            f"| {label} | {full:+.0f} | {full - base_full:+.0f} | {parts[0]} | {parts[1]} | {parts[2]} | {ext_n} |"
        )
        if full > best_net:
            best_net, best_label = full, label
        if mode == "ema_either":
            for p in all_p:
                if p.get("extended"):
                    ext_day_rows.append(p)

    lines.extend([
        "",
        f"**Best:** `{best_label}` → net {best_net:+.0f}",
        "",
        "## Extension days (ema_either exit)",
        "",
        "| day | net | exit | path |",
        "|-----|----:|------|------|",
    ])
    for p in sorted(ext_day_rows, key=lambda x: -float(x["net"])):
        lines.append(f"| {p['day']} | {p['net']:+.0f} | {p.get('exit_reason')} | {p['path']} |")

    # head-to-head on extension-gate days only
    lines.extend(["", "## Extension-gate days: trail vs ema_either", "", "| day | sealed | trail | ema_either |", "|-----|-------:|------:|-----------:|"])
    for pick in picks:
        if not pick["path"].startswith("p0"):
            continue
        day = pick["day"]
        ctx = ctx_by_day[day]
        entry = _probe_entry_from_row(_row_for(by_day[day], "p0", "sealed"))
        if not qualifies_for_extension(entry, ctx, params=RouteAParams()):
            continue
        nets = {}
        for label, mode in EXIT_MODES:
            if label in ("ext_ema_both", "ext_trail|ema_either"):
                continue
            nets[label] = _p0_net(entry, ctx, mode)[0]
        lines.append(
            f"| {day} | {nets['sealed15']:+.0f} | {nets['ext_trail1.0']:+.0f} | {nets['ext_ema_either']:+.0f} |"
        )

    out = args.out_md or reports / f"gudt_route_a_ema_{args.from_date}_{args.to_date}.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote -> {out}")
    for label, mode in EXIT_MODES:
        full = sum(p["net"] for p in stack_nets(picks, by_day=by_day, ctx_by_day=ctx_by_day, mode=mode))
        print(f"  {label:22s} {full:+.0f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
