"""Shared metric extraction from UAT JSON reports."""

from __future__ import annotations

from typing import Any


def log_daily_pnl(data: dict) -> float | None:
    summaries = data.get("daily_summaries") or []
    if summaries:
        pnl = (summaries[-1].get("pnl") or {}).get("daily_pnl_points")
        if pnl is not None:
            return float(pnl)
    perf = data.get("performance") or {}
    if perf.get("total_pnl_net") is not None:
        return float(perf["total_pnl_net"])
    return None


def type0_pct(data: dict) -> float | None:
    tick = data.get("tick_type") or {}
    if tick.get("type0_pct") is not None:
        return float(tick["type0_pct"])
    summaries = data.get("daily_summaries") or []
    if summaries:
        operational = summaries[-1].get("operational") or {}
        if operational.get("tick_type0_pct") is not None:
            return float(operational["tick_type0_pct"])
    return None


def daily_pnl_series(reports: list[tuple[str, dict]]) -> list[tuple[str, float]]:
    series: list[tuple[str, float]] = []
    for date, data in reports:
        pnl = log_daily_pnl(data)
        if pnl is not None:
            series.append((date, pnl))
    return series


def per_trade_return_series(reports: list[tuple[str, dict]]) -> list[float]:
    """Approximate per-trade net returns from daily expectancy × round count."""
    returns: list[float] = []
    for _date, data in reports:
        rounds = int(data.get("completed_rounds") or 0)
        exp = (data.get("performance") or {}).get("expectancy") or {}
        exp_net = exp.get("expectancy_per_trade_net")
        if rounds > 0 and exp_net is not None:
            returns.extend([float(exp_net)] * rounds)
    return returns


def parse_optional_float(raw: str) -> tuple[float | None, str | None]:
    text = (raw or "").strip()
    if not text:
        return None, None
    try:
        return float(text), None
    except ValueError:
        return None, f"invalid broker_daily_pnl_pts: {text!r}"