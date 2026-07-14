from __future__ import annotations

from datetime import datetime

from tfx_trading.kbar import KBar


class BarStore:
    def __init__(self, kbars: list[KBar]) -> None:
        """
        初始化 BarStore。
        參數 kbars 為 KBar 列表，as_of 為當前時間戳記。
        """
        self._kbars: list[KBar] = kbars
        self._as_of: datetime = kbars[-1].timestamp

    def push(self, kbar: KBar) -> None:
        """
        新增 K 棒到 BarStore。
        """
        self._kbars.append(kbar)
        self._as_of = kbar.timestamp

    def recent(self, as_of: datetime, n: int) -> list[KBar]:
        """
        回傳指定時間戳記之前的 N 根 K 棒。
        之後可以考慮使用二分搜尋法來加速查詢。
        """
        return [kbar for kbar in self._kbars if kbar.timestamp <= as_of][-n:]

    def show_window(self, start: datetime, end: datetime) -> None:
        """
        顯示指定時間區間的 K 棒。
        """
        for kbar in self._kbars:
            if start <= kbar.timestamp <= end:
                print("--------------------------------")
                print(f"Timestamp: {kbar.timestamp}")
                print(f"Open: {kbar.open}")
                print(f"High: {kbar.high}")
                print(f"Low: {kbar.low}")
                print(f"Close: {kbar.close}")
                print(f"Volume: {kbar.volume}")
                print("--------------------------------")
