"""Tick skip schedule for GUDT replay backtests (event-anchored wake points)."""

from __future__ import annotations

import datetime as dt
from typing import Any

# MockBroker default latency + IOC single-tick window
LATENCY_CUSHION_SEC = 0.25
_PRE_EVENT_SEC = 0.05


def _combine(day: dt.date, t: dt.time) -> dt.datetime:
    return dt.datetime.combine(day, t)


def _plan_events(plan: Any) -> list[Any]:
    if plan is None:
        return []
    if isinstance(plan, dict):
        if plan.get("skipped"):
            return []
        return list(plan.get("events") or [])
    if getattr(plan, "skipped", False):
        return []
    return list(getattr(plan, "events", None) or [])


def build_day_anchor_ts(
    day: dt.date,
    plan: dict[str, Any] | Any | None,
    *,
    session_start: dt.time,
    session_end: dt.time,
    session_flatten: dt.time,
    force_flatten: dt.time,
) -> list[float]:
    """Sorted epoch seconds that must be visited for one session day."""
    anchors: list[float] = []
    for t in (session_start, session_flatten, force_flatten, session_end):
        anchors.append(_combine(day, t).timestamp())
    for ev in _plan_events(plan):
        ts = float(ev["ts"] if isinstance(ev, dict) else ev.ts)
        anchors.extend((ts - _PRE_EVENT_SEC, ts, ts + LATENCY_CUSHION_SEC))
    return sorted(set(anchors))


class GudtReplayJump:
    """Skip idle ticks between GUDT plan anchors; never skip while orders are active."""

    def __init__(
        self,
        day_plans: dict[str, Any],
        *,
        session_start: dt.time,
        session_end: dt.time,
        session_flatten: dt.time,
        force_flatten: dt.time,
    ) -> None:
        self._day_plans = day_plans
        self._session_start = session_start
        self._session_end = session_end
        self._session_flatten = session_flatten
        self._force_flatten = force_flatten
        self._current_day: str | None = None
        self._anchors: list[float] = []
        self._wake_ts = 0.0
        self.skipped_ticks = 0
        self.processed_ticks = 0

    def _ensure_day(self, day_str: str) -> None:
        if day_str == self._current_day:
            return
        self._current_day = day_str
        day = dt.date.fromisoformat(day_str)
        plan = self._day_plans.get(day_str)
        self._anchors = build_day_anchor_ts(
            day,
            plan,
            session_start=self._session_start,
            session_end=self._session_end,
            session_flatten=self._session_flatten,
            force_flatten=self._force_flatten,
        )
        self._wake_ts = self._anchors[0] if self._anchors else 0.0

    def set_active(self, active: bool) -> None:
        if active:
            self._wake_ts = 0.0

    def should_skip(self, tick_ts: float, day_str: str) -> bool:
        if self._wake_ts <= 0.0:
            return False
        self._ensure_day(day_str)
        if tick_ts < self._wake_ts - 1e-6:
            self.skipped_ticks += 1
            return True
        return False

    def on_tick_processed(self, tick_ts: float, day_str: str, *, idle: bool) -> None:
        self.processed_ticks += 1
        if not idle:
            self._wake_ts = 0.0
            return
        self._ensure_day(day_str)
        self._wake_ts = self._next_wake_after(tick_ts)

    def _next_wake_after(self, ts: float) -> float:
        for anchor in self._anchors:
            if anchor > ts + 1e-6:
                return max(ts, anchor - LATENCY_CUSHION_SEC)
        return float("inf")


def maybe_gudt_jump(
    strategy: Any,
    cfg: Any,
) -> GudtReplayJump | None:
    day_plans = getattr(strategy, "_day_plans", None)
    if not day_plans:
        return None
    return GudtReplayJump(
        day_plans,
        session_start=cfg.session_start,
        session_end=cfg.session_end,
        session_flatten=cfg.session_flatten_time,
        force_flatten=cfg.session_force_flatten_time,
    )


def host_needs_reconcile(host: Any) -> bool:
    """Live safety loops only needed when execution state is non-trivial."""
    if host.is_pending or host._settling or host._kernel_converging:
        return True
    if getattr(host, "_stop_market_flatten_request", False):
        return True
    if host.has_position:
        return True
    return False


__all__ = [
    "GudtReplayJump",
    "build_day_anchor_ts",
    "host_needs_reconcile",
    "maybe_gudt_jump",
]
