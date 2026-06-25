"""Audit tick_cache: compare tick-derived 1m bars vs on-disk kbars (OHLC + volume)."""

from __future__ import annotations

import argparse
import csv
import datetime
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Iterator

from storage.cache_paths import DEFAULT_KBAR_CACHE_DIR, DEFAULT_TICK_CACHE_DIR
from storage.kbar_loader import load_kbars_csv, resolve_kbars_cache_path
from storage.tick_loader import (
    DEFAULT_TICK_RANGE_END,
    DEFAULT_TICK_RANGE_START,
    ReplayTick,
    _open_tick_csv_reader,
    load_merged_tick_cache,
    resolve_tick_cache_path,
)
from storage.tick_rollover import (
    EXPECTED_LAST_TICK_MINUTE,
    tick_tail_missing_minutes,
)

EXPECTED_DAY_BARS = (
    (DEFAULT_TICK_RANGE_END.hour * 60 + DEFAULT_TICK_RANGE_END.minute)
    - (DEFAULT_TICK_RANGE_START.hour * 60 + DEFAULT_TICK_RANGE_START.minute)
)

_TICK_FILE_RE = re.compile(
    r"^(?P<code>.+?)_(?P<date>\d{4}-\d{2}-\d{2})(?:\.csv)?(?:\.gz)?$"
)


@dataclass(frozen=True)
class MinuteBar:
    minute: datetime.datetime
    Open: float
    High: float
    Low: float
    Close: float
    Volume: int


@dataclass
class DayAuditReport:
    code: str
    date: datetime.date
    tick_path: Path | None = None
    kbar_path: Path | None = None
    tick_count: int = 0
    tick_first: datetime.datetime | None = None
    tick_last: datetime.datetime | None = None
    tick_minutes: int = 0
    kbar_count: int = 0
    kbar_first: datetime.datetime | None = None
    kbar_last: datetime.datetime | None = None
    # Full counts (not truncated)
    vol_diff_count: int = 0
    ohlc_diff_count: int = 0
    missing_kbar_count: int = 0
    kbar_without_tick_count: int = 0
    tick_tail_missing_minutes: int = 0
    kbar_gap_count: int = 0
    kbar_gap_missing_minutes: int = 0
    max_vol_abs_diff: int = 0
    # Detail samples
    missing_kbar_for_ticks: list[datetime.datetime] = field(default_factory=list)
    kbar_without_ticks: list[datetime.datetime] = field(default_factory=list)
    kbar_gaps: list[tuple[datetime.datetime, datetime.datetime, int]] = field(
        default_factory=list
    )
    ohlc_mismatches: list[str] = field(default_factory=list)
    volume_mismatches: list[str] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.issues

    @property
    def tick_filename(self) -> str:
        return f"{self.code}_{self.date.isoformat()}.csv"

    @property
    def severity(self) -> str:
        if (
            self.missing_kbar_count
            or self.kbar_without_tick_count
            or self.ohlc_diff_count
            or self.tick_tail_missing_minutes
            or self.kbar_count != EXPECTED_DAY_BARS
            or self.kbar_gap_missing_minutes
        ):
            return "FAIL"
        if self.vol_diff_count:
            return "WARN"
        return "OK"


def discover_tick_cache_pairs(
    cache_dir: Path,
    *,
    code: str | None = None,
    start: datetime.date | None = None,
    end: datetime.date | None = None,
) -> list[tuple[str, datetime.date]]:
    """Return sorted (code, date) for tick CSV files under *cache_dir* (excludes kbars)."""
    cache_dir = Path(cache_dir)
    if not cache_dir.is_dir():
        return []

    pairs: set[tuple[str, datetime.date]] = set()
    for path in cache_dir.iterdir():
        if not path.is_file():
            continue
        name = path.name
        if "_kbars_" in name:
            continue
        m = _TICK_FILE_RE.match(name)
        if m is None:
            continue
        file_code = m.group("code")
        if code is not None and file_code != code:
            continue
        try:
            day = datetime.date.fromisoformat(m.group("date"))
        except ValueError:
            continue
        if start is not None and day < start:
            continue
        if end is not None and day > end:
            continue
        pairs.add((file_code, day))
    return sorted(pairs, key=lambda x: (x[0], x[1]))


def _minute_floor(ts: datetime.datetime) -> datetime.datetime:
    return ts.replace(second=0, microsecond=0)


def _kbar_ts_for_tick_minute(minute: datetime.datetime) -> datetime.datetime:
    return minute + datetime.timedelta(minutes=1)


SESSION_KBAR_START = datetime.time(8, 46)


def _in_session_kbar_ts(kts: datetime.datetime) -> bool:
    return SESSION_KBAR_START <= kts.time() <= DEFAULT_TICK_RANGE_END


def aggregate_ticks_to_minute_bars(ticks: Iterable[ReplayTick]) -> dict[datetime.datetime, MinuteBar]:
    """Build OHLCV per calendar minute from raw ticks (volume = sum, no dedupe)."""
    ordered = sorted(ticks, key=lambda t: t.datetime)
    vol: dict[datetime.datetime, int] = defaultdict(int)
    o: dict[datetime.datetime, float] = {}
    h: dict[datetime.datetime, float] = {}
    l: dict[datetime.datetime, float] = {}
    c: dict[datetime.datetime, float] = {}
    for tick in ordered:
        m = _minute_floor(tick.datetime)
        price = float(tick.close)
        vol[m] += int(tick.volume)
        if m not in o:
            o[m] = price
            h[m] = price
            l[m] = price
            c[m] = price
        else:
            h[m] = max(h[m], price)
            l[m] = min(l[m], price)
            c[m] = price
    return {
        m: MinuteBar(minute=m, Open=o[m], High=h[m], Low=l[m], Close=c[m], Volume=vol[m])
        for m in sorted(vol)
    }


def _iter_ticks_csv(path: Path) -> Iterator[ReplayTick]:
    with _open_tick_csv_reader(path) as f:
        for row in csv.DictReader(f):
            yield ReplayTick(
                datetime=datetime.datetime.fromisoformat(row["datetime"]),
                close=row["close"],
                volume=int(row["volume"]),
                tick_type=int(row["tick_type"]),
                bid_price=float(row["bid_price"]),
                ask_price=float(row["ask_price"]),
            )


def _load_ticks_for_audit(cache_dir: Path, code: str, date: datetime.date) -> list[ReplayTick]:
    path = resolve_tick_cache_path(cache_dir, code, date)
    if path is None:
        return []
    try:
        return list(load_merged_tick_cache(cache_dir, code, date))
    except Exception:
        return list(_iter_ticks_csv(path))


def _resolve_kbar_path_for_audit(
    tick_cache_dir: Path,
    code: str,
    date: datetime.date,
    *,
    kbar_cache_dir: Path | None = None,
) -> Path | None:
    """Prefer primary ``kbar_cache`` when configured; else tick_cache mirror."""
    if kbar_cache_dir is not None:
        path = resolve_kbars_cache_path(kbar_cache_dir, code, date)
        if path is not None:
            return path
    return resolve_kbars_cache_path(tick_cache_dir, code, date)


def audit_day(
    code: str,
    date: datetime.date,
    *,
    cache_dir: Path = DEFAULT_TICK_CACHE_DIR,
    kbar_cache_dir: Path | None = None,
    max_examples: int = 5,
) -> DayAuditReport:
    """Compare tick-derived minute bars with on-disk kbars for one session day."""
    report = DayAuditReport(code=code, date=date)
    report.tick_path = resolve_tick_cache_path(cache_dir, code, date)
    report.kbar_path = _resolve_kbar_path_for_audit(
        cache_dir, code, date, kbar_cache_dir=kbar_cache_dir
    )

    if report.tick_path is None:
        report.issues.append("missing tick cache")
        return report
    if report.kbar_path is None:
        report.issues.append("missing kbar cache")
        return report

    ticks = _load_ticks_for_audit(cache_dir, code, date)
    report.tick_count = len(ticks)
    if not ticks:
        report.issues.append("empty tick file")
        return report

    report.tick_first = ticks[0].datetime
    report.tick_last = ticks[-1].datetime
    minute_bars = aggregate_ticks_to_minute_bars(ticks)
    report.tick_minutes = len(minute_bars)
    report.tick_tail_missing_minutes = tick_tail_missing_minutes(ticks, date)

    kbars = load_kbars_csv(report.kbar_path)
    session_kbars = [
        b
        for b in kbars
        if datetime.time(8, 46) <= b.ts.time() <= DEFAULT_TICK_RANGE_END
    ]
    report.kbar_count = len(session_kbars)
    if session_kbars:
        report.kbar_first = session_kbars[0].ts
        report.kbar_last = session_kbars[-1].ts

    if report.kbar_count != EXPECTED_DAY_BARS:
        report.issues.append(
            f"kbar count {report.kbar_count} != expected {EXPECTED_DAY_BARS}"
        )

    if report.tick_tail_missing_minutes > 0:
        report.issues.append(
            f"tick尾缺 {report.tick_tail_missing_minutes}m "
            f"(最後 {report.tick_last.time().strftime('%H:%M:%S')}, "
            f"預期至 {EXPECTED_LAST_TICK_MINUTE.strftime('%H:%M')})"
        )

    ordered = sorted(b.ts for b in session_kbars)
    gap_missing = 0
    for prev, cur in zip(ordered, ordered[1:]):
        gap_min = int((cur - prev).total_seconds() // 60)
        if gap_min > 1:
            report.kbar_gaps.append((prev, cur, gap_min))
            gap_missing += gap_min - 1
    report.kbar_gap_count = len(report.kbar_gaps)
    report.kbar_gap_missing_minutes = gap_missing
    if report.kbar_gaps:
        report.issues.append(
            f"kbar時間缺口 {report.kbar_gap_missing_minutes}m "
            f"({report.kbar_gap_count} 段)"
        )

    kbar_by_ts = {b.ts: b for b in session_kbars}
    all_missing_kbar: list[datetime.datetime] = []
    all_kbar_wo_tick: list[datetime.datetime] = []
    all_ohlc: list[str] = []
    all_vol: list[str] = []
    max_vol_diff = 0

    for minute, bar in minute_bars.items():
        kts = _kbar_ts_for_tick_minute(minute)
        if not _in_session_kbar_ts(kts):
            continue
        kbar = kbar_by_ts.get(kts)
        if kbar is None:
            all_missing_kbar.append(kts)
            continue
        for field_name, tick_val, kbar_val in (
            ("Open", bar.Open, kbar.Open),
            ("High", bar.High, kbar.High),
            ("Low", bar.Low, kbar.Low),
            ("Close", bar.Close, kbar.Close),
        ):
            if abs(tick_val - kbar_val) > 0.01:
                all_ohlc.append(
                    f"{kts.strftime('%H:%M')} {field_name} tick={tick_val} kbar={kbar_val}"
                )
        if bar.Volume != kbar.Volume:
            diff = abs(bar.Volume - kbar.Volume)
            max_vol_diff = max(max_vol_diff, diff)
            all_vol.append(
                f"{kts.strftime('%H:%M')} tick={bar.Volume} kbar={kbar.Volume} Δ{diff}"
            )

    for kts in sorted(kbar_by_ts):
        tick_minute = kts - datetime.timedelta(minutes=1)
        if tick_minute not in minute_bars:
            all_kbar_wo_tick.append(kts)

    report.missing_kbar_count = len(all_missing_kbar)
    report.kbar_without_tick_count = len(all_kbar_wo_tick)
    report.ohlc_diff_count = len(all_ohlc)
    report.vol_diff_count = len(all_vol)
    report.max_vol_abs_diff = max_vol_diff

    if report.missing_kbar_count:
        report.issues.append(f"kbars缺口 {report.missing_kbar_count}")
    if report.kbar_without_tick_count:
        report.issues.append(f"kbars無tick {report.kbar_without_tick_count}")
    if report.ohlc_diff_count:
        report.issues.append(f"ohlc差 {report.ohlc_diff_count}")
    if report.vol_diff_count:
        report.issues.append(f"vol差 {report.vol_diff_count}")

    if max_examples >= 0:
        report.missing_kbar_for_ticks = all_missing_kbar[:max_examples]
        report.kbar_without_ticks = all_kbar_wo_tick[:max_examples]
        report.ohlc_mismatches = all_ohlc[:max_examples]
        report.volume_mismatches = all_vol[:max_examples]

    return report


def scan_cache_dir(
    cache_dir: Path,
    *,
    code: str | None = None,
    start: datetime.date | None = None,
    end: datetime.date | None = None,
    max_examples: int = 3,
    kbar_cache_dir: Path | None = None,
) -> list[DayAuditReport]:
    pairs = discover_tick_cache_pairs(cache_dir, code=code, start=start, end=end)
    return [
        audit_day(
            c,
            d,
            cache_dir=cache_dir,
            kbar_cache_dir=kbar_cache_dir,
            max_examples=max_examples,
        )
        for c, d in pairs
    ]


def format_day_line(report: DayAuditReport) -> str:
    """One-line summary per day for scan output."""
    parts = [
        report.tick_filename,
        f"差異vols:{report.vol_diff_count}",
        f"ohlc差:{report.ohlc_diff_count}",
        f"kbars:{report.kbar_count}/{EXPECTED_DAY_BARS}",
    ]
    if report.missing_kbar_count:
        parts.insert(3, f"kbars缺口:{report.missing_kbar_count}")
    if report.tick_tail_missing_minutes:
        parts.append(f"tick尾缺:{report.tick_tail_missing_minutes}m")
    if report.kbar_gap_missing_minutes:
        parts.append(f"kbar缺口:{report.kbar_gap_missing_minutes}m")
    if report.max_vol_abs_diff > 1:
        parts.append(f"最大volΔ:{report.max_vol_abs_diff}")
    return f"{report.severity:4} " + ", ".join(parts)


def format_day_report(report: DayAuditReport, *, verbose: bool = False) -> str:
    lines = [format_day_line(report)]
    if verbose or not report.ok:
        if report.issues:
            lines.append("      " + "; ".join(report.issues))
        lines.append(
            f"      ticks={report.tick_count} "
            f"{report.tick_first} .. {report.tick_last} | minutes={report.tick_minutes}"
        )
        lines.append(
            f"      kbars {report.kbar_first} .. {report.kbar_last}"
        )
        if report.kbar_gaps:
            for prev, cur, gap in report.kbar_gaps:
                lines.append(
                    f"      kbar gap: {prev.strftime('%H:%M')} → {cur.strftime('%H:%M')} (+{gap}m)"
                )
        for label, items in (
            ("missing kbar", report.missing_kbar_for_ticks),
            ("kbar w/o ticks", report.kbar_without_ticks),
            ("OHLC diff", report.ohlc_mismatches),
            ("vol diff", report.volume_mismatches),
        ):
            if items:
                lines.append(f"      {label}: " + "; ".join(str(x) for x in items))
    return "\n".join(lines)


def format_scan_summary(
    reports: list[DayAuditReport],
    *,
    vol_warn_threshold: int = 20,
) -> str:
    total = len(reports)
    failed = [r for r in reports if r.severity == "FAIL"]
    warned = [r for r in reports if r.severity == "WARN"]
    ok = [r for r in reports if r.severity == "OK"]
    high_vol = [r for r in reports if r.vol_diff_count >= vol_warn_threshold]

    lines = [
        "=== tick_cache audit 摘要 ===",
        f"掃描 {total} 天 | OK {len(ok)} | WARN(vol) {len(warned)} | FAIL {len(failed)}",
    ]
    if high_vol:
        lines.append(
            f"vol差 ≥{vol_warn_threshold} 的天數: {len(high_vol)} "
            "(建議人工檢查或刪檔重抓)"
        )
    if failed:
        lines.append("")
        lines.append("FAIL 清單:")
        for r in failed:
            lines.append(f"  {format_day_line(r)}")
    if warned and len(warned) <= 30:
        lines.append("")
        lines.append("WARN 清單 (僅 vol 偏差):")
        for r in warned:
            lines.append(f"  {format_day_line(r)}")
    elif warned:
        lines.append("")
        lines.append(f"WARN {len(warned)} 天 (僅 vol 偏差，見上方逐日列表)")
    return "\n".join(lines)


def _parse_optional_date(value: str | None) -> datetime.date | None:
    if value is None:
        return None
    return datetime.date.fromisoformat(value)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Audit tick_cache: ticks-derived 1m OHLCV vs kbars. "
            "Prints one summary line per day."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
Examples (from apps/trading-app/src):
  python -m storage.cache_audit --code TMFR1
  python -m storage.cache_audit --date 2026-01-08 -v
  python -m storage.cache_repair --code TMFR1 --fix

Use cache_repair to auto-merge rollover ticks and fill kbar gaps from ticks.
""",
    )
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=DEFAULT_TICK_CACHE_DIR,
        help="tick_cache root (kbars read from same dir)",
    )
    parser.add_argument(
        "--kbar-cache-dir",
        type=Path,
        default=DEFAULT_KBAR_CACHE_DIR,
        help="Primary kbar_cache (used when mirror not under --cache-dir)",
    )
    parser.add_argument("--code", help="Filter by contract code (e.g. TMFR1)")
    parser.add_argument("--date", type=_parse_optional_date, help="Single YYYY-MM-DD")
    parser.add_argument("--from-date", type=_parse_optional_date, dest="from_date")
    parser.add_argument("--to-date", type=_parse_optional_date, dest="to_date")
    parser.add_argument(
        "--vol-warn-threshold",
        type=int,
        default=20,
        help="Flag days with vol diff count >= N in summary (default 20)",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Extra detail for failed/warned days",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    cache_dir = Path(args.cache_dir)

    if args.date is not None:
        code = args.code or _default_code_from_cache(cache_dir, args.date)
        if code is None:
            print(
                f"cache_audit: no tick file for {args.date} (use --code)",
                file=sys.stderr,
            )
            return 1
        report = audit_day(
            code,
            args.date,
            cache_dir=cache_dir,
            kbar_cache_dir=Path(args.kbar_cache_dir),
            max_examples=10,
        )
        print(format_day_report(report, verbose=True))
        return 0 if report.severity != "FAIL" else 1

    reports = scan_cache_dir(
        cache_dir,
        code=args.code,
        start=args.from_date,
        end=args.to_date,
        max_examples=3,
        kbar_cache_dir=Path(args.kbar_cache_dir),
    )
    if not reports:
        print(f"cache_audit: no tick files under {cache_dir}", file=sys.stderr)
        return 1

    for report in reports:
        print(format_day_line(report))
        if args.verbose and not report.ok:
            print(format_day_report(report, verbose=True).split("\n", 1)[-1])
    print()
    print(format_scan_summary(reports, vol_warn_threshold=args.vol_warn_threshold))
    return 0 if not any(r.severity == "FAIL" for r in reports) else 1


def _default_code_from_cache(cache_dir: Path, date: datetime.date) -> str | None:
    for code, day in discover_tick_cache_pairs(cache_dir, start=date, end=date):
        if day == date:
            return code
    return None


if __name__ == "__main__":
    raise SystemExit(main())
