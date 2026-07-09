"""FT-018b: GUDT wash probe CLI — entry×exit matrix, CSV + panel MD."""

from __future__ import annotations

import argparse
from pathlib import Path

from reporting.gudt_wash_probe import (
    PANEL_DAYS_DEFAULT,
    WashProbeTuning,
    format_panel_md,
    probe_day_rows,
    run_probe_range,
    summarize_by_entry_exit,
    write_probe_csv,
)
from storage.tick_loader import resolve_cli_tick_cache_dates


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def main(argv: list[str] | None = None) -> int:
    root = _repo_root()
    reports = root / "workspaces" / "gudt-baseline" / "reports"
    parser = argparse.ArgumentParser(description="FT-018b GUDT wash probe")
    parser.add_argument("--code", default="TMFR1")
    parser.add_argument("--cache-dir", type=Path, default=root / "tick_cache")
    parser.add_argument("--from", dest="from_date", default="2025-12-01")
    parser.add_argument("--to", dest="to_date", default="2026-05-31")
    parser.add_argument("--day", default="", help="Single day YYYY-MM-DD")
    parser.add_argument("--panel", action="store_true", help="Panel MD for anchor days")
    parser.add_argument(
        "--days",
        default=",".join(PANEL_DAYS_DEFAULT),
        help="Comma-separated panel days (with --panel)",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output CSV or MD path",
    )
    args = parser.parse_args(argv)

    tuning = WashProbeTuning()
    cache_dir = args.cache_dir

    if args.day:
        import datetime as dt

        day = dt.date.fromisoformat(args.day)
        dates = resolve_cli_tick_cache_dates(
            code=args.code,
            cache_dir=cache_dir,
            from_date=args.from_date,
            to_date=args.to_date,
            explicit=None,
            from_cache=True,
        )
        rows = probe_day_rows(args.code, day, cache_dir=cache_dir, sorted_dates=dates, tuning=tuning)
        out = args.out or reports / f"gudt_wash_probe_{args.day}.csv"
        write_probe_csv(rows, out)
        print(f"wrote {len(rows)} rows -> {out}", flush=True)
        return 0

    if args.panel:
        import datetime as dt

        panel_days = tuple(d.strip() for d in args.days.split(",") if d.strip())
        pad_from = (dt.date.fromisoformat(min(panel_days)) - dt.timedelta(days=45)).isoformat()
        rows = run_probe_range(
            code=args.code,
            from_date=pad_from,
            to_date=max(panel_days),
            cache_dir=cache_dir,
            tuning=tuning,
        )
        panel_rows = [r for r in rows if r["day"] in panel_days]
        md = format_panel_md(panel_rows, panel_days=panel_days)
        out = args.out or reports / "gudt_wash_probe_panel.md"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(md, encoding="utf-8")
        print(f"panel {len(panel_days)} days -> {out}", flush=True)
        return 0

    rows = run_probe_range(
        code=args.code,
        from_date=args.from_date,
        to_date=args.to_date,
        cache_dir=cache_dir,
        tuning=tuning,
    )
    out = args.out or reports / f"gudt_wash_probe_{args.from_date.replace('-', '')}_{args.to_date.replace('-', '')}.csv"
    write_probe_csv(rows, out)
    summary = summarize_by_entry_exit(rows)
    p0_sealed = summary.get("p0+sealed", {})
    print(
        f"wrote {len(rows)} rows -> {out} · p0+sealed n={p0_sealed.get('n')} "
        f"net_total={p0_sealed.get('net_total')}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
