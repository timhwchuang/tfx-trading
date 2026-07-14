from __future__ import annotations

import csv
from datetime import date, datetime, timedelta
from pathlib import Path

from tfx_trading.kbar import KBar


class BarReader:
    def __init__(self, kbars_path: Path):
        self._kbars_path = kbars_path

    def load(self, start_date: date, end_date: date) -> list[KBar]:
        """
        載入指定日期區間內的所有 K 棒資料。
        參數可接受 date。
        """
        kbars = []
        current_date = start_date
        while current_date <= end_date:
            file_path = self._kbars_path / f"TMFR1_kbars_{current_date.strftime('%Y-%m-%d')}.csv"
            kbars.extend(self._load_from_file(file_path))
            current_date += timedelta(days=1)

        return kbars

    def _load_from_file(self, file_path: Path) -> list[KBar]:
        """從單一檔案載入 K 棒，檔案不存在時回傳空列表。"""
        if not file_path.exists():
            return []
        with open(file_path, "r", encoding="utf-8") as f:
            reader = csv.reader(f)
            next(reader)
            return [self._parse_row(row) for row in reader]

    def _parse_row(self, row: list[str]) -> KBar:
        return KBar(
            timestamp=datetime.fromisoformat(row[0]),
            open=float(row[1]),
            high=float(row[2]),
            low=float(row[3]),
            close=float(row[4]),
            volume=int(row[5]),
            amount=float(row[6]),
        )
