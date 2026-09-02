from __future__ import annotations

import csv
import json
from datetime import date, datetime, timedelta
from pathlib import Path

from tfx_trading.calendar import TradeCalendar, expected_day_1m, expected_night_1m
from tfx_trading.data_quality import DayQuality, QualityReport, report, write_rollover_csv
from tfx_trading.kbar import KBar

_FRIDAY = date(2026, 4, 10)
_SATURDAY = date(2026, 4, 11)
_SUNDAY = date(2026, 4, 12)
_MONDAY = date(2026, 4, 13)
_SETTLE = date(2026, 4, 15)


def _bar(
    ts: datetime,
    close: float = 100.0,
    *,
    high: float | None = None,
    low: float | None = None,
    volume: int = 1,
) -> KBar:
    return KBar(
        timestamp=ts,
        open=close,
        high=high if high is not None else close,
        low=low if low is not None else close,
        close=close,
        volume=volume,
        amount=close,
    )


def _write_calendar(path: Path, flags: dict[date, bool]) -> TradeCalendar:
    path.mkdir(parents=True, exist_ok=True)
    by_year: dict[int, list[dict[str, object]]] = {}
    for day, is_holiday in sorted(flags.items()):
        by_year.setdefault(day.year, []).append(
            {"date": day.strftime("%Y%m%d"), "isHoliday": is_holiday}
        )
    for year, rows in by_year.items():
        (path / f"{year}.json").write_text(json.dumps(rows), encoding="utf-8")
    return TradeCalendar(path)


def _april_flags() -> dict[date, bool]:
    flags: dict[date, bool] = {}
    day = date(2026, 3, 31)
    while day <= date(2026, 4, 16):
        flags[day] = day.weekday() >= 5
        day += timedelta(days=1)
    return flags


def _write_kbars(kbars_path: Path, day: date, bars: list[KBar]) -> None:
    path = kbars_path / f"TMFR1_kbars_{day.isoformat()}.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["timestamp", "open", "high", "low", "close", "volume", "amount"])
        for bar in bars:
            writer.writerow(
                [
                    f"{bar.timestamp:%Y-%m-%d %H:%M:%S.%f}",
                    bar.open,
                    bar.high,
                    bar.low,
                    bar.close,
                    bar.volume,
                    bar.amount,
                ]
            )


def _day_bars(
    day: date,
    close: float = 100.0,
    *,
    skip: set[datetime] | None = None,
    extra: list[KBar] | None = None,
    price_at: dict[datetime, float] | None = None,
    high: float | None = None,
) -> list[KBar]:
    bars: list[KBar] = []
    for ts in sorted(expected_day_1m(day)):
        if skip is not None and ts in skip:
            continue
        px = price_at[ts] if price_at is not None and ts in price_at else close
        bars.append(_bar(ts, px, high=high if high is not None else px))
    if extra:
        bars.extend(extra)
    return bars


def _evening_bars(day: date, close: float = 100.0) -> list[KBar]:
    return [_bar(ts, close) for ts in sorted(expected_night_1m(day)) if ts.date() == day]


def _dawn_bars(night_start: date, close: float = 100.0) -> list[KBar]:
    return [
        _bar(ts, close)
        for ts in sorted(expected_night_1m(night_start))
        if ts.date() == night_start + timedelta(days=1)
    ]


def _by_date(quality: QualityReport) -> dict[date, DayQuality]:
    return {row.date: row for row in quality.days}


def test_friday_saturday_stitch_drops_nothing(tmp_path: Path) -> None:
    kbars = tmp_path / "kbars"
    kbars.mkdir()
    cal = _write_calendar(tmp_path / "cal", _april_flags())
    _write_kbars(kbars, _FRIDAY, _day_bars(_FRIDAY) + _evening_bars(_FRIDAY))
    _write_kbars(kbars, _SATURDAY, _dawn_bars(_FRIDAY))

    quality = report(_FRIDAY, _SATURDAY, kbars, cal)
    friday = _by_date(quality)[_FRIDAY]
    saturday = _by_date(quality)[_SATURDAY]
    assert friday.dropped_5m_night == 0
    assert friday.night_1m_actual == 840
    assert friday.night_truncated is False
    assert saturday.file_status == "ok"
    assert saturday.day_1m_expected == 0
    assert saturday.night_1m_expected == 0
    assert saturday.notes == "dawn_only"


def test_friday_file_alone_drops_midnight_5m(tmp_path: Path) -> None:
    kbars = tmp_path / "kbars"
    kbars.mkdir()
    cal = _write_calendar(tmp_path / "cal", _april_flags())
    _write_kbars(kbars, _FRIDAY, _day_bars(_FRIDAY) + _evening_bars(_FRIDAY))

    quality = report(_FRIDAY, _SATURDAY, kbars, cal)
    friday = _by_date(quality)[_FRIDAY]
    saturday = _by_date(quality)[_SATURDAY]
    assert friday.night_truncated is False
    assert friday.dropped_5m_night > 0
    assert saturday.file_status == "missing_expected"
    assert quality.tape_dropped_5m == friday.dropped_5m_night
    assert quality.tape_expected_5m == 60 + 168


def test_window_end_friday_is_night_truncated(tmp_path: Path) -> None:
    kbars = tmp_path / "kbars"
    kbars.mkdir()
    cal = _write_calendar(tmp_path / "cal", _april_flags())
    _write_kbars(kbars, _FRIDAY, _day_bars(_FRIDAY) + _evening_bars(_FRIDAY))

    quality = report(_FRIDAY, _FRIDAY, kbars, cal)
    friday = _by_date(quality)[_FRIDAY]
    assert friday.night_truncated is True
    assert "night_truncated" in friday.notes
    assert friday.dropped_5m_night > 0
    assert quality.tape_expected_5m == 60
    assert quality.tape_dropped_5m == 0
    assert _SATURDAY not in _by_date(quality)


def test_extra_1346_does_not_count_as_missing(tmp_path: Path) -> None:
    kbars = tmp_path / "kbars"
    kbars.mkdir()
    cal = _write_calendar(tmp_path / "cal", _april_flags())
    extra = [_bar(datetime(2026, 4, 10, 13, 46), 100.0)]
    _write_kbars(kbars, _FRIDAY, _day_bars(_FRIDAY, extra=extra) + _evening_bars(_FRIDAY))
    _write_kbars(kbars, _SATURDAY, _dawn_bars(_FRIDAY))

    friday = _by_date(report(_FRIDAY, _SATURDAY, kbars, cal))[_FRIDAY]
    assert friday.day_1m_actual == 300
    assert friday.day_1m_missing_n == 0
    assert friday.dropped_5m_day == 0


def test_missing_1m_drops_matching_5m(tmp_path: Path) -> None:
    kbars = tmp_path / "kbars"
    kbars.mkdir()
    cal = _write_calendar(tmp_path / "cal", _april_flags())
    hole = {datetime(2026, 4, 10, 9, 0)}
    _write_kbars(kbars, _FRIDAY, _day_bars(_FRIDAY, skip=hole) + _evening_bars(_FRIDAY))
    _write_kbars(kbars, _SATURDAY, _dawn_bars(_FRIDAY))

    friday = _by_date(report(_FRIDAY, _SATURDAY, kbars, cal))[_FRIDAY]
    assert friday.day_1m_missing_n == 1
    assert friday.dropped_5m_day == 1


def test_sunday_is_holiday_ok(tmp_path: Path) -> None:
    kbars = tmp_path / "kbars"
    kbars.mkdir()
    cal = _write_calendar(tmp_path / "cal", _april_flags())
    _write_kbars(kbars, _FRIDAY, _day_bars(_FRIDAY) + _evening_bars(_FRIDAY))
    _write_kbars(kbars, _SATURDAY, _dawn_bars(_FRIDAY))

    quality = report(_FRIDAY, _SUNDAY, kbars, cal)
    sunday = _by_date(quality)[_SUNDAY]
    assert sunday.file_status == "holiday_ok"
    assert sunday.expected_file is False
    assert sunday.file_exists is False


def test_near_limit_uses_friday_1345_not_saturday_dawn(tmp_path: Path) -> None:
    kbars = tmp_path / "kbars"
    kbars.mkdir()
    cal = _write_calendar(tmp_path / "cal", _april_flags())
    _write_kbars(kbars, _FRIDAY, _day_bars(_FRIDAY, close=100.0) + _evening_bars(_FRIDAY))
    _write_kbars(kbars, _SATURDAY, _dawn_bars(_FRIDAY, close=200.0))
    _write_kbars(
        kbars,
        _MONDAY,
        _day_bars(_MONDAY, close=100.0, high=109.5) + _evening_bars(_MONDAY),
    )

    quality = report(_FRIDAY, _MONDAY, kbars, cal)
    monday = _by_date(quality)[_MONDAY]
    assert monday.near_limit is True
    assert "holiday_gap" in monday.notes


def test_settlement_rollover_row_and_non_settlement_skip(tmp_path: Path) -> None:
    kbars = tmp_path / "kbars"
    kbars.mkdir()
    cal = _write_calendar(tmp_path / "cal", _april_flags())
    prices = {
        datetime(2026, 4, 15, 13, 30): 100.0,
        datetime(2026, 4, 15, 13, 31): 147.0,
    }
    _write_kbars(kbars, _FRIDAY, _day_bars(_FRIDAY) + _evening_bars(_FRIDAY))
    _write_kbars(kbars, _SATURDAY, _dawn_bars(_FRIDAY))
    _write_kbars(kbars, _SETTLE, _day_bars(_SETTLE, price_at=prices) + _evening_bars(_SETTLE))

    quality = report(_FRIDAY, _SETTLE, kbars, cal)
    settle = _by_date(quality)[_SETTLE]
    assert settle.is_settlement is True
    assert "rollover_gap=+47" in settle.notes
    assert len(quality.rollovers) == 1
    assert quality.rollovers[0].settlement_date == _SETTLE
    assert quality.rollovers[0].gap_points == 47.0
    friday = _by_date(quality)[_FRIDAY]
    assert friday.is_settlement is False

    out = tmp_path / "roll.csv"
    write_rollover_csv(out, quality)
    text = out.read_text(encoding="utf-8")
    assert "back_adjust=false" in text
    assert "2026-04-15" in text


def test_missing_and_dawn_only_do_not_build_empty_store(tmp_path: Path) -> None:
    kbars = tmp_path / "kbars"
    kbars.mkdir()
    cal = _write_calendar(tmp_path / "cal", _april_flags())
    quality = report(_SATURDAY, _SUNDAY, kbars, cal)
    saturday = _by_date(quality)[_SATURDAY]
    sunday = _by_date(quality)[_SUNDAY]
    assert saturday.file_status == "missing_expected"
    assert saturday.dropped_5m_day == 0
    assert saturday.dropped_5m_night == 0
    assert sunday.file_status == "holiday_ok"


def test_file_present_day_1m_zero_listed_not_in_tape_rate(tmp_path: Path) -> None:
    kbars = tmp_path / "kbars"
    kbars.mkdir()
    flags = _april_flags()
    flags[date(2026, 4, 13)] = False
    cal = _write_calendar(tmp_path / "cal", flags)
    _write_kbars(kbars, _MONDAY, _dawn_bars(_SUNDAY, close=100.0))

    quality = report(_MONDAY, _MONDAY, kbars, cal)
    monday = _by_date(quality)[_MONDAY]
    assert monday.file_status == "ok"
    assert monday.day_1m_expected == 300
    assert monday.day_1m_actual == 0
    assert quality.file_present_day_1m_zero == (_MONDAY,)
    assert quality.tape_expected_5m == 0


def _jan_2025_flags() -> dict[date, bool]:
    flags: dict[date, bool] = {}
    day = date(2025, 1, 1)
    while day <= date(2025, 1, 31):
        flags[day] = day.weekday() >= 5
        day += timedelta(days=1)
    flags[date(2025, 1, 1)] = True
    return flags


def test_report_new_year_without_previous_year_json(tmp_path: Path) -> None:
    kbars = tmp_path / "kbars"
    kbars.mkdir()
    cal = _write_calendar(tmp_path / "cal", _jan_2025_flags())
    new_year = date(2025, 1, 1)

    quality = report(new_year, new_year, kbars, cal)
    row = _by_date(quality)[new_year]
    assert row.file_status == "holiday_ok"
    assert row.expected_file is False

    _write_kbars(kbars, new_year, _dawn_bars(date(2024, 12, 31)))
    quality_with_file = report(new_year, new_year, kbars, cal)
    present = _by_date(quality_with_file)[new_year]
    assert present.file_status == "unexpected_present"
    assert present.notes == "dawn_only"
