"""FT-018b: B′ composite — long + distribution short second leg."""

from __future__ import annotations

import argparse
import datetime as dt
from pathlib import Path

from reporting.gudt_wash_probe import (
    BPrimeCompositeParams,
    WashProbeTuning,
    build_session_bars_by_day,
    format_b_prime_composite_md,
    format_b_prime_composite_spec_md,
    load_probe_contexts,
    read_probe_csv,
    run_probe_range,
    summarize_b_prime_composite,
    summarize_rule,
    write_probe_csv,
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def main(argv: list[str] | None = None) -> int:
    root = _repo_root()
    reports = root / "workspaces" / "gudt-baseline" / "reports"
    parser = argparse.ArgumentParser(description="FT-018b B′ composite (long + dist short)")
    parser.add_argument("--code", default="TMFR1")
    parser.add_argument("--cache-dir", type=Path, default=root / "tick_cache")
    parser.add_argument("--from", dest="from_date", default="2025-05-01")
    parser.add_argument("--to", dest="to_date", default="2026-06-30")
    parser.add_argument(
        "--preset",
        choices=("v4", "v5", "dist_short_only", "flip_only", "chase_v4"),
        default="v5",
    )
    parser.add_argument("--from-csv", type=Path, default=None, help="Reuse probe CSV (skip tick replay)")
    parser.add_argument("--out-md", type=Path, default=None)
    parser.add_argument("--out-spec", type=Path, default=None)
    parser.add_argument("--out-csv", type=Path, default=None)
    args = parser.parse_args(argv)

    presets: dict[str, BPrimeCompositeParams] = {
        "v4": BPrimeCompositeParams(pre_break_br_min=0.35),
        "v5": BPrimeCompositeParams(
            pre_break_br_min=0.35,
            pre_break_br_p0_only=True,
            flip_min_ext_open=5.0,
        ),
        "flip_only": BPrimeCompositeParams(pre_break_br_min=None),
        "chase_v4": BPrimeCompositeParams(
            pre_break_br_min=0.35,
            p0_ext_open_max=5.0,
            p0_sess_vwap_dist_max=3.0,
        ),
        "dist_short_only": BPrimeCompositeParams(
            pre_break_br_min=None,
            short_only=True,
        ),
    }
    params = presets[args.preset]

    tuning = WashProbeTuning()
    if args.from_csv is not None:
        rows = read_probe_csv(args.from_csv)
        rows = [r for r in rows if args.from_date <= r["day"] <= args.to_date]
    else:
        pad_from = (dt.date.fromisoformat(args.from_date) - dt.timedelta(days=45)).isoformat()
        rows = run_probe_range(
            code=args.code,
            from_date=pad_from,
            to_date=args.to_date,
            cache_dir=args.cache_dir,
            tuning=tuning,
        )
        rows = [r for r in rows if args.from_date <= r["day"] <= args.to_date]
    label = f"{args.from_date}_{args.to_date}"

    if args.out_csv:
        write_probe_csv(rows, args.out_csv)

    days = sorted({r["day"] for r in rows})
    ctx_by_day = load_probe_contexts(
        args.code, days, cache_dir=args.cache_dir, tuning=tuning
    )
    bars_by_day = None
    if params.p0_ext_open_max is not None or params.p0_sess_vwap_dist_max is not None:
        bars_by_day = build_session_bars_by_day(
            args.code, days, cache_dir=args.cache_dir, ctx_by_day=ctx_by_day
        )

    bprime = summarize_rule(rows, rule="B_prime", ft_exit="drive_low_struct")
    composite = summarize_b_prime_composite(
        rows,
        ctx_by_day=ctx_by_day,
        params=params,
        session_bars_by_day=bars_by_day,
    )

    spec_path = args.out_spec or reports / "gudt_bprime_composite_SPEC.md"
    spec_path.write_text(format_b_prime_composite_spec_md(), encoding="utf-8")

    md = format_b_prime_composite_md(
        composite,
        title=f"GUDT B′ composite ({args.preset}) {args.from_date}..{args.to_date}",
        compare_net=bprime["net_total"],
    )
    out_md = args.out_md or reports / f"gudt_bprime_composite_{args.preset}_{label}.md"
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_md.write_text(md, encoding="utf-8")

    print(f"preset={args.preset}", flush=True)
    print(f"  B' alone:  n={bprime['n']} net={bprime['net_total']:+.1f}", flush=True)
    print(
        f"  composite: n={composite['n']} skip={composite['skipped_days']} "
        f"flip={composite['flip_days']} net={composite['net_total']:+.1f} "
        f"d={composite['net_total'] - bprime['net_total']:+.1f}",
        flush=True,
    )
    print(f"wrote spec -> {spec_path}", flush=True)
    print(f"wrote report -> {out_md}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
