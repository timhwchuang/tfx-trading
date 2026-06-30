"""FT-018b: Rule B / B' / D matrix backtest."""

from __future__ import annotations

import argparse
import datetime as dt
from pathlib import Path

from reporting.gudt_wash_probe import (
    WashProbeTuning,
    format_bprime_hedge_detail_md,
    format_rules_matrix_md,
    load_probe_contexts,
    run_probe_range,
    summarize_by_entry_exit,
    summarize_rule,
    summarize_rule_with_distribution_hedge,
    summarize_rules_matrix,
    write_probe_csv,
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def main(argv: list[str] | None = None) -> int:
    root = _repo_root()
    reports = root / "workspaces" / "gudt-baseline" / "reports"
    parser = argparse.ArgumentParser(description="FT-018b GUDT rule matrix (B, B', D)")
    parser.add_argument("--code", default="TMFR1")
    parser.add_argument("--cache-dir", type=Path, default=root / "tick_cache")
    parser.add_argument("--from", dest="from_date", default="2025-05-01")
    parser.add_argument("--to", dest="to_date", default="2026-05-31")
    parser.add_argument("--out-md", type=Path, default=None)
    parser.add_argument("--out-csv", type=Path, default=None)
    args = parser.parse_args(argv)

    pad_from = (dt.date.fromisoformat(args.from_date) - dt.timedelta(days=45)).isoformat()
    tuning = WashProbeTuning()
    rows = run_probe_range(
        code=args.code,
        from_date=pad_from,
        to_date=args.to_date,
        cache_dir=args.cache_dir,
        tuning=tuning,
    )
    rows = [r for r in rows if args.from_date <= r["day"] <= args.to_date]
    label = f"{args.from_date}_{args.to_date}"

    rows = [r for r in rows if args.from_date <= r["day"] <= args.to_date]
    label = f"{args.from_date}_{args.to_date}"

    if args.out_csv:
        write_probe_csv(rows, args.out_csv)

    days = sorted({r["day"] for r in rows})
    ctx_by_day = load_probe_contexts(
        args.code,
        days,
        cache_dir=args.cache_dir,
        tuning=tuning,
    )

    matrix = summarize_rules_matrix(
        rows,
        from_date=args.from_date,
        to_date=args.to_date,
        ctx_by_day=ctx_by_day,
    )
    ref = summarize_by_entry_exit(rows)
    md = format_rules_matrix_md(
        matrix,
        title=f"GUDT Rule Matrix {args.from_date}..{args.to_date}",
    )
    md += "## Entry×exit reference\n\n"
    for key, v in sorted(ref.items()):
        md += f"- `{key}`: n={v['n']} net_total={v['net_total']}\n"
    md += "\n"

    hedge_summary = summarize_rule_with_distribution_hedge(
        rows,
        rule="B_prime",
        ft_exit="drive_low_struct",
        ctx_by_day=ctx_by_day,
    )
    bprime = summarize_rule(rows, rule="B_prime", ft_exit="drive_low_struct")
    hedge_md = format_bprime_hedge_detail_md(
        hedge_summary,
        title=f"GUDT B′ + hedge_distribution_short {args.from_date}..{args.to_date}",
        compare_net=bprime["net_total"],
    )

    out_md = args.out_md or reports / f"gudt_wash_rule_matrix_{label}.md"
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_md.write_text(md, encoding="utf-8")

    hedge_md_path = reports / f"gudt_bprime_hedge_{label}.md"
    hedge_md_path.write_text(hedge_md, encoding="utf-8")

    print(f"wrote matrix -> {out_md}", flush=True)
    print(f"wrote hedge  -> {hedge_md_path}", flush=True)
    for r in matrix:
        if r["period"] in ("ALL", "H2_holdout", "H1_2026"):
            hedge_tag = f" flip={r.get('hedge_days', 0)}" if r.get("hedge") else ""
            delta = ""
            if r.get("delta_vs_bprime_dl") is not None:
                delta = f" dB'={r['delta_vs_bprime_dl']:+.0f}"
            print(
                f"  {r['period']:12s} {r['spec']:18s} n={r['n']:2d} "
                f"net={r['net_total']:+7.1f}{delta} WR={r['win_rate']:4.1f}% "
                f"veto={r['veto_days']}{hedge_tag}",
                flush=True,
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
