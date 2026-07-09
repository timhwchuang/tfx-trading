"""FT-024: Opening sweep + 15m FVG + 5m trigger counterfactual (long-only)."""

from __future__ import annotations

import argparse
import datetime
import json
import sys
from pathlib import Path

from config import PRODUCT_CODE
from reporting.opening_sweep_fvg_counterfactual import (
    OsfParams,
    build_osf_payload,
    replay_day_long,
)
from reporting.osf_outlook import load_store_for_outlook
from reporting.osf_session_context import OsfBarStore
from storage.cache_paths import DEFAULT_TICK_CACHE_DIR
from storage.session_bar_cache import discover_session_close_days


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _discover_kbar_days(
    cache_dir: Path,
    code: str,
    *,
    from_date: str | None,
    to_date: str | None,
) -> list[datetime.date]:
    """Session close days with day-session 1m (disk SSOT; shared with census)."""
    return discover_session_close_days(
        code,
        cache_dir,
        from_date=datetime.date.fromisoformat(from_date) if from_date else None,
        to_date=datetime.date.fromisoformat(to_date) if to_date else None,
    )


def _warn_if_sparse_days(days: list[datetime.date]) -> None:
    """Single load_range uses len(days); sparse multi-month lists under-load early dates."""
    if len(days) < 2:
        return
    span = (days[-1] - days[0]).days + 1
    if span > 2 * len(days):
        print(
            f"warning: sparse day list (n={len(days)}, calendar_span={span}); "
            "OsfBarStore.load_range sizes history by n only — prefer contiguous "
            "ranges or month-batch (unsupported for single load).",
            file=sys.stderr,
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="OSF long counterfactual")
    parser.add_argument("--code", default=PRODUCT_CODE)
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_TICK_CACHE_DIR)
    parser.add_argument(
        "--dates",
        nargs="+",
        help="YYYY-MM-DD day(s); prefer contiguous / month ranges (single load_range)",
    )
    parser.add_argument("--from-date")
    parser.add_argument("--to-date")
    parser.add_argument(
        "--mode",
        choices=("fingerprint", "grid", "replay"),
        default="fingerprint",
        help="replay: single-day funnel + 15m reject breakdown",
    )
    parser.add_argument(
        "--htf-mode",
        default="h4_only",
        choices=("none", "h4_only", "h4_h1", "full"),
    )
    parser.add_argument(
        "--liquidity-mode",
        default="pools",
        choices=("or_only", "pools", "pools_or"),
    )
    parser.add_argument("--out", type=Path, help="Write JSON payload")
    parser.add_argument(
        "--include-outlook",
        action="store_true",
        help="Attach night/HTF outlook block (replay mode)",
    )
    args = parser.parse_args(argv)

    if args.dates:
        days = sorted({datetime.date.fromisoformat(d) for d in args.dates})
    else:
        days = _discover_kbar_days(
            args.cache_dir,
            args.code,
            from_date=args.from_date,
            to_date=args.to_date,
        )
    if not days:
        print("No days resolved", file=sys.stderr)
        return 2
    _warn_if_sparse_days(days)

    params = OsfParams(htf_mode=args.htf_mode, liquidity_mode=args.liquidity_mode)

    if args.mode == "replay":
        if len(days) != 1:
            print("replay mode expects a single --dates day", file=sys.stderr)
            return 2
        day = days[0]
        store = (
            load_store_for_outlook(args.code, day, cache_dir=args.cache_dir)
            if args.include_outlook
            else OsfBarStore.load_range(args.code, [day], cache_dir=args.cache_dir)
        )
        if store is None:
            print("No bars for day", file=sys.stderr)
            return 2
        payload = replay_day_long(
            args.code,
            day,
            params=params,
            store=store,
            include_outlook=args.include_outlook,
        )
    else:
        store = OsfBarStore.load_range(args.code, days, cache_dir=args.cache_dir)
        payload = build_osf_payload(
            args.code, days, params=params, cache_dir=args.cache_dir, store=store
        )
        payload["mode"] = args.mode
        payload["n_days"] = len(days)

    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + "\n", encoding="utf-8")
        print(f"Wrote {args.out}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
