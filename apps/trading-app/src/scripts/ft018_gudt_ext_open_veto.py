"""FT-018b: ext_open early-ft veto counterfactual (route to p0 when ext_open > threshold)."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from reporting.gudt_wash_probe import (
    WashProbeTuning,
    ext_open_atr_for_day,
    load_probe_contexts,
    read_probe_csv,
    summarize_rule,
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _diff_picks(
    base: dict[str, Any],
    veto: dict[str, Any],
) -> list[dict[str, Any]]:
    by_day_b = {p["day"]: p for p in base["picks"]}
    out: list[dict[str, Any]] = []
    for p in veto["picks"]:
        day = p["day"]
        b = by_day_b.get(day)
        if b is None:
            continue
        delta = round(float(p["net"]) - float(b["net"]), 2)
        if p["path"] != b["path"] or abs(delta) > 0.01:
            out.append({
                "day": day,
                "base_path": b["path"],
                "base_net": float(b["net"]),
                "veto_path": p["path"],
                "veto_net": float(p["net"]),
                "delta": delta,
            })
    return sorted(out, key=lambda x: -abs(x["delta"]))


def main(argv: list[str] | None = None) -> int:
    root = _repo_root()
    reports = root / "workspaces" / "gudt-baseline" / "reports"
    parser = argparse.ArgumentParser(description="FT-018b ext_open early-ft veto")
    parser.add_argument("--code", default="TMFR1")
    parser.add_argument("--cache-dir", type=Path, default=root / "tick_cache")
    parser.add_argument("--from", dest="from_date", default="2025-04-01")
    parser.add_argument("--to", dest="to_date", default="2026-06-30")
    parser.add_argument("--threshold", type=float, default=5.0)
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
    ctx_by_day = load_probe_contexts(
        args.code, days, cache_dir=args.cache_dir, tuning=WashProbeTuning()
    )

    base = summarize_rule(
        rows, rule="B_prime", ft_exit="drive_low_struct", ctx_by_day=ctx_by_day
    )
    veto = summarize_rule(
        rows,
        rule="B_prime",
        ft_exit="drive_low_struct",
        ft_ext_open_min=args.threshold,
        ctx_by_day=ctx_by_day,
    )
    delta_total = round(veto["net_total"] - base["net_total"], 2)
    diffs = _diff_picks(base, veto)

    # days where veto would fire (early ft + ext > thr)
    veto_candidates: list[dict[str, Any]] = []
    by_day: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        by_day.setdefault(r["day"], []).append(r)
    for day, dr in by_day.items():
        ctx = ctx_by_day.get(day)
        ext = ext_open_atr_for_day(dr, ctx=ctx)
        ft = next((x for x in dr if x["entry_mode"] == "flow_turn"), None)
        p0 = next((x for x in dr if x["entry_mode"] == "p0" and x["exit_mode"] == "sealed"), None)
        if ft is None or p0 is None or ext is None:
            continue
        if int(ft["entry_ts"]) < int(p0["entry_ts"]) and ext > args.threshold:
            veto_candidates.append({
                "day": day,
                "ext_open": round(ext, 2),
                "ft_net": float(ft["net"]),
                "p0_net": float(p0["net"]),
                "delta_if_veto": round(float(p0["net"]) - float(ft["net"]), 2),
            })

    lines = [
        f"# GUDT B′ ext_open early-ft veto (>{args.threshold}×ATR → p0)",
        f"",
        f"Period: {args.from_date} .. {args.to_date}",
        "",
        "| variant | n | net | mean | WR% |",
        "|---------|--:|----:|-----:|----:|",
        f"| B′ baseline | {base['n']} | {base['net_total']:+.1f} | "
        f"{base['net_mean']:+.1f} | {base['win_rate']:.1f} |",
        f"| B′ + ext_open veto | {veto['n']} | {veto['net_total']:+.1f} | "
        f"{veto['net_mean']:+.1f} | {veto['win_rate']:.1f} |",
        f"| **Δ** | | **{delta_total:+.1f}** | | |",
        "",
        f"Veto candidates (early ft + ext>{args.threshold}): **{len(veto_candidates)}** days",
        "",
        "| day | ext_open | ft+dl | p0+sealed | Δ if veto |",
        "|-----|--------:|------:|----------:|----------:|",
    ]
    for c in sorted(veto_candidates, key=lambda x: -abs(x["delta_if_veto"])):
        lines.append(
            f"| {c['day']} | {c['ext_open']:.1f} | {c['ft_net']:+.1f} | "
            f"{c['p0_net']:+.1f} | {c['delta_if_veto']:+.1f} |"
        )

    if diffs:
        lines.extend([
            "",
            "## Pick changes (applied rule)",
            "",
            "| day | base | base net | veto path | veto net | Δ |",
            "|-----|------|--------:|-----------|--------:|--:|",
        ])
        for d in diffs:
            lines.append(
                f"| {d['day']} | {d['base_path']} | {d['base_net']:+.1f} | "
                f"{d['veto_path']} | {d['veto_net']:+.1f} | {d['delta']:+.1f} |"
            )

    out = args.out_md or reports / (
        f"gudt_ext_open_ft_veto_{args.from_date}_{args.to_date}.md"
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"B' baseline: n={base['n']} net={base['net_total']:+.1f} WR={base['win_rate']:.1f}%")
    print(
        f"B' ext_veto: n={veto['n']} net={veto['net_total']:+.1f} "
        f"WR={veto['win_rate']:.1f}% d={delta_total:+.1f}"
    )
    print(f"veto candidates: {len(veto_candidates)}  pick changes: {len(diffs)}")
    for c in veto_candidates:
        if c["day"] in ("2025-04-23",):
            print(f"  4/23 ext={c['ext_open']} ft={c['ft_net']:+.1f} p0={c['p0_net']:+.1f}")
    print(f"wrote -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
