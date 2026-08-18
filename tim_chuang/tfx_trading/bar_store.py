from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Literal

from tfx_trading.kbar import KBar

KType = Literal["1m", "5m", "15m", "30m", "1h", "4h", "1d"]
SessionKind = Literal["day", "night"]


def _five_min_close(ts: datetime) -> datetime:
    """08:46～08:50 → 08:50；已在 5 分整點則維持不變。"""
    ts = ts.replace(second=0, microsecond=0)
    remainder = ts.minute % 5
    if remainder == 0:
        return ts
    return ts + timedelta(minutes=5 - remainder)


def session_kind(ts: datetime) -> SessionKind | None:
    """日盤 08:50～13:45；夜盤 15:05～05:00（含跨午夜）。非盤中則 None。"""
    minutes = ts.hour * 60 + ts.minute
    if 8 * 60 + 50 <= minutes <= 13 * 60 + 45:
        return "day"
    if minutes >= 15 * 60 + 5 or minutes <= 5 * 60:
        return "night"
    return None


def session_key(ts: datetime) -> tuple[date, SessionKind] | None:
    """
    同一盤的識別：日盤用當日日期；夜盤用 15:05 那側的日期（05:00 以前算前一日）。
    週五 13:45 與週一 08:50 都是 day，但 key 不同；夜盤缺 5 分仍同一 key。
    """
    kind = session_kind(ts)
    if kind is None:
        return None
    if kind == "day":
        return (ts.date(), "day")
    if ts.hour * 60 + ts.minute >= 15 * 60 + 5:
        return (ts.date(), "night")
    return (ts.date() - timedelta(days=1), "night")


def is_session_5m_close(ts: datetime) -> bool:
    """合法 5 分 close：日盤 08:50～13:45；夜盤 15:05～05:00。"""
    return ts.minute % 5 == 0 and session_kind(ts) is not None


def is_session_complete(kind: SessionKind, last_bar_ts: datetime) -> bool:
    """該段是否已印出合法最後一根 5 分（日盤 13:45 / 夜盤 05:00）。"""
    hm = (last_bar_ts.hour, last_bar_ts.minute)
    if kind == "day":
        return hm == (13, 45)
    return hm == (5, 0)


def _is_session_5m_close(ts: datetime) -> bool:
    return is_session_5m_close(ts)


class BarStore:
    def __init__(self, kbars: list[KBar]) -> None:
        """
        初始化 BarStore。
        參數 kbars 為 KBar 列表，as_of 為當前時間戳記。
        """
        if len(kbars) == 0:
            raise ValueError("KBar list is empty")

        self._kbars: list[KBar] = kbars
        self._as_of: datetime = kbars[-1].timestamp

    def push(self, kbar: KBar) -> None:
        """
        新增 K 棒到 BarStore。
        """
        self._kbars.append(kbar)
        self._as_of = kbar.timestamp

    def recent(self, as_of: datetime, n: int, ktype: KType = "1m") -> list[KBar]:
        """
        回傳指定時間戳記之前的 N 根 K 棒。
        之後可以考慮使用二分搜尋法來加速查詢。
        """
        if ktype != "1m":
            raise NotImplementedError(f"Not implemented: {ktype}")

        return [kbar for kbar in self._kbars if kbar.timestamp <= as_of][-n:]

    def show_window(self, start: datetime, end: datetime, ktype: KType = "1m") -> None:
        """
        顯示指定時間區間的 K 棒。
        """

        if ktype != "1m" and ktype != "5m":
            raise NotImplementedError(f"Not implemented: {ktype}")

        if ktype == "1m":
            print("========= 1m ==========")
            kbars = self._kbars
        elif ktype == "5m":
            kbars = self.resample_5m()
            print("========= 5m ==========")

        print(
            f"{'timestamp':<19}  {'open':<8}  {'high':<8}  {'low':<8}  {'close':<8}  {'volume':<7}"
        )

        for kbar in kbars:
            if start <= kbar.timestamp <= end:
                print(
                    f"{kbar.timestamp:%Y-%m-%d %H:%M:%S}  "
                    f"{kbar.open:<8.1f}  "
                    f"{kbar.high:<8.1f}  "
                    f"{kbar.low:<8.1f}  "
                    f"{kbar.close:<8.1f}  "
                    f"{kbar.volume:<7d}"
                )

    def resample_1m(self) -> list[KBar]:
        """
        將指定時間區間的 K 棒重新採樣為 1 分鐘 K 棒。
        """
        return self._kbars

    def resample_5m(self) -> list[KBar]:
        """
        從 1m SSOT 組成已收 5m。
        日盤：08:46～08:50 → 08:50 … 13:41～13:45 → 13:45
        夜盤：15:01～15:05 → 15:05 … 04:56～05:00 → 05:00
        不滿 5 根 1m 不輸出。
        """
        buckets: dict[datetime, list[KBar]] = defaultdict(list)
        for kbar in self._kbars:
            close_ts = _five_min_close(kbar.timestamp)
            if not _is_session_5m_close(close_ts):
                continue
            buckets[close_ts].append(kbar)
        out: list[KBar] = []
        for close_ts in sorted(buckets):
            chunk = sorted(buckets[close_ts], key=lambda b: b.timestamp)
            expected = {close_ts - timedelta(minutes=i) for i in range(5)}
            actual = {b.timestamp.replace(second=0, microsecond=0) for b in chunk}
            if actual != expected:
                continue  # 缺分鐘或重複 → 整根丟掉
            out.append(
                KBar(
                    timestamp=close_ts,
                    open=chunk[0].open,
                    high=max(b.high for b in chunk),
                    low=min(b.low for b in chunk),
                    close=chunk[-1].close,
                    volume=sum(b.volume for b in chunk),
                    amount=sum(b.amount for b in chunk),
                )
            )
        return out
