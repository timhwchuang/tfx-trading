"""FT-024 Phase -1: HTF long-background census (Apr–Jun)."""

from __future__ import annotations

import argparse
import datetime
import json
import sys
from pathlib import Path

from config import PRODUCT_CODE
from reporting.htf_regime_census import build_census_payload
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
    """Session close days with day-session 1m (disk SSOT; shared helper)."""
    return discover_session_close_days(
        code,
        cache_dir,
        from_date=datetime.date.fromisoformat(from_date) if from_date else None,
        to_date=datetime.date.fromisoformat(to_date) if to_date else None,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="HTF regime census at 09:30")
    parser.add_argument("--code", default=PRODUCT_CODE)
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_TICK_CACHE_DIR)
    parser.add_argument("--from-date", default="2026-04-01")
    parser.add_argument("--to-date", default="2026-06-30")
    parser.add_argument(
        "--month",
        help="YYYY-MM shortcut (overrides from/to for that calendar month)",
    )
    parser.add_argument(
        "--no-batch-month",
        action="store_true",
        help="Load entire range in one SessionBarCache (higher memory)",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="JSON output path",
    )
    args = parser.parse_args(argv)

    from_date = args.from_date
    to_date = args.to_date
    if args.month:
        y, m = map(int, args.month.split("-"))
        first = datetime.date(y, m, 1)
        if m == 12:
            last = datetime.date(y + 1, 1, 1) - datetime.timedelta(days=1)
        else:
            last = datetime.date(y, m + 1, 1) - datetime.timedelta(days=1)
        from_date = first.isoformat()
        to_date = last.isoformat()

    days = _discover_kbar_days(
        args.cache_dir,
        args.code,
        from_date=from_date,
        to_date=to_date,
    )
    if not days:
        print("No kbar days found in range.", file=sys.stderr)
        return 1

    payload = build_census_payload(
        args.code,
        days,
        cache_dir=args.cache_dir,
        batch_by_month=not args.no_batch_month,
    )
    out = args.out or (
        _repo_root()
        / "workspaces/osf-baseline/reports"
        / f"htf_regime_census_{from_date}_{to_date}.json"
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Days scanned: {len(days)}")
    print(f"decision_hint: {payload['decision_hint']}")
    print(f"avg_htf_full_pct: {payload['avg_htf_full_pct']}")
    print(f"avg_htf_h4_only_pct: {payload['avg_htf_h4_only_pct']}")
    for month, s in payload.get("by_month", {}).items():
        print(
            f"  {month}: days={s['trading_days']} "
            f"full={s['htf_full_pct']:.1%} h4_only={s['htf_h4_only_pct']:.1%} "
            f"gap_up={s['gap_up_pct']:.1%}"
        )
    print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())