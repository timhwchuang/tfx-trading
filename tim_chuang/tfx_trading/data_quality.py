from __future__ import annotations

import argparse
import csv
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

from tfx_trading.bar_reader import BarReader
from tfx_trading.bar_store import BarStore
from tfx_trading.calendar import (
    TradeCalendar,
    expected_day_1m,
    expected_day_5m,
    expected_night_1m,
    expected_night_5m,
    is_day_session_1m,
    is_night_dawn_1m,
    is_night_evening_1m,
    minute_floor,
)
from tfx_trading.kbar import KBar

_DEFAULT_KBARS = Path(__file__).resolve().parent / "kbars_data"
_NEAR_LIMIT = 0.09
FileStatus = str


@dataclass(frozen=True)
class DayQuality:
    date: date
    weekday: str
    file_exists: bool
    expected_file: bool
    file_status: FileStatus
    day_1m_expected: int
    day_1m_actual: int
    day_1m_missing_n: int
    night_1m_expected: int
    night_1m_actual: int
    night_1m_missing_n: int
    expected_5m_day: int
    expected_5m_night: int
    dropped_5m_day: int
    dropped_5m_night: int
    is_settlement: bool
    near_limit: bool
    night_truncated: bool
    notes: str


@dataclass(frozen=True)
class RolloverRow:
    settlement_date: date
    old_close: float
    new_open: float
    gap_points: float
    gap_pct: float
    new_volume: int


@dataclass(frozen=True)
class QualityReport:
    days: tuple[DayQuality, ...]
    missing_expected: tuple[date, ...]
    file_present_day_1m_zero: tuple[date, ...]
    tape_dropped_5m: int
    tape_expected_5m: int
    tape_hole_rate: float
    rollovers: tuple[RolloverRow, ...]


def report(
    start_date: date,
    end_date: date,
    kbars_path: Path,
    calendar: TradeCalendar | None = None,
) -> QualityReport:
    cal = calendar if calendar is not None else TradeCalendar()
    reader = BarReader(kbars_path)
    days: list[DayQuality] = []
    rollovers: list[RolloverRow] = []
    prev_day_close: tuple[date, float] | None = None

    current = start_date
    while current <= end_date:
        day_row, roll, close = _one_day(
            current,
            end_date,
            reader,
            kbars_path,
            cal,
            prev_day_close,
        )
        days.append(day_row)
        if roll is not None:
            rollovers.append(roll)
        if close is not None:
            prev_day_close = (current, close)
        current += timedelta(days=1)

    tape_dropped = 0
    tape_expected = 0
    for row in days:
        if row.day_1m_actual <= 0:
            continue
        tape_dropped += row.dropped_5m_day
        tape_expected += row.expected_5m_day
        if not row.night_truncated:
            tape_dropped += row.dropped_5m_night
            tape_expected += row.expected_5m_night

    missing = tuple(r.date for r in days if r.file_status == "missing_expected")
    zero_day = tuple(
        r.date for r in days if r.file_exists and r.day_1m_actual == 0 and r.day_1m_expected > 0
    )
    rate = (tape_dropped / tape_expected) if tape_expected else 0.0
    return QualityReport(
        days=tuple(days),
        missing_expected=missing,
        file_present_day_1m_zero=zero_day,
        tape_dropped_5m=tape_dropped,
        tape_expected_5m=tape_expected,
        tape_hole_rate=rate,
        rollovers=tuple(rollovers),
    )


def _one_day(
    day: date,
    end_date: date,
    reader: BarReader,
    kbars_path: Path,
    cal: TradeCalendar,
    prev_day_close: tuple[date, float] | None,
) -> tuple[DayQuality, RolloverRow | None, float | None]:
    file_exists = _csv_exists(kbars_path, day)
    expected_file = cal.should_have_file(day)
    file_status = _file_status(expected_file, file_exists)
    trade_day = cal.is_trade_day(day)
    is_settlement = cal.is_settlement_day(day)
    next_day = day + timedelta(days=1)
    night_truncated = trade_day and next_day > end_date and not _csv_exists(kbars_path, next_day)

    file_bars = reader.load(day, day)
    next_bars = reader.load(next_day, next_day) if (trade_day or file_exists) else []

    day_bars = [b for b in file_bars if is_day_session_1m(b.timestamp)]
    night_bars = _stitched_night(day, file_bars, next_bars)

    day_expected = expected_day_1m(day) if trade_day else frozenset()
    night_expected = expected_night_1m(day) if trade_day else frozenset()
    day_actual_ts = {minute_floor(b.timestamp) for b in day_bars}
    night_actual_ts = {minute_floor(b.timestamp) for b in night_bars}
    day_1m_actual = len(day_actual_ts & day_expected)
    night_1m_actual = len(night_actual_ts & night_expected)
    day_1m_missing_n = len(day_expected - day_actual_ts)
    night_1m_missing_n = len(night_expected - night_actual_ts)

    day_5m_expected = expected_day_5m(day) if trade_day else frozenset()
    night_5m_expected = expected_night_5m(day) if trade_day else frozenset()
    dropped_5m_day = _dropped_5m(day_bars, day_5m_expected)
    dropped_5m_night = _dropped_5m(night_bars, night_5m_expected)

    close_1345 = _close_at(day_bars, day, 13, 45)
    near_limit = _near_limit(day_bars, prev_day_close)
    notes = _notes(
        file_exists=file_exists,
        trade_day=trade_day,
        day_1m_actual=day_1m_actual,
        night_truncated=night_truncated,
        near_limit=near_limit,
        prev_day_close=prev_day_close,
        day=day,
        roll_gap=_roll_gap(day_bars) if is_settlement else None,
    )
    roll = _rollover_row(day, day_bars) if is_settlement else None
    return (
        DayQuality(
            date=day,
            weekday=day.strftime("%a"),
            file_exists=file_exists,
            expected_file=expected_file,
            file_status=file_status,
            day_1m_expected=len(day_expected),
            day_1m_actual=day_1m_actual,
            day_1m_missing_n=day_1m_missing_n,
            night_1m_expected=len(night_expected),
            night_1m_actual=night_1m_actual,
            night_1m_missing_n=night_1m_missing_n,
            expected_5m_day=len(day_5m_expected),
            expected_5m_night=len(night_5m_expected),
            dropped_5m_day=dropped_5m_day,
            dropped_5m_night=dropped_5m_night,
            is_settlement=is_settlement,
            near_limit=near_limit,
            night_truncated=night_truncated,
            notes=notes,
        ),
        roll,
        close_1345,
    )


def _csv_exists(kbars_path: Path, day: date) -> bool:
    return (kbars_path / f"TMFR1_kbars_{day.isoformat()}.csv").exists()


def _file_status(expected_file: bool, file_exists: bool) -> FileStatus:
    if expected_file and file_exists:
        return "ok"
    if expected_file and not file_exists:
        return "missing_expected"
    if not expected_file and file_exists:
        return "unexpected_present"
    return "holiday_ok"


def _stitched_night(day: date, file_bars: list[KBar], next_bars: list[KBar]) -> list[KBar]:
    evening = [
        b for b in file_bars if b.timestamp.date() == day and is_night_evening_1m(b.timestamp)
    ]
    dawn = [
        b
        for b in next_bars
        if b.timestamp.date() == day + timedelta(days=1) and is_night_dawn_1m(b.timestamp)
    ]
    return evening + dawn


def _dropped_5m(bars: list[KBar], expected: frozenset[datetime]) -> int:
    if not expected:
        return 0
    if not bars:
        return len(expected)
    actual = {minute_floor(b.timestamp) for b in BarStore(bars).resample_5m()}
    return len(expected - actual)


def _close_at(bars: Sequence[KBar], day: date, hour: int, minute: int) -> float | None:
    target = datetime(day.year, day.month, day.day, hour, minute)
    for bar in bars:
        if minute_floor(bar.timestamp) == target:
            return bar.close
    return None


def _near_limit(
    day_bars: list[KBar],
    prev_day_close: tuple[date, float] | None,
) -> bool:
    if prev_day_close is None:
        return False
    core = [b for b in day_bars if not (b.timestamp.hour == 13 and b.timestamp.minute == 46)]
    if not core:
        return False
    prev_close = prev_day_close[1]
    if prev_close == 0:
        return False
    high = max(b.high for b in core)
    low = min(b.low for b in core)
    return (high - prev_close) / prev_close > _NEAR_LIMIT or (
        prev_close - low
    ) / prev_close > _NEAR_LIMIT


def _bars_by_hm(day_bars: Sequence[KBar]) -> dict[tuple[int, int], KBar]:
    keyed: dict[tuple[int, int], KBar] = {}
    for bar in day_bars:
        ts = minute_floor(bar.timestamp)
        keyed[(ts.hour, ts.minute)] = bar
    return keyed


def _roll_gap(day_bars: list[KBar]) -> float | None:
    by_hm = _bars_by_hm(day_bars)
    old = by_hm.get((13, 30))
    new = by_hm.get((13, 31))
    if old is None or new is None:
        return None
    return new.open - old.close


def _rollover_row(day: date, day_bars: list[KBar]) -> RolloverRow | None:
    by_hm = _bars_by_hm(day_bars)
    old = by_hm.get((13, 30))
    new = by_hm.get((13, 31))
    if old is None or new is None:
        return None
    gap = new.open - old.close
    pct = (gap / old.close * 100.0) if old.close else 0.0
    return RolloverRow(
        settlement_date=day,
        old_close=old.close,
        new_open=new.open,
        gap_points=gap,
        gap_pct=pct,
        new_volume=new.volume,
    )


def _notes(
    *,
    file_exists: bool,
    trade_day: bool,
    day_1m_actual: int,
    night_truncated: bool,
    near_limit: bool,
    prev_day_close: tuple[date, float] | None,
    day: date,
    roll_gap: float | None,
) -> str:
    parts: list[str] = []
    if file_exists and not trade_day:
        parts.append("dawn_only")
    if night_truncated:
        parts.append("night_truncated")
    if near_limit:
        parts.append("near_limit")
        if prev_day_close is not None and (day - prev_day_close[0]).days > 1:
            parts.append("holiday_gap")
    if roll_gap is not None:
        sign = "+" if roll_gap >= 0 else ""
        parts.append(f"rollover_gap={sign}{roll_gap:.0f}")
    if file_exists and trade_day and day_1m_actual == 0:
        parts.append("day_1m=0")
    return ",".join(parts)


def write_daily_csv(path: Path, quality: QualityReport) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "date",
        "weekday",
        "file_exists",
        "expected_file",
        "file_status",
        "day_1m_expected",
        "day_1m_actual",
        "day_1m_missing_n",
        "night_1m_expected",
        "night_1m_actual",
        "night_1m_missing_n",
        "expected_5m_day",
        "expected_5m_night",
        "dropped_5m_day",
        "dropped_5m_night",
        "is_settlement",
        "near_limit",
        "night_truncated",
        "notes",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in quality.days:
            writer.writerow(
                {
                    "date": row.date.isoformat(),
                    "weekday": row.weekday,
                    "file_exists": row.file_exists,
                    "expected_file": row.expected_file,
                    "file_status": row.file_status,
                    "day_1m_expected": row.day_1m_expected,
                    "day_1m_actual": row.day_1m_actual,
                    "day_1m_missing_n": row.day_1m_missing_n,
                    "night_1m_expected": row.night_1m_expected,
                    "night_1m_actual": row.night_1m_actual,
                    "night_1m_missing_n": row.night_1m_missing_n,
                    "expected_5m_day": row.expected_5m_day,
                    "expected_5m_night": row.expected_5m_night,
                    "dropped_5m_day": row.dropped_5m_day,
                    "dropped_5m_night": row.dropped_5m_night,
                    "is_settlement": row.is_settlement,
                    "near_limit": row.near_limit,
                    "night_truncated": row.night_truncated,
                    "notes": row.notes,
                }
            )


def write_rollover_csv(path: Path, quality: QualityReport) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        handle.write("# back_adjust=false\n")
        handle.write("# TMFR1 rolls at 13:31 on settlement; prices are raw, not back-adjusted.\n")
        writer = csv.writer(handle)
        writer.writerow(
            [
                "settlement_date",
                "old_close_1330",
                "new_open_1331",
                "gap_points",
                "gap_pct",
                "new_volume",
            ]
        )
        for row in quality.rollovers:
            writer.writerow(
                [
                    row.settlement_date.isoformat(),
                    row.old_close,
                    row.new_open,
                    row.gap_points,
                    f"{row.gap_pct:.4f}",
                    row.new_volume,
                ]
            )


def print_report(quality: QualityReport) -> None:
    print(
        f"{'date':<12} {'wd':<4} {'status':<20} {'d1m':>7} {'n1m':>7} {'d5m':>8} {'n5m':>8} notes"
    )
    for row in quality.days:
        print(
            f"{row.date.isoformat():<12} {row.weekday:<4} {row.file_status:<20} "
            f"{row.day_1m_actual}/{row.day_1m_expected:<4} "
            f"{row.night_1m_actual}/{row.night_1m_expected:<4} "
            f"{row.dropped_5m_day}/{row.expected_5m_day:<3} "
            f"{row.dropped_5m_night}/{row.expected_5m_night:<3} "
            f"{row.notes}"
        )
    print()
    print(
        f"Tape hole rate (acceptance): {quality.tape_dropped_5m}/{quality.tape_expected_5m}"
        f" = {quality.tape_hole_rate:.4%}"
    )
    missing = ", ".join(d.isoformat() for d in quality.missing_expected) or "-"
    zero = ", ".join(d.isoformat() for d in quality.file_present_day_1m_zero) or "-"
    print(f"Calendar vs files: missing_expected=[{missing}]")
    print(f"Calendar vs files: file present, day_1m=0=[{zero}]")


def parse_ymd(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def parse_args(args: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="TMFR1 1m data quality report")
    parser.add_argument("--start_date", type=parse_ymd, required=True, help="YYYY-MM-DD")
    parser.add_argument("--end_date", type=parse_ymd, required=True, help="YYYY-MM-DD")
    parser.add_argument("--kbars-path", type=Path, default=_DEFAULT_KBARS)
    parser.add_argument("--trade-days-dir", type=Path, default=None)
    parser.add_argument("--csv", type=Path, default=None)
    parser.add_argument("--rollover-csv", type=Path, default=None)
    parsed = parser.parse_args(args)
    if parsed.start_date > parsed.end_date:
        raise ValueError("start_date must be before end_date")
    return parsed


def main(argv: list[str] | None = None) -> None:
    parsed = parse_args(argv)
    calendar = TradeCalendar(parsed.trade_days_dir)
    quality = report(parsed.start_date, parsed.end_date, parsed.kbars_path, calendar)
    print_report(quality)
    if parsed.csv is not None:
        write_daily_csv(parsed.csv, quality)
    if parsed.rollover_csv is not None:
        write_rollover_csv(parsed.rollover_csv, quality)


if __name__ == "__main__":
    main()
