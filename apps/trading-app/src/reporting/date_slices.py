"""Reusable date-range resolution for FT-021 GUDT scripts."""

from __future__ import annotations

import argparse
import calendar
import datetime as dt
import random
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from reporting.gudt_parity_report import HOLDOUTS
from storage.tick_loader import list_cached_tick_dates

SLICES: dict[str, tuple[str, str]] = {label: (f, t) for label, f, t in HOLDOUTS}
DEFAULT_SLICE = "UAT_2m"
UAT_2M_MONTHS = frozenset({"2026-05", "2026-06"})
_MONTH_RE = re.compile(r"^\d{4}-\d{2}$")


@dataclass(frozen=True)
class DateRange:
    label: str
    from_date: str
    to_date: str
    months: tuple[str, ...] = ()

    @property
    def from_dt(self) -> dt.date:
        return dt.date.fromisoformat(self.from_date)

    @property
    def to_dt(self) -> dt.date:
        return dt.date.fromisoformat(self.to_date)


def _month_bounds(month: str) -> tuple[str, str]:
    if not _MONTH_RE.match(month):
        raise ValueError(f"invalid month {month!r}; expected YYYY-MM")
    year, mon = int(month[:4]), int(month[5:7])
    last = calendar.monthrange(year, mon)[1]
    return f"{month}-01", f"{month}-{last:02d}"


def list_cache_months(
    code: str,
    cache_dir: Path,
    *,
    exclude: frozenset[str] | None = None,
    min_days: int = 15,
) -> list[str]:
    """Months with at least ``min_days`` cached tick files (avoids sparse partial months)."""
    exclude = exclude or frozenset()
    dates = list_cached_tick_dates(code, cache_dir)
    by_month: dict[str, int] = {}
    for d in dates:
        m = d.strftime("%Y-%m")
        by_month[m] = by_month.get(m, 0) + 1
    months = sorted(m for m, n in by_month.items() if n >= min_days and m not in exclude)
    return months


def resolve_date_range(
    *,
    slice_name: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
    months: Sequence[str] | None = None,
    spot_check: int | None = None,
    spot_seed: int = 42,
    cache_dir: Path | None = None,
    code: str = "TMFR1",
    exclude_spot_months: frozenset[str] | None = None,
) -> DateRange:
    """Priority: explicit from/to > months > spot-check > slice > default UAT_2m."""
    if from_date and to_date:
        label = f"custom_{from_date}_{to_date}"
        return DateRange(label=label, from_date=from_date, to_date=to_date)
    if from_date or to_date:
        raise ValueError("both --from and --to required to override slice")

    if months:
        norm = sorted({m.strip() for m in months if m.strip()})
        if not norm:
            raise ValueError("empty --months")
        starts = [_month_bounds(m)[0] for m in norm]
        ends = [_month_bounds(m)[1] for m in norm]
        label = norm[0] if len(norm) == 1 else f"months_{norm[0]}_{norm[-1]}"
        return DateRange(
            label=label,
            from_date=min(starts),
            to_date=max(ends),
            months=tuple(norm),
        )

    if spot_check is not None:
        if spot_check < 1:
            raise ValueError("--spot-check must be >= 1")
        if cache_dir is None:
            raise ValueError("cache_dir required for --spot-check")
        pool = list_cache_months(
            code,
            cache_dir,
            exclude=exclude_spot_months or UAT_2M_MONTHS,
        )
        if len(pool) < spot_check:
            raise ValueError(
                f"spot-check {spot_check} exceeds available months ({len(pool)}): {pool}"
            )
        rng = random.Random(spot_seed)
        picked = sorted(rng.sample(pool, spot_check))
        starts = [_month_bounds(m)[0] for m in picked]
        ends = [_month_bounds(m)[1] for m in picked]
        label = f"spot_{spot_seed}_{picked[0]}_{picked[-1]}"
        return DateRange(
            label=label,
            from_date=min(starts),
            to_date=max(ends),
            months=tuple(picked),
        )

    name = slice_name or DEFAULT_SLICE
    if name not in SLICES:
        known = ", ".join(sorted(SLICES))
        raise ValueError(f"unknown slice {name!r}; known: {known}")
    f, t = SLICES[name]
    return DateRange(label=name, from_date=f, to_date=t)


def day_in_date_range(day: str, date_range: DateRange) -> bool:
    """When ``months`` is set, match YYYY-MM membership (non-contiguous spot-check safe)."""
    if date_range.months:
        return day[:7] in date_range.months
    return date_range.from_date <= day <= date_range.to_date


def tick_dates_for_months(
    months: Sequence[str],
    *,
    code: str,
    cache_dir: Path,
) -> list[str]:
    month_set = frozenset(months)
    dates = list_cached_tick_dates(code, cache_dir)
    return sorted(d.isoformat() for d in dates if d.strftime("%Y-%m") in month_set)


def backtest_date_cli_args(
    date_range: DateRange,
    *,
    code: str,
    cache_dir: Path,
) -> list[str]:
    """CLI args for backtest: explicit ``--dates`` when months are non-contiguous."""
    if date_range.months:
        dates = tick_dates_for_months(date_range.months, code=code, cache_dir=cache_dir)
        if not dates:
            raise ValueError(f"no tick cache dates for months {list(date_range.months)}")
        return ["--dates", *dates]
    return [
        "--dates-from-cache",
        "--from-date",
        date_range.from_date,
        "--to-date",
        date_range.to_date,
    ]


def artifact_paths(
    ws_reports: Path,
    ws_logs: Path,
    label: str,
) -> dict[str, Path]:
    safe = label.replace("/", "_")
    return {
        "baseline_log": ws_logs / f"baseline_{safe}.log",
        "baseline_json": ws_reports / f"baseline_{safe}.json",
        "day_plans": ws_reports / f"day_plans_{safe}.json",
        "execution_parity_json": ws_reports / f"execution_parity_{safe}.json",
        "execution_parity_md": ws_reports / f"execution_parity_{safe}.md",
    }


def add_date_slice_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--slice",
        dest="slice_name",
        default=DEFAULT_SLICE,
        help=f"Named range (default {DEFAULT_SLICE}); choices: {', '.join(SLICES)}",
    )
    parser.add_argument("--from", dest="from_date", default=None, help="Override slice start YYYY-MM-DD")
    parser.add_argument("--to", dest="to_date", default=None, help="Override slice end YYYY-MM-DD")
    parser.add_argument(
        "--months",
        default=None,
        help="Comma-separated YYYY-MM months (overrides --slice)",
    )
    parser.add_argument(
        "--spot-check",
        type=int,
        default=None,
        help="Randomly sample N months from tick cache (excludes UAT_2m months)",
    )
    parser.add_argument("--spot-seed", type=int, default=42, help="RNG seed for --spot-check")
    parser.add_argument("--code", default="TMFR1")
    parser.add_argument("--cache-dir", type=Path, default=None)


def resolve_from_args(
    args: argparse.Namespace,
    *,
    repo_root: Path,
) -> DateRange:
    cache_dir = args.cache_dir or (repo_root / "tick_cache")
    months = None
    if getattr(args, "months", None):
        months = [m.strip() for m in str(args.months).split(",") if m.strip()]
    return resolve_date_range(
        slice_name=getattr(args, "slice_name", None),
        from_date=getattr(args, "from_date", None),
        to_date=getattr(args, "to_date", None),
        months=months,
        spot_check=getattr(args, "spot_check", None),
        spot_seed=int(getattr(args, "spot_seed", 42)),
        cache_dir=cache_dir,
        code=getattr(args, "code", "TMFR1"),
    )
