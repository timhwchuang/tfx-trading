"""CF day_plan vs kernel FILL_AUDIT execution comparison (FT-021 UAT)."""

from __future__ import annotations

import datetime as dt
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from observability import FillAudit
from reporting.date_slices import DateRange, day_in_date_range
from reporting.uat_report import build_trade_rounds_from_fills, parse_log_audits_and_fills, read_log_lines

EXIT_REASON_ALIASES: dict[str, str] = {
    "session_force_flatten": "session_force_flatten",
    "flatten": "session_force_flatten",
    "trail_stop": "trail_stop",
    "stop_loss": "stop_loss",
    "take_profit": "take_profit",
    "horizon": "horizon",
    "breakeven": "breakeven",
    "dist_signal": "dist_signal",
    "short_exit": "short_exit",
}


def normalize_exit_reason(reason: str) -> str:
    r = (reason or "").strip().lower()
    return EXIT_REASON_ALIASES.get(r, r or "unknown")


@dataclass
class PlannedRound:
    day: str
    seq: int
    path: str
    direction: str  # Long | Short
    entry_ts: int
    entry_px: float
    entry_reason: str
    exit_ts: int
    exit_px: float
    exit_reason: str
    planned_gross: float

    @property
    def round_id(self) -> str:
        return f"{self.day}#{self.seq}"


@dataclass
class KernelRound:
    day: str
    seq: int
    entry_ts: int
    entry_px: float
    exit_ts: int | None
    exit_px: float | None
    exit_reason: str
    gross_pnl: float

    @property
    def round_id(self) -> str:
        return f"{self.day}#{self.seq}"


@dataclass
class RoundComparison:
    day: str
    seq: int
    path: str
    direction: str
    entry_px_delta: float | None
    entry_ts_delta_sec: int | None
    exit_reason_plan: str
    exit_reason_kernel: str
    exit_reason_match: bool
    exit_px_delta: float | None
    planned_gross: float
    kernel_gross: float | None
    leg_pnl_delta: float | None
    exit_mechanism: str


@dataclass
class ExecutionCompareResult:
    slice_label: str
    from_date: str
    to_date: str
    months: list[str]
    cf_round_count: int
    kernel_round_count: int
    cf_net: float
    kernel_net_gross: float
    net_delta: float
    n_entry_slip_gt_1pt: int
    n_exit_reason_mismatch: int
    n_flatten_substitute: int
    leg_count_mismatches: list[dict[str, Any]] = field(default_factory=list)
    day_mismatches: list[dict[str, Any]] = field(default_factory=list)
    rounds: list[RoundComparison] = field(default_factory=list)
    exit_reason_histogram: dict[str, dict[str, int]] = field(default_factory=dict)
    failures: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "slice_label": self.slice_label,
            "from": self.from_date,
            "to": self.to_date,
            "months": self.months,
            "summary": {
                "cf_round_count": self.cf_round_count,
                "kernel_round_count": self.kernel_round_count,
                "cf_net": self.cf_net,
                "kernel_net_gross": self.kernel_net_gross,
                "net_delta": self.net_delta,
                "n_entry_slip_gt_1pt": self.n_entry_slip_gt_1pt,
                "n_exit_reason_mismatch": self.n_exit_reason_mismatch,
                "n_flatten_substitute": self.n_flatten_substitute,
            },
            "exit_reason_histogram": self.exit_reason_histogram,
            "leg_count_mismatches": self.leg_count_mismatches,
            "day_mismatches": self.day_mismatches,
            "rounds": [asdict(r) for r in self.rounds],
            "failures": self.failures,
            "warnings": self.warnings,
            "pass": len(self.failures) == 0,
        }


def _in_range(day: str, from_date: str, to_date: str) -> bool:
    return from_date <= day <= to_date


def _direction_from_entry_leg(leg: str) -> str:
    return "Short" if leg.startswith("short") else "Long"


def _gross_pnl(direction: str, entry_px: float, exit_px: float) -> float:
    if direction == "Short":
        return round(entry_px - exit_px, 2)
    return round(exit_px - entry_px, 2)


def build_planned_rounds(
    day_plans: dict[str, Any],
    *,
    date_range: DateRange,
    cf_picks: dict[str, dict[str, Any]] | None = None,
) -> list[PlannedRound]:
    """Pair plan events into round-trips (long and short legs)."""
    rounds: list[PlannedRound] = []
    cf_picks = cf_picks or {}
    for day in sorted(day_plans):
        if not day_in_date_range(day, date_range):
            continue
        plan = day_plans[day]
        if plan.get("skipped") or not plan.get("events"):
            continue
        path = str(plan.get("path", ""))
        events = plan["events"]
        open_entry: dict[str, Any] | None = None
        seq = 0
        for ev in events:
            leg = str(ev.get("leg", ""))
            if leg.endswith("_entry"):
                open_entry = ev
            elif leg.endswith("_exit") and open_entry is not None:
                direction = _direction_from_entry_leg(leg)
                entry_px = float(open_entry["price"])
                exit_px = float(ev["price"])
                rounds.append(
                    PlannedRound(
                        day=day,
                        seq=seq,
                        path=path,
                        direction=direction,
                        entry_ts=int(open_entry["ts"]),
                        entry_px=entry_px,
                        entry_reason=str(open_entry.get("reason", "")),
                        exit_ts=int(ev["ts"]),
                        exit_px=exit_px,
                        exit_reason=str(ev.get("reason", "")),
                        planned_gross=_gross_pnl(direction, entry_px, exit_px),
                    )
                )
                seq += 1
                open_entry = None
    # attach CF pick net for summary cross-check
    del cf_picks  # reserved for future per-day meta
    return rounds


def _fill_day(fill: FillAudit) -> str:
    return dt.datetime.fromtimestamp(fill.ts).date().isoformat()


def build_kernel_rounds(
    fills: list[FillAudit],
    *,
    date_range: DateRange,
) -> list[KernelRound]:
    filtered = [f for f in fills if day_in_date_range(_fill_day(f), date_range)]
    by_day: dict[str, list[FillAudit]] = {}
    for f in filtered:
        by_day.setdefault(_fill_day(f), []).append(f)
    rounds: list[KernelRound] = []
    for day in sorted(by_day):
        day_fills = sorted(by_day[day], key=lambda x: x.ts)
        trade_rounds = build_trade_rounds_from_fills(day_fills)
        for seq, tr in enumerate(trade_rounds):
            if tr.exit_ts is None:
                continue
            entry_fill = next(
                (f for f in day_fills if f.intent == "entry" and f.ts == tr.entry_ts),
                None,
            )
            exit_fill = next(
                (f for f in day_fills if f.intent == "exit" and f.ts == tr.exit_ts),
                None,
            ) if tr.exit_ts else None
            rounds.append(
                KernelRound(
                    day=day,
                    seq=seq,
                    entry_ts=tr.entry_ts,
                    entry_px=entry_fill.fill_price if entry_fill else 0.0,
                    exit_ts=tr.exit_ts,
                    exit_px=exit_fill.fill_price if exit_fill else None,
                    exit_reason=tr.exit_reason or (exit_fill.exit_reason if exit_fill else ""),
                    gross_pnl=exit_fill.pnl_points if exit_fill else 0.0,
                )
            )
    return rounds


def _classify_exit_mechanism(plan_reason: str, kernel_reason: str, exit_px_delta: float | None) -> str:
    pn = normalize_exit_reason(plan_reason)
    kn = normalize_exit_reason(kernel_reason)
    if pn == kn:
        return "match"
    if kn == "session_force_flatten" and pn != "session_force_flatten":
        return "flatten_substitute"
    if exit_px_delta is not None and abs(exit_px_delta) > 1.0:
        return "price_mismatch"
    return "reason_mismatch"


def compare_execution(
    day_plans: dict[str, Any],
    log_path: Path,
    *,
    date_range: DateRange,
    cf_picks: list[dict[str, Any]] | None = None,
) -> ExecutionCompareResult:
    from_date = date_range.from_date
    to_date = date_range.to_date
    picks_by_day = {p["day"]: p for p in (cf_picks or []) if "day" in p}

    planned = build_planned_rounds(
        day_plans, date_range=date_range, cf_picks=picks_by_day
    )
    lines = read_log_lines([log_path]) if log_path.is_file() else []
    _audits, fills = parse_log_audits_and_fills(lines)
    kernel = build_kernel_rounds(fills, date_range=date_range)

    result = ExecutionCompareResult(
        slice_label=date_range.label,
        from_date=from_date,
        to_date=to_date,
        months=list(date_range.months),
        cf_round_count=len(planned),
        kernel_round_count=len(kernel),
        cf_net=round(sum(p.planned_gross for p in planned), 2),
        kernel_net_gross=round(sum(k.gross_pnl for k in kernel), 2),
        net_delta=0.0,
        n_entry_slip_gt_1pt=0,
        n_exit_reason_mismatch=0,
        n_flatten_substitute=0,
    )
    result.net_delta = round(result.kernel_net_gross - result.cf_net, 2)

    plan_by_day: dict[str, list[PlannedRound]] = {}
    for p in planned:
        plan_by_day.setdefault(p.day, []).append(p)
    kern_by_day: dict[str, list[KernelRound]] = {}
    for k in kernel:
        kern_by_day.setdefault(k.day, []).append(k)

    all_days = sorted(set(plan_by_day) | set(kern_by_day))
    for day in all_days:
        if day not in plan_by_day:
            result.day_mismatches.append({"day": day, "reason": "kernel_only"})
        elif day not in kern_by_day:
            result.day_mismatches.append({"day": day, "reason": "plan_only"})

    for day in sorted(set(plan_by_day) & set(kern_by_day)):
        pl = plan_by_day[day]
        kr = kern_by_day[day]
        if len(pl) != len(kr):
            result.leg_count_mismatches.append(
                {"day": day, "planned": len(pl), "kernel": len(kr)}
            )

    hist_plan: dict[str, int] = {}
    hist_kernel: dict[str, int] = {}

    all_days = sorted(set(plan_by_day) | set(kern_by_day))
    for day in all_days:
        pl = plan_by_day.get(day, [])
        kr = kern_by_day.get(day, [])
        max_len = max(len(pl), len(kr), 1) if (pl or kr) else 0
        for seq in range(max_len):
            pr = pl[seq] if seq < len(pl) else None
            k_round = kr[seq] if seq < len(kr) else None
            if pr is None and k_round is None:
                continue
            if pr is None and k_round is not None:
                kn = normalize_exit_reason(k_round.exit_reason)
                hist_kernel[kn] = hist_kernel.get(kn, 0) + 1
                result.rounds.append(
                    RoundComparison(
                        day=day,
                        seq=seq,
                        path="?",
                        direction="?",
                        entry_px_delta=None,
                        entry_ts_delta_sec=None,
                        exit_reason_plan="",
                        exit_reason_kernel=k_round.exit_reason,
                        exit_reason_match=False,
                        exit_px_delta=None,
                        planned_gross=0.0,
                        kernel_gross=k_round.gross_pnl,
                        leg_pnl_delta=None,
                        exit_mechanism="extra_kernel_round",
                    )
                )
                continue
            assert pr is not None
            entry_px_delta = None
            entry_ts_delta = None
            exit_px_delta = None
            kernel_gross = None
            leg_pnl_delta = None
            k_reason = ""
            mechanism = "missing_kernel"
            reason_match = False
            if k_round is not None:
                entry_px_delta = round(k_round.entry_px - pr.entry_px, 2)
                entry_ts_delta = k_round.entry_ts - pr.entry_ts
                k_reason = k_round.exit_reason
                if k_round.exit_px is not None:
                    exit_px_delta = round(k_round.exit_px - pr.exit_px, 2)
                kernel_gross = k_round.gross_pnl
                leg_pnl_delta = round(k_round.gross_pnl - pr.planned_gross, 2)
                reason_match = normalize_exit_reason(pr.exit_reason) == normalize_exit_reason(
                    k_reason
                )
                mechanism = _classify_exit_mechanism(pr.exit_reason, k_reason, exit_px_delta)
                if entry_px_delta is not None and abs(entry_px_delta) > 1.0:
                    result.n_entry_slip_gt_1pt += 1
                if not reason_match:
                    result.n_exit_reason_mismatch += 1
                if mechanism == "flatten_substitute":
                    result.n_flatten_substitute += 1

            pn = normalize_exit_reason(pr.exit_reason)
            kn = normalize_exit_reason(k_reason) if k_reason else "missing"
            hist_plan[pn] = hist_plan.get(pn, 0) + 1
            hist_kernel[kn] = hist_kernel.get(kn, 0) + 1

            result.rounds.append(
                RoundComparison(
                    day=pr.day,
                    seq=pr.seq,
                    path=pr.path,
                    direction=pr.direction,
                    entry_px_delta=entry_px_delta,
                    entry_ts_delta_sec=entry_ts_delta,
                    exit_reason_plan=pr.exit_reason,
                    exit_reason_kernel=k_reason,
                    exit_reason_match=reason_match,
                    exit_px_delta=exit_px_delta,
                    planned_gross=pr.planned_gross,
                    kernel_gross=kernel_gross,
                    leg_pnl_delta=leg_pnl_delta,
                    exit_mechanism=mechanism,
                )
            )

    result.exit_reason_histogram = {"plan": hist_plan, "kernel": hist_kernel}

    if result.cf_round_count != result.kernel_round_count:
        result.failures.append(
            f"round_count mismatch: cf={result.cf_round_count} kernel={result.kernel_round_count}"
        )
    if result.leg_count_mismatches:
        result.failures.append(f"leg_count_mismatches={len(result.leg_count_mismatches)}")
    if result.day_mismatches:
        result.failures.append(f"day_mismatches={len(result.day_mismatches)}")
    if abs(result.net_delta) > 0:
        result.warnings.append(f"net_delta={result.net_delta} (warn-only)")

    return result


def format_net_compare_line(result: ExecutionCompareResult) -> str:
    s = result.to_dict()["summary"]
    status = "PASS" if not result.failures else "FAIL"
    return (
        f"NET_COMPARE | {result.slice_label} | "
        f"cf={s['cf_net']} kernel={s['kernel_net_gross']} delta={s['net_delta']} | "
        f"n={s['cf_round_count']}/{s['kernel_round_count']} | {status}"
    )


def append_spot_check_log(
    log_path: Path,
    *,
    date_label: str,
    command: str,
    result: ExecutionCompareResult,
) -> None:
    """Append one row to SPOT_CHECK_LOG.md (creates header if missing)."""
    s = result.to_dict()["summary"]
    status = "PASS" if not result.failures else "FAIL"
    months = ",".join(result.months) if result.months else date_label
    row = (
        f"| {dt.date.today().isoformat()} | `{command}` | {months} | "
        f"{s['cf_round_count']}/{s['kernel_round_count']} | "
        f"cf={s['cf_net']} kernel={s['kernel_net_gross']} Δ={s['net_delta']} | "
        f"{status} | |"
    )
    if not log_path.is_file():
        log_path.write_text(
            "# GUDT execution parity — spot-check log\n\n"
            "| Date run | Command | Months | n (CF/kernel) | Net (cf / kernel / Δ) | PASS/FAIL | Notes |\n"
            "|----------|---------|--------|---------------|------------------------|-----------|-------|\n",
            encoding="utf-8",
        )
    text = log_path.read_text(encoding="utf-8")
    log_path.write_text(text.rstrip() + "\n" + row + "\n", encoding="utf-8")


def write_execution_report_json(path: Path, result: ExecutionCompareResult) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result.to_dict(), indent=2), encoding="utf-8")


def write_execution_report_md(path: Path, result: ExecutionCompareResult) -> None:
    lines = [
        f"# GUDT Execution Parity — {result.slice_label}",
        "",
        f"**Period:** {result.from_date} … {result.to_date}",
    ]
    if result.months:
        lines.append(f"**Months:** {', '.join(result.months)}")
    s = result.to_dict()["summary"]
    lines.extend(
        [
            "",
            "## Net compare (CF plan vs kernel fills)",
            "",
            f"- **CF plan gross:** {s['cf_net']} pts",
            f"- **Kernel gross:** {s['kernel_net_gross']} pts",
            f"- **Delta (kernel − CF):** {s['net_delta']} pts",
            "",
            "## Summary",
            "",
            f"| Metric | CF plan | Kernel |",
            f"|--------|--------:|-------:|",
            f"| Round-trips (n) | {s['cf_round_count']} | {s['kernel_round_count']} |",
            f"| Net gross (pts) | {s['cf_net']} | {s['kernel_net_gross']} |",
            f"| Net delta | | {s['net_delta']} |",
            f"| Entry slip >1pt | {s['n_entry_slip_gt_1pt']} | |",
            f"| Exit reason mismatch | {s['n_exit_reason_mismatch']} | |",
            f"| Flatten substitute | {s['n_flatten_substitute']} | |",
            "",
            f"**PASS:** {result.to_dict()['pass']}",
        ]
    )
    if result.failures:
        lines.extend(["", "### Failures", ""] + [f"- {f}" for f in result.failures])
    if result.warnings:
        lines.extend(["", "### Warnings", ""] + [f"- {w}" for w in result.warnings])

    lines.extend(["", "## Per round", "", "| day | seq | path | entry Δpx | exit plan | exit kernel | exit Δpx | plan PnL | kernel PnL | ΔPnL | mechanism |", "|-----|-----|------|----------|-----------|-------------|----------|----------|------------|------|-----------|"])
    for r in result.rounds:
        lines.append(
            f"| {r.day} | {r.seq} | {r.path} | {r.entry_px_delta} | {r.exit_reason_plan} | {r.exit_reason_kernel} | {r.exit_px_delta} | {r.planned_gross} | {r.kernel_gross} | {r.leg_pnl_delta} | {r.exit_mechanism} |"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
