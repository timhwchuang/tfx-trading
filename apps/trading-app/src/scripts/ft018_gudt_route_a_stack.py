"""FT-018b Route A UAT stack — B′+br5 + 5m EMA extension + distribution confirm flip."""

from __future__ import annotations

import argparse
import datetime as dt
from pathlib import Path

from reporting.gudt_route_a_stack import RouteAStackParams, summarize_route_a_stack
from reporting.gudt_wash_probe import (
    WashProbeTuning,
    load_probe_contexts,
    read_probe_csv,
    run_probe_range,
    summarize_b_prime_composite,
    BPrimeCompositeParams,
)

HOLDOUTS = (
    ("2025 H2", "2025-07-01", "2025-12-31"),
    ("2026 H1", "2026-01-01", "2026-05-31"),
    ("UAT 2m", "2026-05-01", "2026-06-30"),
    ("full", "2025-05-01", "2026-06-30"),
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _slice_net(picks: list[dict], f: str, t: str) -> float:
    return round(sum(float(p["net"]) for p in picks if f <= p["day"] <= t), 2)


def main(argv: list[str] | None = None) -> int:
    root = _repo_root()
    reports = root / "workspaces" / "gudt-baseline" / "reports"
    parser = argparse.ArgumentParser(description="FT-018b Route A UAT stack")
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

    if args.from_csv and args.from_csv.exists():
        rows = read_probe_csv(args.from_csv)
        rows = [r for r in rows if args.from_date <= r["day"] <= args.to_date]
    else:
        pad_from = (dt.date.fromisoformat(args.from_date) - dt.timedelta(days=45)).isoformat()
        rows = run_probe_range(
            code=args.code,
            from_date=pad_from,
            to_date=args.to_date,
            cache_dir=args.cache_dir,
            tuning=WashProbeTuning(),
        )
        rows = [r for r in rows if args.from_date <= r["day"] <= args.to_date]

    days = sorted({r["day"] for r in rows})
    ctx_by_day = load_probe_contexts(args.code, days, cache_dir=args.cache_dir)
    params = RouteAStackParams()
    summary = summarize_route_a_stack(rows, ctx_by_day=ctx_by_day, params=params)
    picks = summary["picks"]

    br5 = summarize_b_prime_composite(
        rows,
        ctx_by_day=ctx_by_day,
        params=BPrimeCompositeParams(
            pre_break_br_min=0.35, pre_break_br_p0_only=True, flip_min_ext_open=999.0
        ),
    )

    lines = [
        f"# FT-018b Route A UAT stack — {args.from_date}..{args.to_date}",
        "",
        "## Spec (two independent legs)",
        "",
        "### Leg 1 — Route A long (p0 only)",
        "- Router: B′ + br5 p0-only veto",
        "- Checkpoint: 15m sealed gross>0 + ext_open>5 → extend 60m",
        "- Extension exit: **5m EMA9>EMA21 break** (fallback trail/stop)",
        "- ft path: drive_low_struct unchanged",
        "",
        "### Leg 2 — Distribution short (overlay)",
        "- Gate: ext_open > 5",
        "- Signal @ P0+10m: px < p0_entry AND BR < 0.42",
        "- **Confirm @ P0+12m**: dump_atr ≤ −0.65 AND −0.35 ≤ slope2 ≤ 0",
        "- Short stop: drive_high + 2, hold 60m",
        "",
        "## Holdout / UAT ledger",
        "",
        "| period | B′+br5 | Route A stack | Δ | flips | extend |",
        "|--------|-------:|--------------:|--:|------:|-------:|",
    ]
    for label, f, t in HOLDOUTS:
        if t < args.from_date or f > args.to_date:
            continue
        b = _slice_net(br5["picks"], f, t)
        s = _slice_net(picks, f, t)
        fl = sum(1 for p in picks if f <= p["day"] <= t and p.get("hedge") == "flip")
        ex = sum(1 for p in picks if f <= p["day"] <= t and p.get("route_a_extended"))
        lines.append(f"| {label} | {b:+.0f} | {s:+.0f} | {s - b:+.0f} | {fl} | {ex} |")

    lines.extend([
        "",
        f"**Full period:** net **{summary['net_total']:+.1f}** · "
        f"flip={summary['flip_days']} · confirm_veto={summary['confirm_veto']} · "
        f"extend={summary['extend_days']}",
        "",
        "## Day ledger",
        "",
        "| day | path | long | short | net | hedge | confirm | route_a |",
        "|-----|------|-----:|------:|----:|-------|---------|---------|",
    ])
    for p in sorted(picks, key=lambda x: x["day"]):
        lines.append(
            f"| {p['day']} | {p['path']} | {p.get('long_net', p['net'])} | "
            f"{p.get('short_net', 0)} | {p['net']} | {p.get('hedge', '—')} | "
            f"{p.get('dist_confirm', '—')} | "
            f"{'ext' if p.get('route_a_extended') else '—'} |"
        )

    out = args.out_md or reports / f"gudt_route_a_uat_stack_{args.from_date}_{args.to_date}.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote -> {out}")
    print(f"net={summary['net_total']:+.1f} flip={summary['flip_days']} extend={summary['extend_days']}")
    uat = _slice_net(picks, "2026-05-01", "2026-06-30")
    print(f"UAT 2026-05..06: {uat:+.0f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
