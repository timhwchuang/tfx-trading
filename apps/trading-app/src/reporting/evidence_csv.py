"""Read and validate UAT evidence CSV files (broker / tick stratification)."""

from __future__ import annotations

import csv
from pathlib import Path

from reporting.metrics_extract import parse_optional_float

BROKER_COLUMNS = [
    "date",
    "broker_daily_pnl_pts",
    "log_daily_pnl_points",
    "diff_pts",
    "round_trips",
    "broker_source_note",
    "explained_y_or_n",
    "explanation",
]

TICK_COLUMNS = [
    "date",
    "type0_pct",
    "tier",
    "signal_intents",
    "fills",
    "conversion_pct",
    "expectancy_gross_pts",
    "expectancy_net_pts",
    "notes",
]

BROKER_DIFF_REVIEW_THRESHOLD = 0.5
VALID_TICK_TIERS = frozenset({"low_lt30", "mid_30_40", "high_gt40"})


def read_evidence_csv(path: Path, columns: list[str]) -> dict[str, dict[str, str]]:
    if not path.is_file():
        return {}
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        rows: dict[str, dict[str, str]] = {}
        for row in reader:
            date = (row.get("date") or "").strip()
            if not date or date.startswith("YYYY"):
                continue
            rows[date] = {col: (row.get(col) or "").strip() for col in columns}
        return rows


def evaluate_broker_reconciliation_csv(
    path: Path | None,
    *,
    expected_dates: set[str] | None = None,
    diff_threshold: float = BROKER_DIFF_REVIEW_THRESHOLD,
) -> tuple[bool, str]:
    if path is None or not path.is_file():
        return False, f"找不到 broker CSV：{path or '(未指定)'}"

    rows = read_evidence_csv(path, BROKER_COLUMNS)
    if not rows:
        return False, f"broker CSV 無資料列：{path}"

    issues: list[str] = []
    checked_dates = expected_dates or set(rows)
    for date in sorted(checked_dates):
        row = rows.get(date)
        if row is None:
            issues.append(f"{date}: 缺列")
            continue

        broker_raw = row.get("broker_daily_pnl_pts", "")
        if not broker_raw:
            issues.append(f"{date}: 缺 broker_daily_pnl_pts")
            continue

        _, parse_err = parse_optional_float(broker_raw)
        if parse_err:
            issues.append(f"{date}: {parse_err}")
            continue

        explained = (row.get("explained_y_or_n") or "").upper()
        diff_raw = row.get("diff_pts", "")
        diff_val, diff_err = parse_optional_float(diff_raw)
        if diff_err:
            issues.append(f"{date}: invalid diff_pts")
            continue

        if explained == "Y":
            continue
        if explained == "N" and row.get("explanation"):
            continue
        if diff_val is not None and abs(diff_val) <= diff_threshold:
            issues.append(f"{date}: |diff|={diff_val}≤{diff_threshold} 但未標 explained=Y")
        else:
            issues.append(
                f"{date}: diff={diff_raw or '?'} 未解釋（需 explained=Y/N + explanation）"
            )

    if issues:
        return False, "; ".join(issues[:8]) + ("..." if len(issues) > 8 else "")
    return True, f"{len(checked_dates)} 日對帳列已審閱"


def evaluate_tick_stratification_csv(
    path: Path | None,
    *,
    expected_dates: set[str] | None = None,
    min_coverage_ratio: float = 0.8,
) -> tuple[bool, str]:
    if path is None or not path.is_file():
        return False, f"找不到 tick CSV：{path or '(未指定)'}"

    rows = read_evidence_csv(path, TICK_COLUMNS)
    if not rows:
        return False, f"tick CSV 無資料列：{path}"

    target_dates = expected_dates or set(rows)
    if not target_dates:
        return False, "無預期交易日可對照"

    covered = 0
    tier_counts = {tier: 0 for tier in VALID_TICK_TIERS}
    issues: list[str] = []

    for date in target_dates:
        row = rows.get(date)
        if row is None:
            issues.append(f"{date}: 缺列")
            continue
        tier = row.get("tier", "")
        type0 = row.get("type0_pct", "")
        if tier in VALID_TICK_TIERS and type0:
            covered += 1
            tier_counts[tier] += 1
        else:
            issues.append(f"{date}: 缺 tier/type0_pct")

    coverage = covered / len(target_dates)
    tier_summary = ", ".join(f"{k}={v}" for k, v in tier_counts.items() if v)

    if coverage < min_coverage_ratio:
        detail = (
            f"覆蓋率 {coverage:.0%} < {min_coverage_ratio:.0%} "
            f"({covered}/{len(target_dates)} 日)；{tier_summary}"
        )
        if issues:
            detail += "; " + "; ".join(issues[:5])
        return False, detail

    if not any(tier_counts.values()):
        return False, "無有效 tier 分層資料"

    return True, f"覆蓋 {covered}/{len(target_dates)} 日；{tier_summary}"