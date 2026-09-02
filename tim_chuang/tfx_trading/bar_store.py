from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Callable, Literal

from tfx_trading.kbar import KBar

KType = Literal["1m", "5m", "15m", "30m", "1h", "4h", "1d"]
SessionKind = Literal["day", "night"]


def _n_min_close(ts: datetime, n: int) -> datetime:
    """08:46～08:50 → 08:50；08:46～09:00 → 09:00。已在 n 分整點則維持不變。"""
    ts = ts.replace(second=0, microsecond=0)
    remainder = ts.minute % n
    if remainder == 0:
        return ts
    return ts + timedelta(minutes=n - remainder)


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


def is_session_15m_close(ts: datetime) -> bool:
    """合法 15 分 close：日盤 09:00～13:45；夜盤 15:15～05:00。"""
    return ts.minute % 15 == 0 and session_kind(ts) is not None


def is_session_30m_close(ts: datetime) -> bool:
    """合法 30 分 close：日盤 09:15～13:45（:15/:45）；夜盤 15:30～05:00（:00/:30）。"""
    kind = session_kind(ts)
    if kind == "day":
        return ts.minute in (15, 45)
    if kind == "night":
        return ts.minute in (0, 30)
    return False


def is_session_60m_close(ts: datetime) -> bool:
    """合法 60 分 close：日盤 09:45～13:45（:45）；夜盤 16:00～05:00（:00）。"""
    kind = session_kind(ts)
    if kind == "day":
        return ts.minute == 45
    if kind == "night":
        return ts.minute == 0
    return False


def _ceil_from(origin: datetime, ts: datetime, n: int) -> datetime:
    elapsed = int((ts - origin).total_seconds() // 60)
    remainder = elapsed % n
    if remainder == 0:
        return ts
    return origin + timedelta(minutes=elapsed + (n - remainder))


def _session_n_min_close(ts: datetime, n: int) -> datetime | None:
    """
    用錨區間選窗，不能用 session_kind(1m ts)。
    日盤 08:45 < t ≤ 13:45 → 從 08:45 ceil；夜盤 t > 15:00 或 t ≤ 05:00 → 從 15:00 ceil。
    """
    ts = ts.replace(second=0, microsecond=0)
    minutes = ts.hour * 60 + ts.minute
    if 8 * 60 + 45 < minutes <= 13 * 60 + 45:
        origin = ts.replace(hour=8, minute=45)
        return _ceil_from(origin, ts, n)
    if minutes > 15 * 60 or minutes <= 5 * 60:
        if minutes > 15 * 60:
            origin = ts.replace(hour=15, minute=0)
        else:
            origin = (ts - timedelta(days=1)).replace(hour=15, minute=0)
        return _ceil_from(origin, ts, n)
    return None


def _session_30m_bucket(ts: datetime) -> datetime | None:
    close_ts = _session_n_min_close(ts, 30)
    if close_ts is None or not is_session_30m_close(close_ts):
        return None
    return close_ts


def _session_60m_bucket(ts: datetime) -> datetime | None:
    close_ts = _session_n_min_close(ts, 60)
    if close_ts is None or not is_session_60m_close(close_ts):
        return None
    return close_ts


def is_session_complete(kind: SessionKind, last_bar_ts: datetime) -> bool:
    """該段是否已印出合法最後一根（日盤 13:45 / 夜盤 05:00）。1/5/15/30/60m 皆然。"""
    hm = (last_bar_ts.hour, last_bar_ts.minute)
    if kind == "day":
        return hm == (13, 45)
    return hm == (5, 0)


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

        if ktype == "1m":
            kbars = self._kbars
        elif ktype == "5m":
            kbars = self.resample_5m()
        elif ktype == "15m":
            kbars = self.resample_15m()
        elif ktype == "30m":
            kbars = self.resample_30m()
        elif ktype == "1h":
            kbars = self.resample_60m()
        else:
            raise NotImplementedError(f"Not implemented: {ktype}")

        print(f"========= {ktype} ==========")

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
        return self._resample_minutes(5)

    def resample_15m(self) -> list[KBar]:
        """
        從 1m SSOT 組成已收 15m。
        日盤：08:46～09:00 → 09:00 … 13:31～13:45 → 13:45
        夜盤：15:01～15:15 → 15:15 … 04:46～05:00 → 05:00
        不滿 15 根 1m 不輸出。
        """
        return self._resample_minutes(15)

    def resample_30m(self) -> list[KBar]:
        """
        從 1m SSOT 組成已收 30m（session 錨，不是 minute % 30）。
        日盤：08:46～09:15 → 09:15 … 13:16～13:45 → 13:45
        夜盤：15:01～15:30 → 15:30 … 04:31～05:00 → 05:00
        不滿 30 根 1m 不輸出。
        """
        return self._resample_from_close(30, _session_30m_bucket)

    def resample_60m(self) -> list[KBar]:
        """
        從 1m SSOT 組成已收 60m（≡ 1h；session 錨）。
        日盤：08:46～09:45 → 09:45 … 12:46～13:45 → 13:45
        夜盤：15:01～16:00 → 16:00 … 04:01～05:00 → 05:00
        不滿 60 根 1m 不輸出。
        """
        return self._resample_from_close(60, _session_60m_bucket)

    def resample_1h(self) -> list[KBar]:
        return self.resample_60m()

    def _resample_minutes(self, n: int) -> list[KBar]:
        def close_of(ts: datetime) -> datetime | None:
            close_ts = _n_min_close(ts, n)
            if close_ts.minute % n != 0 or session_kind(close_ts) is None:
                return None
            return close_ts

        return self._resample_from_close(n, close_of)

    def _resample_from_close(
        self,
        n: int,
        close_of: Callable[[datetime], datetime | None],
    ) -> list[KBar]:
        buckets: dict[datetime, list[KBar]] = defaultdict(list)
        for kbar in self._kbars:
            close_ts = close_of(kbar.timestamp)
            if close_ts is None:
                continue
            buckets[close_ts].append(kbar)
        out: list[KBar] = []
        for close_ts in sorted(buckets):
            chunk = sorted(buckets[close_ts], key=lambda b: b.timestamp)
            expected = {close_ts - timedelta(minutes=i) for i in range(n)}
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
