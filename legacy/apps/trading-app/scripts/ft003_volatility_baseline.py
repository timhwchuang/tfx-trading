"""FT-003 Phase 3.6: emit market scale baseline from tick_cache."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

import yaml

from reporting.volatility_baseline import (
    build_baseline_payload,
    compute_kbar_month_stats,
    compute_tick_month_stats,
    inject_markdown_section,
    preserve_markdown_section,
    render_markdown,
)
from storage.tick_loader import resolve_cli_tick_cache_dates


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _load_strategy_config(config_path: Path) -> dict[str, float]:
    data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    strategy = data.get("strategy") or {}
    return {
        "hard_stop_points": float(strategy.get("hard_stop_points", 6)),
        "trail_points": float(strategy.get("trail_points", 8)),
        "fixed_tp_points": float(strategy.get("fixed_tp_points", 20)),
        "min_atr_threshold": float(strategy.get("min_atr_threshold", 25)),
        "momentum_vol_1s": float(strategy.get("momentum_vol_1s", 150)),
        "exhaustion_vol": float(strategy.get("exhaustion_vol", 15)),
    }


def _kbar_paths(cache_dir: Path, code: str, dates: list[dt.date]) -> list[Path]:
    out: list[Path] = []
    for d in dates:
        p = cache_dir / f"{code}_kbars_{d.isoformat()}.csv"
        if p.is_file():
            out.append(p)
    return out


def _tick_paths(cache_dir: Path, code: str, dates: list[dt.date]) -> list[Path]:
    out: list[Path] = []
    for d in dates:
        p = cache_dir / f"{code}_{d.isoformat()}.csv"
        if p.is_file():
            out.append(p)
    return out


def run(
    *,
    code: str,
    cache_dir: Path,
    from_date: str,
    to_date: str,
    config_path: Path,
    include_ticks: bool,
) -> dict:
    dates = resolve_cli_tick_cache_dates(
        explicit=None,
        from_cache=True,
        code=code,
        cache_dir=cache_dir,
        from_date=from_date,
        to_date=to_date,
    )
    if not dates:
        raise SystemExit(f"no kbars/tick dates in cache for {from_date}..{to_date}")

    cfg = _load_strategy_config(config_path)
    kbar_paths = _kbar_paths(cache_dir, code, dates)
    if not kbar_paths:
        raise SystemExit("no kbar files found")

    kbar_months = compute_kbar_month_stats(
        kbar_paths,
        stop_points=cfg["hard_stop_points"],
        trail_points=cfg["trail_points"],
        tp_points=cfg["fixed_tp_points"],
    )
    tick_months = None
    if include_ticks:
        tick_paths = _tick_paths(cache_dir, code, dates)
        tick_months = compute_tick_month_stats(tick_paths)

    return build_baseline_payload(
        code=code,
        from_date=from_date,
        to_date=to_date,
        config=cfg,
        kbar_months=kbar_months,
        tick_months=tick_months,
    )


def main(argv: list[str] | None = None) -> int:
    root = _repo_root()
    parser = argparse.ArgumentParser(description="FT-003 Phase 3.6 volatility baseline")
    parser.add_argument("--code", default="TMFR1")
    parser.add_argument("--cache-dir", type=Path, default=root / "tick_cache")
    parser.add_argument("--from-date", default="2026-01-01")
    parser.add_argument("--to-date", default="2026-05-31")
    parser.add_argument(
        "--config",
        type=Path,
        default=root / "apps" / "trading-app" / "config" / "config.yaml",
    )
    parser.add_argument(
        "--json-out",
        type=Path,
        default=root / "workspaces" / "reports" / "volatility_baseline.json",
    )
    parser.add_argument("--markdown-out", type=Path, default=None)
    parser.add_argument("--ticks", action="store_true", help="include P1 tick vol/spread")
    args = parser.parse_args(argv)

    payload = run(
        code=args.code,
        cache_dir=args.cache_dir,
        from_date=args.from_date,
        to_date=args.to_date,
        config_path=args.config,
        include_ticks=args.ticks,
    )

    args.json_out.parent.mkdir(parents=True, exist_ok=True)
    args.json_out.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {args.json_out}")

    if args.markdown_out:
        md = render_markdown(payload, generated=dt.date.today().isoformat())
        if args.markdown_out.is_file():
            prior = args.markdown_out.read_text(encoding="utf-8")
            preserved_d = preserve_markdown_section(prior, "D. 出場診斷（P0 — baseline valid）")
            if preserved_d:
                md = inject_markdown_section(md, "D. 出場診斷（P0 — baseline valid）", preserved_d)
            # Preserve trader interpretation under section A if present
            if "**解讀**（交易員填寫）：" in prior:
                a_interp_start = prior.index("**解讀**（交易員填寫）：")
                a_interp_end = prior.find("\n---\n", a_interp_start)
                if a_interp_end > a_interp_start:
                    interp_block = prior[a_interp_start:a_interp_end].strip()
                    if len(interp_block) > len("**解讀**（交易員填寫）："):
                        a_header = "## A. 月度波動（P0 — kbars）"
                        a_block = prior[prior.index(a_header) : a_interp_end].rstrip()
                        md = inject_markdown_section(md, "A. 月度波動（P0 — kbars）", a_block)
        args.markdown_out.parent.mkdir(parents=True, exist_ok=True)
        args.markdown_out.write_text(md, encoding="utf-8")
        print(f"wrote {args.markdown_out}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
