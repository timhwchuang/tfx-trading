"""FT-003 Phase 3.6: market scale statistics from tick_cache kbars/ticks."""

from __future__ import annotations

import csv
import datetime as dt
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any

DEFAULT_ATR_PERIOD = 20
BASELINE_SCHEMA_VERSION = 1
HOLDOUT_MONTH = "2026-05"
VALID_MONTH = "2026-04"

# Matches trading_engine.indicators.IndicatorState.compute_atr (SMA of last N TRs).
ATR_METHOD = "sma_tr"


def percentile(sorted_vals: list[float], p: float) -> float:
    if not sorted_vals:
        return 0.0
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    idx = int(p * (len(sorted_vals) - 1))
    return sorted_vals[idx]


def _summarize(values: list[float]) -> dict[str, float]:
    if not values:
        return {"count": 0, "min": 0.0, "p50": 0.0, "p90": 0.0, "p99": 0.0, "max": 0.0, "mean": 0.0}
    s = sorted(values)
    return {
        "count": len(s),
        "min": s[0],
        "p50": statistics.median(s),
        "p90": percentile(s, 0.9),
        "p99": percentile(s, 0.99),
        "max": s[-1],
        "mean": statistics.mean(s),
    }


def load_kbar_rows(path: Path) -> list[tuple[float, float, float, float, float]]:
    """Return (high, low, close, range, volume) per 1m bar."""
    rows: list[tuple[float, float, float, float, float]] = []
    with path.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            h = float(row["High"])
            l = float(row["Low"])
            c = float(row["Close"])
            vol = float(row.get("Volume") or 0)
            rows.append((h, l, c, h - l, vol))
    return rows


def atr_series_from_bars(
    bars: list[tuple[float, float, float, float, float]],
    period: int = DEFAULT_ATR_PERIOD,
) -> list[float]:
    """Rolling SMA(TR, period) per bar — TR from bar 1 (matches IndicatorState.compute_atr)."""
    if len(bars) < 2:
        return []
    trs: list[float] = []
    for i in range(1, len(bars)):
        h, l, c = bars[i][0], bars[i][1], bars[i][2]
        prev_c = bars[i - 1][2]
        tr = max(h - l, abs(h - prev_c), abs(l - prev_c))
        trs.append(tr)
    if len(trs) < period:
        return []
    out: list[float] = []
    for i in range(period - 1, len(trs)):
        out.append(sum(trs[i - period + 1 : i + 1]) / period)
    return out


def month_key_from_path(path: Path) -> str:
    date_part = path.stem.split("_")[-1]
    return date_part[:7]


def month_role(month: str) -> str:
    if month == HOLDOUT_MONTH:
        return "holdout_narrative_only"
    if month == VALID_MONTH:
        return "valid"
    return "train_or_diagnostic"


def compute_kbar_month_stats(
    kbar_paths: list[Path],
    *,
    stop_points: float,
    trail_points: float,
    tp_points: float,
    atr_period: int = DEFAULT_ATR_PERIOD,
) -> dict[str, Any]:
    by_month: dict[str, dict[str, list[float]]] = defaultdict(
        lambda: {
            "ranges": [],
            "atrs": [],
            "closes": [],
            "volumes": [],
            "day_count": 0,
        }
    )
    for path in sorted(kbar_paths):
        month = month_key_from_path(path)
        bars = load_kbar_rows(path)
        if not bars:
            continue
        bucket = by_month[month]
        bucket["day_count"] += 1
        for h, l, c, rng, vol in bars:
            bucket["ranges"].append(rng)
            bucket["closes"].append(c)
            if vol > 0:
                bucket["volumes"].append(vol)
        bucket["atrs"].extend(atr_series_from_bars(bars, period=atr_period))

    months_out: dict[str, Any] = {}
    for month in sorted(by_month):
        b = by_month[month]
        range_s = _summarize(b["ranges"])
        atr_s = _summarize(b["atrs"])
        close_s = _summarize(b["closes"])
        volume_s = _summarize(b["volumes"])
        atr_p50 = atr_s["p50"] or 1.0
        range_p50 = range_s["p50"] or 1.0
        months_out[month] = {
            "trading_days": b["day_count"],
            "role": month_role(month),
            "close": close_s,
            "range_1m": range_s,
            "volume_1m": volume_s,
            "atr20": atr_s,
            "ratios": {
                "stop_ratio": round(stop_points / atr_p50, 4),
                "trail_ratio": round(trail_points / atr_p50, 4),
                "tp_ratio": round(tp_points / atr_p50, 4),
                "range_ratio": round(stop_points / range_p50, 4),
            },
        }
    return months_out


def load_tick_vol_spread_stats(tick_path: Path) -> dict[str, list[float]]:
    vol_1s: list[float] = []
    spreads: list[float] = []
    by_second: dict[dt.datetime, float] = defaultdict(float)

    with tick_path.open(encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            ts = dt.datetime.fromisoformat(row["datetime"])
            sec = ts.replace(microsecond=0)
            vol = float(row["volume"])
            by_second[sec] += vol
            bid = float(row["bid_price"])
            ask = float(row["ask_price"])
            if bid > 0 and ask > 0 and ask >= bid:
                spreads.append(ask - bid)

    for v in by_second.values():
        if v > 0:
            vol_1s.append(v)

    return {"vol_1s": vol_1s, "spreads": spreads}


def threshold_percentile(threshold: float, samples: list[float]) -> float | None:
    """Percent of samples with value <= threshold."""
    if not samples:
        return None
    below = sum(1 for x in samples if x <= threshold)
    return round(100.0 * below / len(samples), 1)


def threshold_pct_gte(threshold: float, samples: list[float]) -> float | None:
    """Percent of samples with value >= threshold (floor gates e.g. momentum_vol_1s)."""
    if not samples:
        return None
    above = sum(1 for x in samples if x >= threshold)
    return round(100.0 * above / len(samples), 1)


def compute_tick_month_stats(tick_paths: list[Path]) -> dict[str, Any]:
    by_month: dict[str, dict[str, list[float]]] = defaultdict(
        lambda: {"vol_1s": [], "spreads": []}
    )
    for path in sorted(tick_paths):
        date_part = path.stem.split("_", 1)[-1]
        month = date_part[:7]
        day_stats = load_tick_vol_spread_stats(path)
        by_month[month]["vol_1s"].extend(day_stats["vol_1s"])
        by_month[month]["spreads"].extend(day_stats["spreads"])

    out: dict[str, Any] = {}
    for month in sorted(by_month):
        b = by_month[month]
        vol_s = _summarize(b["vol_1s"])
        spread_s = _summarize(b["spreads"])
        out[month] = {
            "role": month_role(month),
            "vol_1s": vol_s,
            "spread": spread_s,
            "_vol_1s_samples": b["vol_1s"],
        }
    return out


def build_threshold_coverage(
    tick_months: dict[str, Any],
    config: dict[str, float],
) -> dict[str, Any]:
    mom = float(config.get("momentum_vol_1s", 150))
    exh = float(config.get("exhaustion_vol", 15))
    all_vol: list[float] = []

    for month_data in tick_months.values():
        samples = month_data.get("_vol_1s_samples") or []
        if samples:
            month_data["threshold_coverage"] = {
                "momentum_vol_1s_pct_gte": threshold_pct_gte(mom, samples),
                "exhaustion_vol_pct_lte": threshold_percentile(exh, samples),
            }
            all_vol.extend(samples)
        month_data.pop("_vol_1s_samples", None)

    return {
        "sample_count": len(all_vol),
        "momentum_vol_1s": {
            "threshold": mom,
            "pct_samples_gte": threshold_pct_gte(mom, all_vol),
            "pct_samples_lte": threshold_percentile(mom, all_vol),
            "note": "entry needs vol_1s >= threshold; gte = pass rate on random 1s bars",
        },
        "exhaustion_vol": {
            "threshold": exh,
            "pct_samples_lte": threshold_percentile(exh, all_vol),
            "note": "pullback exhaustion when vol_1s <= threshold",
        },
    }


def build_baseline_payload(
    *,
    code: str,
    from_date: str,
    to_date: str,
    config: dict[str, float],
    kbar_months: dict[str, Any],
    tick_months: dict[str, Any] | None = None,
) -> dict[str, Any]:
    tick_months = dict(tick_months or {})
    threshold_coverage = None
    if tick_months:
        threshold_coverage = build_threshold_coverage(tick_months, config)

    months_role = {m: month_role(m) for m in kbar_months}
    for m in tick_months:
        months_role.setdefault(m, month_role(m))

    return {
        "schema_version": BASELINE_SCHEMA_VERSION,
        "atr_method": ATR_METHOD,
        "atr_period": DEFAULT_ATR_PERIOD,
        "code": code,
        "from_date": from_date,
        "to_date": to_date,
        "months_role": months_role,
        "config": config,
        "kbar_months": kbar_months,
        "tick_months": tick_months,
        "threshold_coverage": threshold_coverage,
        "misread_reminder": (
            "tick close price level is NOT minute range in points; "
            "volume is contracts not price amplitude"
        ),
        "methodology": {
            "atr": f"{ATR_METHOD} period={DEFAULT_ATR_PERIOD} (matches IndicatorState.compute_atr)",
            "holdout_month_usage": f"{HOLDOUT_MONTH} stats are narrative only; do not tune grid",
        },
    }


def preserve_markdown_section(existing: str, header: str) -> str | None:
    """Return section body from header through content, excluding trailing ``---``."""
    marker = f"## {header}"
    if marker not in existing:
        return None
    start = existing.index(marker)
    rest = existing[start:]
    end = rest.find("\n---\n", len(marker))
    if end < 0:
        return None
    return rest[:end].rstrip()


def inject_markdown_section(markdown: str, header: str, section_block: str) -> str:
    """Replace a section; ``section_block`` must not include the trailing ``---``."""
    marker = f"## {header}"
    if marker not in markdown:
        return markdown
    start = markdown.index(marker)
    rest = markdown[start:]
    end = rest.find("\n---\n", len(marker))
    if end < 0:
        return markdown
    return markdown[:start] + section_block.rstrip() + rest[end:]


def render_markdown(payload: dict[str, Any], *, generated: str) -> str:
    cfg = payload["config"]
    lines = [
        "# VOLATILITY_BASELINE — FT-003 Phase 3.6",
        "",
        f"**商品**：{payload['code']}  ",
        f"**資料區間**：{payload['from_date']} ～ {payload['to_date']}  ",
        f"**產生時間**：{generated}  ",
        f"**ATR**：{payload.get('atr_method', ATR_METHOD)} (period={payload.get('atr_period', DEFAULT_ATR_PERIOD)})  ",
        f"**Config 對照**：hard_stop={cfg['hard_stop_points']}, "
        f"trail={cfg['trail_points']}, tp={cfg['fixed_tp_points']}, "
        f"min_atr={cfg.get('min_atr_threshold', '—')}",
        "",
        "> **診斷 only** — 禁止用於本輪 leaderboard 選參。契約："
        "[`SPEC.md`](../docs/features/ai-backtest-tuning/SPEC.md) §4.6。",
        f"> **{HOLDOUT_MONTH}** 列僅供 holdout 風險敘事，禁止回頭 tune grid。",
        "",
        "---",
        "",
        "## A. 月度波動（P0 — kbars）",
        "",
        "| 月 | 角色 | 交易日 | Close med | 1m range p50 | p90 | max | ATR20 p50 | p90 | "
        "1m Vol p50 | stop_ratio | trail_ratio | tp_ratio | range_ratio |",
        "|----|------|--------|-----------|--------------|-----|-----|-----------|-----|"
        "------------|------------|-------------|----------|-------------|",
    ]
    for month, m in payload["kbar_months"].items():
        r = m["range_1m"]
        a = m["atr20"]
        v = m.get("volume_1m") or {}
        rt = m["ratios"]
        role = m.get("role", month_role(month))
        vol_p50 = f"{v.get('p50', 0):.0f}" if v.get("count") else "—"
        lines.append(
            f"| {month} | {role} | {m['trading_days']} | {m['close']['p50']:.0f} | "
            f"{r['p50']:.1f} | {r['p90']:.0f} | {r['max']:.0f} | "
            f"{a['p50']:.1f} | {a['p90']:.0f} | {vol_p50} | "
            f"{rt['stop_ratio']:.2f} | {rt['trail_ratio']:.2f} | "
            f"{rt['tp_ratio']:.2f} | {rt['range_ratio']:.2f} |"
        )
    lines.extend(
        [
            "",
            "**解讀**（交易員填寫）：",
            "",
            "---",
            "",
            "## B. 量能（P1 — tick）",
            "",
        ]
    )
    if payload.get("tick_months"):
        lines.append(
            "| 月 | 角色 | vol_1s p50 | p90 | p99 | spread p50 | spread p90 |"
        )
        lines.append("|----|------|------------|-----|-----|------------|------------|")
        for month, t in payload["tick_months"].items():
            v = t["vol_1s"]
            s = t["spread"]
            role = t.get("role", month_role(month))
            lines.append(
                f"| {month} | {role} | {v['p50']:.0f} | {v['p90']:.0f} | {v['p99']:.0f} | "
                f"{s['p50']:.1f} | {s['p90']:.1f} |"
            )
        tc = payload.get("threshold_coverage") or {}
        if tc:
            mom = tc.get("momentum_vol_1s") or {}
            exh = tc.get("exhaustion_vol") or {}
            lines.extend(
                [
                    "",
                    "### B.1 Config 門檻覆蓋率（vol_1s 樣本）",
                    "",
                    "| 門檻 | 值 | 樣本占比 | 備註 |",
                    "|------|-----|----------|------|",
                    (
                        f"| momentum_vol_1s (floor) | {mom.get('threshold')} | "
                        f"≥門檻 {mom.get('pct_samples_gte', '—')}% · "
                        f"≤門檻 {mom.get('pct_samples_lte', '—')}% | "
                        f"n={tc.get('sample_count', 0)} |"
                    ),
                    (
                        f"| exhaustion_vol (ceiling) | {exh.get('threshold')} | "
                        f"≤門檻 {exh.get('pct_samples_lte', '—')}% | "
                        f"量能枯竭判定 |"
                    ),
                ]
            )
    else:
        lines.append("（未執行 `--ticks`；略過）")
    lines.extend(
        [
            "",
            "---",
            "",
            "## D. 出場診斷（P0 — baseline valid）",
            "",
            "（由 `ft003_exit_diagnosis.py` 填入）",
            "",
            "---",
            "",
            "## E. 常見誤讀提醒",
            "",
            payload["misread_reminder"],
            "",
            "---",
            "",
            "## F. 機器可讀",
            "",
            "`workspaces/reports/volatility_baseline.json`",
            "",
            f"schema_version={payload.get('schema_version', BASELINE_SCHEMA_VERSION)} · "
            f"atr_method={payload.get('atr_method', ATR_METHOD)}",
            "",
        ]
    )
    return "\n".join(lines)
