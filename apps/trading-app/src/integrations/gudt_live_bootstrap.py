"""GUDT Route A live staged bootstrap coordinator (FT-022 Phase 4)."""

from __future__ import annotations

import datetime as dt
import logging
import time
from pathlib import Path
from typing import Any, Literal

from core.runtime_config import RuntimeConfig
from integrations.gudt_replay_planner import build_replay_plans_for_range
from reporting.gap_drive_continuation_counterfactual import (
    _open_0845,
    _prior_close,
    _prior_session_date,
)
from reporting.gudt_wash_probe import (
    DayWashContext,
    WashProbeTuning,
    load_probe_contexts,
    probe_day_rows,
)
from storage.kbar_loader import load_kbars_csv, resolve_kbar_path
from storage.tick_loader import resolve_cli_tick_cache_dates
from strategy_gudt_route_a import GudtRouteAStrategy
from strategy_gudt_route_a.params import GudtRouteAParams
from strategy_gudt_route_a.stack_params import stack_params_from_gudt
from strategy_gudt_route_a.types import DayReplayPlan

logger = logging.getLogger(__name__)

LiveBootstrapState = Literal[
    "Init",
    "AwaitingOpen",
    "AwaitingAtr",
    "AwaitingSignal",
    "PlanReady",
    "NotGudtDay",
    "RouterSkip",
]

AWAITING_ATR_LOG_INTERVAL_SEC = 300.0
EVAL_THROTTLE_SEC = 10.0
ATR_QUALIFY_TIME = dt.time(9, 14)
OPEN_0845_TIME = dt.time(8, 45)


def _ctx_log_suffix(ctx: DayWashContext | None) -> str:
    if ctx is None or not ctx.atr:
        return ""
    ext_open = (ctx.drive_high - ctx.open_0845) / ctx.atr
    return (
        f" gap_pts={ctx.gap_pts:.1f} atr={ctx.atr:.1f}"
        f" ext_open={ext_open:.2f}"
        f" prior_close={ctx.prior_close:.1f}"
    )


class GudtLiveBootstrapCoordinator:
    """Staged GUDT replay plan builder for live sessions (outside engine lock)."""

    def __init__(
        self,
        strategy: GudtRouteAStrategy,
        cfg: RuntimeConfig,
        *,
        code: str,
        cache_dir: Path,
        trade_day: dt.date | None = None,
    ) -> None:
        self.strategy = strategy
        self.cfg = cfg
        self.code = code
        self.cache_dir = cache_dir
        self.trade_day = trade_day or dt.date.today()
        self.day_str = self.trade_day.isoformat()
        self._state: LiveBootstrapState = "Init"
        self._terminal = False
        self._prior_close: float | None = None
        self._ctx: DayWashContext | None = None
        self._last_eval_mono = 0.0
        self._last_awaiting_atr_log_mono = 0.0
        self._last_tick_ts: int | None = None
        self._tuning = WashProbeTuning()

    @property
    def state(self) -> LiveBootstrapState:
        return self._state

    @property
    def terminal(self) -> bool:
        return self._terminal

    def _resolve_sorted_dates(self) -> list[dt.date]:
        pad_from = (self.trade_day - dt.timedelta(days=45)).isoformat()
        try:
            dates = resolve_cli_tick_cache_dates(
                code=self.code,
                cache_dir=self.cache_dir,
                from_date=pad_from,
                to_date=self.day_str,
                explicit=None,
                from_cache=True,
            )
        except ValueError:
            return []
        if self.trade_day not in dates:
            dates = sorted(dates + [self.trade_day])
        return dates

    def start(self) -> None:
        """Run Init → AwaitingOpen (or terminal skip)."""
        sorted_dates = self._resolve_sorted_dates()
        if not sorted_dates:
            self._finish_skip("no_prior_close")
            return
        prior_day = _prior_session_date(self.trade_day, sorted_dates)
        if prior_day is None:
            self._finish_skip("no_prior_close")
            return
        prior_close = _prior_close(self.code, prior_day, cache_dir=self.cache_dir)
        if prior_close is None:
            self._finish_skip("no_prior_close")
            return
        self._prior_close = prior_close
        self._state = "AwaitingOpen"
        logger.info(
            "gudt_live state=AwaitingOpen day=%s prior_close=%.1f",
            self.day_str,
            prior_close,
        )

    def on_shioaji_tick(self, tick: Any) -> None:
        """Called after ``TradingEngine.on_tick`` returns (not under engine lock)."""
        if self._terminal:
            return
        exchange_dt = getattr(tick, "datetime", None)
        if exchange_dt is None:
            return
        self._last_tick_ts = int(exchange_dt.timestamp())
        now = time.monotonic()
        if now - self._last_eval_mono < EVAL_THROTTLE_SEC:
            return
        self._last_eval_mono = now
        self._step(exchange_dt)

    def _local_dt(self, exchange_dt: dt.datetime) -> dt.datetime:
        if exchange_dt.tzinfo is not None:
            return exchange_dt.astimezone().replace(tzinfo=None)
        return exchange_dt

    def _load_today_bars(self) -> list[Any]:
        path = resolve_kbar_path(self.cache_dir, self.code, self.trade_day)
        if path is None:
            return []
        return load_kbars_csv(path)

    def _sorted_dates(self) -> list[dt.date]:
        dates = self._resolve_sorted_dates()
        return dates if dates else [self.trade_day]

    def _maybe_log_awaiting_atr(self) -> None:
        now = time.monotonic()
        if now - self._last_awaiting_atr_log_mono < AWAITING_ATR_LOG_INTERVAL_SEC:
            return
        self._last_awaiting_atr_log_mono = now
        logger.info(
            "gudt_skip day=%s strategy=gudt_route_a skip_reason=awaiting_atr action=wait",
            self.day_str,
        )

    def _finish_skip(
        self,
        skip_reason: str,
        *,
        ctx: DayWashContext | None = None,
        path: str | None = None,
    ) -> None:
        terminal_state: LiveBootstrapState
        if skip_reason == "router_skip":
            terminal_state = "RouterSkip"
        else:
            terminal_state = "NotGudtDay"
        self._state = terminal_state
        self._terminal = True
        suffix = _ctx_log_suffix(ctx)
        path_part = f" path={path}" if path else ""
        logger.info(
            "gudt_skip day=%s strategy=gudt_route_a skip_reason=%s action=skip%s%s",
            self.day_str,
            skip_reason,
            path_part,
            suffix,
        )

    def _step(self, exchange_dt: dt.datetime) -> None:
        local = self._local_dt(exchange_dt)
        if local.date() != self.trade_day:
            return
        clock = local.time()

        if self._state == "AwaitingOpen":
            bars = self._load_today_bars()
            open_0845 = _open_0845(bars) if bars else None
            if open_0845 is not None:
                self._state = "AwaitingAtr"
                logger.info("gudt_live state=AwaitingAtr day=%s open_0845=%.1f", self.day_str, open_0845)
                return
            if clock >= ATR_QUALIFY_TIME:
                self._finish_skip("no_open_0845")
            return

        if self._state == "AwaitingAtr":
            if clock < ATR_QUALIFY_TIME:
                self._maybe_log_awaiting_atr()
                return
            ctx_map = load_probe_contexts(
                self.code,
                [self.day_str],
                cache_dir=self.cache_dir,
                tuning=self._tuning,
            )
            ctx = ctx_map.get(self.day_str)
            if ctx is None:
                self._finish_skip("not_gudt_day")
                return
            self._ctx = ctx
            self._state = "AwaitingSignal"
            logger.info(
                "gudt_live state=AwaitingSignal day=%s gap_pts=%.1f atr=%.1f",
                self.day_str,
                ctx.gap_pts,
                ctx.atr,
            )
            return

        if self._state == "AwaitingSignal":
            self._try_build_plan()

    def _try_build_plan(self) -> None:
        sorted_dates = self._sorted_dates()
        rows = probe_day_rows(
            self.code,
            self.trade_day,
            cache_dir=self.cache_dir,
            sorted_dates=sorted_dates,
            tuning=self._tuning,
        )
        if not rows:
            return
        ctx_by_day = load_probe_contexts(
            self.code,
            [self.day_str],
            cache_dir=self.cache_dir,
            tuning=self._tuning,
        )
        if not ctx_by_day:
            ctx_by_day = {self.day_str: self._ctx} if self._ctx is not None else {}
        params = stack_params_from_gudt(GudtRouteAParams.from_runtime_config(self.cfg))
        plans = build_replay_plans_for_range(rows, ctx_by_day, params=params)
        plan = plans.get(self.day_str)
        if plan is None:
            return
        if plan.skipped or plan.path == "skip":
            self._finish_skip("router_skip", ctx=ctx_by_day.get(self.day_str), path=plan.path)
            return
        self.strategy.apply_intraday_plan(
            self.day_str,
            plan,
            as_of_ts=self._last_tick_ts,
        )
        self._state = "PlanReady"
        self._terminal = True
        logger.info(
            "gudt_live state=PlanReady day=%s path=%s events=%d",
            self.day_str,
            plan.path,
            len(plan.events),
        )


def attach_gudt_live_coordinator(
    strategy: Any,
    cfg: RuntimeConfig,
    *,
    code: str,
    cache_dir: Path,
    trade_day: dt.date | None = None,
) -> GudtLiveBootstrapCoordinator | None:
    if not isinstance(strategy, GudtRouteAStrategy):
        return None
    coord = GudtLiveBootstrapCoordinator(
        strategy=strategy,
        cfg=cfg,
        code=code,
        cache_dir=cache_dir,
        trade_day=trade_day,
    )
    coord.start()
    return coord


def start_live_session(engine: Any, *, coordinator: GudtLiveBootstrapCoordinator | None = None) -> None:
    """Wire optional GUDT coordinator then run Shioaji live bootstrap."""
    from trading_engine.adapters.shioaji_live import ShioajiLiveBootstrap

    boot = ShioajiLiveBootstrap(engine)
    if coordinator is not None:
        original = boot.on_tick_from_shioaji

        def _on_tick_with_coordinator(tick: Any) -> None:
            original(tick)
            coordinator.on_shioaji_tick(tick)

        boot.on_tick_from_shioaji = _on_tick_with_coordinator
    boot.start_live()


__all__ = [
    "GudtLiveBootstrapCoordinator",
    "attach_gudt_live_coordinator",
    "start_live_session",
]
