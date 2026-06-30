"""FT-018b: GUDT wash grid v2 — entry + exit sweep, single-day streaming."""

from __future__ import annotations

import datetime as dt
import itertools
import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from reporting.armed_forward_counterfactual import FRICTION_POINTS, _summarize_gross_net
from reporting.gudt_wash_probe import (
    ProbeEntry,
    WashProbeTuning,
    _detect_entries,
    _load_day_context,
    _resolve_stop_price,
    classify_wash_label,
    _path_mfe_mae,
    _stop_less,
)
from reporting.simulate_atr_trail_skew_exit import simulate_atr_trail_skew_exit
from storage.tick_loader import resolve_cli_tick_cache_dates

SCHEMA_VERSION = 1
DEFAULT_K_SL = 1.25
DEFAULT_MIN_ATR = 25.0

EntryModeGrid = Literal["p0", "flow_turn", "p0_quality"]
StopMode = Literal["atr", "wash_struct"]
BeMode = Literal["off", "1.0"]


@dataclass(frozen=True)
class GudtWashParams:
    entry_mode: EntryModeGrid
    min_wash_k: float
    delta_br_min: float
    be_trigger: BeMode
    stop_mode: StopMode
    max_hold_sec: int
    trail_arm_atr_k: float
    trail_dist_atr_k: float
    hard_tp_atr_k: float | None
    gap_k_atr: float = 1.0
    retrace_max_frac: float = 0.4
    k_sl: float = DEFAULT_K_SL
    br_min: float = 0.55
    break_eps: float = 0.05

    def key(self) -> str:
        em = self.entry_mode
        mw = f"{self.min_wash_k:g}".replace(".", "p")
        dbr = f"{self.delta_br_min:g}".replace(".", "p")
        be = "off" if self.be_trigger == "off" else "1p0"
        ss = "wash" if self.stop_mode == "wash_struct" else "atr"
        h = self.max_hold_sec
        ta = f"{self.trail_arm_atr_k:g}".replace(".", "p")
        td = f"{self.trail_dist_atr_k:g}".replace(".", "p")
        tp = "none" if self.hard_tp_atr_k is None else f"{self.hard_tp_atr_k:g}".replace(".", "p")
        return f"em_{em}_mw{mw}_dbr{dbr}_be{be}_ss_{ss}_h{h}_ta{ta}_td{td}_tp{tp}"

    def tuning(self) -> WashProbeTuning:
        return WashProbeTuning(
            min_wash_k=self.min_wash_k,
            br_min=self.br_min,
            delta_br_min=self.delta_br_min,
            break_eps=self.break_eps,
            gap_k_atr=self.gap_k_atr,
            retrace_max_frac=self.retrace_max_frac,
        )


def _iter_wash_param_sets() -> list[GudtWashParams]:
    entry_modes: tuple[EntryModeGrid, ...] = ("p0", "flow_turn", "p0_quality")
    min_wash = (0.15, 0.25, 0.35)
    delta_br = (0.08, 0.12, 0.18)
    be_modes: tuple[BeMode, ...] = ("off", "1.0")
    stop_modes: tuple[StopMode, ...] = ("atr", "wash_struct")
    holds = (900, 1800)
    trail_arms = (1.5, 2.0)
    trail_dists = (0.5, 0.6)
    hard_tps: tuple[float | None, ...] = (3.0, None)

    combos: list[GudtWashParams] = []
    for em, mw, dbr, be, sm, hold, ta, td, tp in itertools.product(
        entry_modes,
        min_wash,
        delta_br,
        be_modes,
        stop_modes,
        holds,
        trail_arms,
        trail_dists,
        hard_tps,
    ):
        if em != "flow_turn" and mw != 0.25:
            continue
        if em != "flow_turn" and dbr != 0.12:
            continue
        combos.append(
            GudtWashParams(
                entry_mode=em,
                min_wash_k=mw,
                delta_br_min=dbr,
                be_trigger=be,
                stop_mode=sm,
                max_hold_sec=hold,
                trail_arm_atr_k=ta,
                trail_dist_atr_k=td,
                hard_tp_atr_k=tp,
            )
        )
    return combos


def _pick_entry(entries: list[ProbeEntry], params: GudtWashParams) -> ProbeEntry | None:
    for e in entries:
        if e.entry_mode == params.entry_mode:
            return e
    return None


def _simulate_wash_row(
    entry: ProbeEntry,
    ctx: Any,
    params: GudtWashParams,
    *,
    friction: float = FRICTION_POINTS,
) -> dict[str, Any]:
    be_k: float | None = None if params.be_trigger == "off" else 1.0
    exit_mode = "wash_struct" if params.stop_mode == "wash_struct" else "momentum_tail"
    initial_stop = _resolve_stop_price(entry, ctx, exit_mode) if params.stop_mode == "wash_struct" else None
    sim = simulate_atr_trail_skew_exit(
        direction="Long",
        entry_price=entry.entry_price,
        entry_ts=entry.entry_ts,
        atr=ctx.atr,
        ticks=ctx.ticks,
        hard_stop_atr_k=params.k_sl,
        be_trigger_atr_k=be_k,
        trail_arm_atr_k=params.trail_arm_atr_k,
        trail_dist_atr_k=params.trail_dist_atr_k,
        hard_tp_atr_k=params.hard_tp_atr_k,
        max_hold_sec=params.max_hold_sec,
        min_atr_pts=DEFAULT_MIN_ATR,
        initial_stop_price=initial_stop,
    )
    gross = float(sim["gross_pnl"])
    mfe, mae, dipped = _path_mfe_mae(entry, ctx)
    w15 = _stop_less(entry, ctx, 900)
    w30 = _stop_less(entry, ctx, 1800)
    w60 = _stop_less(entry, ctx, 3600)
    label = classify_wash_label(
        entry=entry,
        ctx=ctx,
        w15=w15,
        w30=w30,
        w60=w60,
        mfe=mfe,
        mae=mae,
        dipped_below_dh=dipped or entry.dip_below_dh,
        friction=friction,
    )
    return {
        "day": ctx.day.isoformat(),
        "param": params.key(),
        "entry_mode": entry.entry_mode,
        "entry_ts": entry.entry_ts,
        "entry_price": round(entry.entry_price, 1),
        "gross_atr_sim": gross,
        "net_atr_sim": round(gross - friction, 2),
        "wash_label": label,
        "w30": round(w30, 2),
        "w60": round(w60, 2),
        "atr_trail_sim": sim,
    }


def build_gudt_wash_grid_payload(
    *,
    code: str,
    from_date: str,
    to_date: str,
    cache_dir: Path,
    friction_points: float = FRICTION_POINTS,
) -> dict[str, Any]:
    dates = resolve_cli_tick_cache_dates(
        code=code,
        cache_dir=cache_dir,
        from_date=from_date,
        to_date=to_date,
        explicit=None,
        from_cache=True,
    )
    param_sets = _iter_wash_param_sets()
    rows_by_param: dict[str, list[dict[str, Any]]] = {p.key(): [] for p in param_sets}

    for day in dates:
        base_ctx = _load_day_context(
            code,
            day,
            cache_dir=cache_dir,
            sorted_dates=dates,
            tuning=WashProbeTuning(),
        )
        if base_ctx is None:
            continue
        entries_by_tuning: dict[tuple[float, float], list[ProbeEntry]] = {}

        for params in param_sets:
            tuning = params.tuning()
            tune_key = (tuning.min_wash_k, tuning.delta_br_min)
            if tune_key not in entries_by_tuning:
                entries_by_tuning[tune_key] = _detect_entries(base_ctx, tuning)
            entries = entries_by_tuning[tune_key]
            entry = _pick_entry(entries, params)
            if entry is None:
                continue
            row = _simulate_wash_row(entry, base_ctx, params, friction=friction_points)
            rows_by_param[params.key()].append(row)

    summary_by_param: dict[str, dict[str, Any]] = {}
    for key, rows in rows_by_param.items():
        if not rows:
            continue
        summary_by_param[key] = _summarize_gross_net(
            "gross_atr_sim", "net_atr_sim", rows
        )

    best_key = None
    best_net = float("-inf")
    for key, s in summary_by_param.items():
        total = float(s.get("net_total", 0))
        if total > best_net:
            best_net = total
            best_key = key

    label_breakdown: dict[str, list[float]] = {}
    if best_key:
        for row in rows_by_param[best_key]:
            lbl = str(row.get("wash_label", "ambiguous"))
            label_breakdown.setdefault(lbl, []).append(float(row["net_atr_sim"]))

    label_summary = {
        lbl: {"n": len(v), "net_mean": round(statistics.mean(v), 2), "net_total": round(sum(v), 2)}
        for lbl, v in label_breakdown.items()
    }

    return {
        "schema_version": SCHEMA_VERSION,
        "thesis": "gudt_wash_grid_v2",
        "from_date": from_date,
        "to_date": to_date,
        "code": code,
        "friction_points": friction_points,
        "param_count": len(param_sets),
        "summary_by_param": summary_by_param,
        "best_param": best_key,
        "best_net_total": round(best_net, 2) if best_key else None,
        "wash_label_breakdown_best": label_summary,
        "rows_by_param": rows_by_param,
        "note": "Exploratory — does not overwrite sealed 432 grid or gate_report.",
    }
