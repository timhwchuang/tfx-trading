"""FT-024: Multi-day 15m timeline with 4h/1h/5m context + trader signal scan."""

from __future__ import annotations

import argparse
import datetime
import json
import sys
from pathlib import Path

from config import PRODUCT_CODE
from reporting.osf_timeline import build_15m_timeline
from reporting.osf_trader_scan import scan_timeline_trader_signals
from storage.cache_paths import DEFAULT_TICK_CACHE_DIR
from storage.session_bar_cache import DAY_ANCHOR


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="15m timeline + 4h/1h/5m + trader scan")
    parser.add_argument("--code", default=PRODUCT_CODE)
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_TICK_CACHE_DIR)
    parser.add_argument("--from-date", default="2026-06-01")
    parser.add_argument("--to-date", default="2026-06-03")
    parser.add_argument(
        "--end-time",
        default="24:00",
        help="Last calendar day end time (24:00 = midnight next day)",
    )
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--compact", action="store_true", help="Skip per-row h4/m5 detail in stdout")
    parser.add_argument(
        "--trader-scan",
        action="store_true",
        help="Run discretionary playbook scan and print candidate entries",
    )
    args = parser.parse_args(argv)

    start_day = datetime.date.fromisoformat(args.from_date)
    end_day = datetime.date.fromisoformat(args.to_date)
    start = datetime.datetime.combine(start_day, DAY_ANCHOR)
    if args.end_time == "24:00":
        end = datetime.datetime.combine(end_day + datetime.timedelta(days=1), datetime.time(0, 0))
    else:
        h, m = map(int, args.end_time.split(":"))
        end = datetime.datetime.combine(end_day, datetime.time(h, m))

    payload = build_15m_timeline(
        start=start, end=end, code=args.code, cache_dir=args.cache_dir
    )
    if args.trader_scan:
        payload["trader_scan"] = scan_timeline_trader_signals(
            args.code, payload, from_date=start_day, to_date=end_day
        )

    out = args.out or (
        _repo_root()
        / "workspaces/osf-baseline/reports"
        / f"timeline_15m_{args.from_date}_{args.to_date}.json"
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print(
        f"range {payload['start']} → {payload['end']}  n_15m={payload['n_15m']}  "
        f"ma_from={payload.get('ma_history_from')}"
    )
    print(
        f"{'ts':<18} {'15m_C':>7}  {'h1_20':>7} {'h1_60':>7}  "
        f"{'h4_20':>7} {'h4_60':>7}  {'vs':>4}"
    )
    for row in payload["rows"]:
        m15 = row["m15"]
        h1 = row["h1"]
        h4 = row["h4"]
        pvm = row.get("price_vs_ma") or {}
        ts = m15["ts"][5:16].replace("T", " ")
        if ts.endswith("09:00") or ts.endswith("09:30") or ts.endswith("12:15") or ts.endswith("13:45"):
            def _fmt(v: float | None) -> str:
                return f"{v:7.0f}" if v is not None else "    n/a"

            stack = "↑↑" if pvm.get("h4_ma60") == "above" and pvm.get("h1_ma20") == "above" else ""
            print(
                f"{ts:<18} {m15['C']:7.0f}  {_fmt(h1.get('ma20'))} {_fmt(h1.get('ma60'))}  "
                f"{_fmt(h4.get('ma20'))} {_fmt(h4.get('ma60'))}  {stack}"
            )
            if not args.compact and row.get("m5_last"):
                m5s = " ".join(f"{b['ts'][11:16]}:{b['C']:.0f}" for b in row["m5_last"])
                print(f"  m5×{len(row['m5_last'])}: {m5s}")
    if payload.get("trader_scan"):
        ts = payload["trader_scan"]
        print(f"\n=== trader scan: {ts['n_signals']} signals ===")
        for s in ts["signals"]:
            print(f"  {s['ts'][5:16]} [{s['confidence']}] {s['playbook']}")
            print(f"    entry~{s['entry_ref']} stop~{s['stop_ref']}  {s['rationale']}")
    print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())