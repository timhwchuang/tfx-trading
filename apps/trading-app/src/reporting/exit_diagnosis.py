"""FT-003 Phase 3.6: exit diagnosis from baseline backtest report + log."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from reporting.near_miss_aggregate import aggregate_near_miss
from reporting.volatility_baseline import percentile

FRICTION_FOOTNOTE = (
    "§D.2 為 **毛點**（gross）；TMFR1 摩擦 **5 點/趟** 見 "
    "[`SHARED_ASSUMPTIONS.md`](SHARED_ASSUMPTIONS.md) §3.1。"
)
IN_GRACE_FOOTNOTE = (
    "`in_grace` 期間 **hard stop 仍會觸發**（保護期內不啟用 VWAP 停損）；"
    "此占比為 exit audit 中 `reason=stop_loss` 且 `in_grace=true` 的比例。"
)


def _format_rate(rate: float | None) -> str:
    if rate is None:
        return "—"
    return f"{rate * 100:.1f}%"


def _resolve_near_miss(report: dict[str, Any]) -> dict[str, Any]:
    daily = report.get("daily_summaries") or []
    if daily:
        aggregated = aggregate_near_miss(daily)
        if aggregated:
            return aggregated
    return dict(report.get("near_miss") or {})


def _integrity_warnings(report: dict[str, Any], reason_rows: list[dict]) -> list[str]:
    warnings: list[str] = []
    exit_reasons = report.get("exit_reasons") or {}
    exp_by = report.get("expectancy_by_reason") or {}
    for row in reason_rows:
        reason = row["reason"]
        er_count = int(exit_reasons.get(reason, 0))
        exp_count = exp_by.get(reason, {}).get("count")
        if exp_count is not None and int(exp_count) != er_count:
            warnings.append(
                f"exit_reasons[{reason!r}]={er_count} vs "
                f"expectancy_by_reason.count={exp_count}"
            )
    return warnings


def diagnose_report(report: dict[str, Any]) -> dict[str, Any]:
    exit_reasons = report.get("exit_reasons") or {}
    total_exits = sum(int(v) for v in exit_reasons.values()) or 1
    reason_rows = [
        {
            "reason": k,
            "count": int(v),
            "pct": round(100.0 * int(v) / total_exits, 1),
        }
        for k, v in sorted(exit_reasons.items(), key=lambda x: -x[1])
    ]
    exp_by = report.get("expectancy_by_reason") or {}
    exp_rows = [
        {
            "reason": k,
            "count": v.get("count"),
            "total_pnl": v.get("total_pnl"),
            "avg_pnl": v.get("avg_pnl"),
        }
        for k, v in exp_by.items()
    ]
    near_miss = _resolve_near_miss(report)
    return {
        "completed_rounds": report.get("completed_rounds"),
        "quick_stop_loss_rate": report.get("quick_stop_loss_rate_lt_5s"),
        "exit_reasons": reason_rows,
        "expectancy_by_reason": exp_rows,
        "near_miss": near_miss,
        "integrity_warnings": _integrity_warnings(report, reason_rows),
    }


def parse_exit_audits_from_log(log_path: Path) -> dict[str, Any]:
    hold_ticks: list[int] = []
    stop_in_grace = 0
    stop_total = 0
    malformed = 0
    pattern = re.compile(r"SIGNAL_AUDIT (\{.*\})")
    with log_path.open(encoding="utf-8", errors="replace") as f:
        for line in f:
            if '"intent":"exit"' not in line and '"intent": "exit"' not in line:
                continue
            m = pattern.search(line)
            if not m:
                continue
            try:
                audit = json.loads(m.group(1))
            except json.JSONDecodeError:
                malformed += 1
                continue
            ht = int(audit.get("hold_ticks") or 0)
            hold_ticks.append(ht)
            reason = str(audit.get("reason") or "")
            if reason == "stop_loss":
                stop_total += 1
                if audit.get("in_grace"):
                    stop_in_grace += 1
    hold_sorted = sorted(hold_ticks)
    return {
        "exit_audit_count": len(hold_ticks),
        "hold_ticks_p50": percentile(hold_sorted, 0.5) if hold_sorted else None,
        "stop_loss_in_grace_pct": (
            round(100.0 * stop_in_grace / stop_total, 1) if stop_total else None
        ),
        "stop_loss_count": stop_total,
        "malformed_audit_lines": malformed,
    }


def render_exit_section(
    agent: str,
    report_path: Path,
    diagnosis: dict[str, Any],
    log_stats: dict[str, Any] | None,
) -> str:
    lines = [
        f"**Agent / report**：`{agent}` / `{report_path.as_posix()}`",
        "",
        "### D.1 Exit reason 占比",
        "",
        "| reason | count | % |",
        "|--------|-------|---|",
    ]
    for row in diagnosis["exit_reasons"]:
        lines.append(f"| {row['reason']} | {row['count']} | {row['pct']}% |")
    lines.extend(
        [
            "",
            "### D.2 Expectancy by reason（毛點）",
            "",
            f"> {FRICTION_FOOTNOTE}",
            "",
            "| reason | count | total_pnl | avg_pnl |",
            "|--------|-------|-----------|---------|",
        ]
    )
    for row in diagnosis["expectancy_by_reason"]:
        lines.append(
            f"| {row['reason']} | {row['count']} | {row['total_pnl']} | {row['avg_pnl']} |"
        )
    warnings = diagnosis.get("integrity_warnings") or []
    if warnings:
        lines.extend(["", "**Integrity warnings**："])
        for w in warnings:
            lines.append(f"- {w}")

    lines.extend(["", "### D.3 秒停損與 hold_ticks", "", "| 指標 | 值 |", "|------|-----|"])
    qsl = diagnosis.get("quick_stop_loss_rate")
    lines.append(f"| quick_stop_loss_rate | {_format_rate(qsl)} |")
    if log_stats:
        grace_pct = log_stats.get("stop_loss_in_grace_pct")
        grace_display = f"{grace_pct}%" if grace_pct is not None else "—"
        lines.append(f"| stop_loss in_grace 占比 | {grace_display} |")
        lines.append(f"| hold_ticks p50（exit audit） | {log_stats.get('hold_ticks_p50', '—')} |")
        if log_stats.get("malformed_audit_lines"):
            lines.append(f"| malformed exit audit lines | {log_stats['malformed_audit_lines']} |")
    lines.extend(["", f"> {IN_GRACE_FOOTNOTE}"])

    nm = diagnosis.get("near_miss") or {}
    lines.extend(["", "### D.4 Near-miss 漏斗", ""])
    agg_days = nm.get("_aggregated_from_days")
    if agg_days:
        lines.append(f"（跨 **{agg_days}** 個交易日加總；非最後一日 snapshot）")
    lines.extend(["", "| 指標 | 值 |", "|------|-----|"])
    for key in (
        "momentum_episodes",
        "momentum_timeout",
        "blocked_both",
        "blocked_vwap_only",
        "blocked_vol_only",
        "closest_vwap_distance",
    ):
        if key in nm:
            lines.append(f"| {key} | {nm[key]} |")
    return "\n".join(lines) + "\n"


def merge_exit_into_markdown(markdown_path: Path, exit_section: str, *, agent: str) -> None:
    """Append or replace one agent block inside section D."""
    text = markdown_path.read_text(encoding="utf-8")
    marker = "## D. 出場診斷（P0 — baseline valid）"
    if marker not in text:
        raise ValueError(f"{markdown_path}: missing section D marker")
    start = text.index(marker)
    rest = text[start:]
    d_end = rest.find("\n---\n", len(marker))
    if d_end < 0:
        raise ValueError(f"{markdown_path}: cannot find end of section D")
    d_body = rest[len(marker) : d_end].strip()
    agent_hdr = f"**Agent / report**：`{agent}` /"
    if agent_hdr in d_body:
        a_start = d_body.index(agent_hdr)
        next_agent = d_body.find("\n\n**Agent / report**：`", a_start + 1)
        if next_agent < 0:
            d_body = d_body[:a_start].rstrip() + "\n\n" + exit_section.strip()
        else:
            d_body = (
                d_body[:a_start].rstrip()
                + "\n\n"
                + exit_section.strip()
                + "\n\n"
                + d_body[next_agent + 2 :].lstrip()
            )
    elif d_body.startswith("（由 `ft003_exit_diagnosis.py` 填入）"):
        d_body = exit_section.strip()
    else:
        d_body = d_body.rstrip() + "\n\n" + exit_section.strip()
    new_rest = marker + "\n\n" + d_body + "\n" + rest[d_end:]
    markdown_path.write_text(text[:start] + new_rest, encoding="utf-8")
