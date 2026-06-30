"""FT-018b: early-ft quick stop-loss oracle → p0 fallback counterfactual."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from reporting.gudt_wash_probe import (
    WashProbeTuning,
    load_probe_contexts,
    read_probe_csv,
    summarize_rule,
    summarize_rule_with_ft_quick_stop_veto,
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _diff_picks(base: dict[str, Any], veto: dict[str, Any]) -> list[dict[str, Any]]:
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
                "ft_hold_sec": p.get("ft_sim_hold_sec"),
            })
    return sorted(out, key=lambda x: -abs(x["delta"]))


def main(argv: list[str] | None = None) -> int:
    root = _repo_root()
    reports = root / "workspaces" / "gudt-baseline" / "reports"
    parser = argparse.ArgumentParser(description="FT-018b ft quick-stop → p0 oracle")
    parser.add_argument("--code", default="TMFR1")
    parser.add_argument("--cache-dir", type=Path, default=root / "tick_cache")
    parser.add_argument("--from", dest="from_date", default="2025-05-01")
    parser.add_argument("--to", dest="to_date", default="2026-06-30")
    parser.add_argument(
        "--from-csv",
        type=Path,
        default=reports / "gudt_wash_probe_merged_202505_202606.csv",
    )
    parser.add_argument(
        "--max-sec",
        type=int,
        default=0,
        help="Quick-stop threshold seconds; 0 = sweep 300/600/900",
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
    thresholds = [args.max_sec] if args.max_sec > 0 else [300, 600, 900]

    sweep: list[dict[str, Any]] = []
    best_t = thresholds[0]
    best_veto = summarize_rule_with_ft_quick_stop_veto(
        rows, ctx_by_day=ctx_by_day, quick_stop_max_sec=best_t
    )
    for t in thresholds:
        v = summarize_rule_with_ft_quick_stop_veto(
            rows, ctx_by_day=ctx_by_day, quick_stop_max_sec=t
        )
        sweep.append({
            "max_sec": t,
            "max_min": t // 60,
            "n": v["n"],
            "veto_days": v["veto_days"],
            "net": v["net_total"],
            "delta": round(v["net_total"] - base["net_total"], 2),
            "wr": v["win_rate"],
            "picks": v["picks"],
        })
        if v["net_total"] > best_veto["net_total"]:
            best_t = t
            best_veto = v

    diffs = _diff_picks(base, best_veto)
    delta_total = round(best_veto["net_total"] - base["net_total"], 2)

    lines = [
        "# GUDT B′ quick-stop oracle (early ft → p0 if dl stop before break)",
        "",
        f"Period: {args.from_date} .. {args.to_date}",
        "",
        "Rule: early `flow_turn+dl` re-simulated; if `stop_loss` within T sec "
        "and entry before `first_break_ts` → `p0+sealed`.",
        "",
        f"| B′ baseline | n={base['n']} | net={base['net_total']:+.1f} | WR={base['win_rate']:.1f}% |",
        "",
        "## Threshold sweep",
        "",
        "| T (min) | veto days | net | Δ vs B′ | WR% |",
        "|--------:|----------:|----:|--------:|----:|",
    ]
    for s in sweep:
        lines.append(
            f"| {s['max_min']} | {s['veto_days']} | {s['net']:+.1f} | {s['delta']:+.1f} | {s['wr']:.1f} |"
        )

    lines.extend([
        "",
        f"**Best T = {best_t // 60} min** → net {best_veto['net_total']:+.1f} (Δ {delta_total:+.1f})",
        "",
        "## Pick changes (best T)",
        "",
        "| day | base net | veto net | Δ | ft hold(s) |",
        "|-----|--------:|--------:|--:|-----------:|",
    ])
    for d in diffs:
        hold = d.get("ft_hold_sec", "—")
        lines.append(
            f"| {d['day']} | {d['base_net']:+.1f} | {d['veto_net']:+.1f} | "
            f"{d['delta']:+.1f} | {hold} |"
        )

    out = args.out_md or reports / f"gudt_quick_stop_veto_{args.from_date}_{args.to_date}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"B' baseline: n={base['n']} net={base['net_total']:+.1f} WR={base['win_rate']:.1f}%")
    for s in sweep:
        print(
            f"  T={s['max_min']}min: veto={s['veto_days']} net={s['net']:+.1f} "
            f"d={s['delta']:+.1f} WR={s['wr']:.1f}%"
        )
    print(f"best T={best_t // 60}min  pick_changes={len(diffs)}")
    print(f"wrote -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
