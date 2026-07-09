"""One-off: compare fresh Shioaji ticks vs kbars (same logic as cache_audit)."""

from __future__ import annotations

import datetime
import sys

from backfilldata.core import create_and_login_api, resolve_contract
from storage.cache_audit import (
    _in_session_kbar_ts,
    _kbar_ts_for_tick_minute,
    aggregate_ticks_to_minute_bars,
    audit_day,
)
from storage.cache_paths import DEFAULT_TICK_CACHE_DIR
from storage.kbar_loader import fetch_kbars_for_date
from storage.tick_loader import DEFAULT_TICK_RANGE_END, fetch_ticks_for_date


def compare_api_ticks_kbars(code: str, date: datetime.date) -> dict[str, object]:
    api = create_and_login_api(simulation=True)
    try:
        contract = resolve_contract(api, code)
        ticks = fetch_ticks_for_date(api, contract, date)
        kbars = fetch_kbars_for_date(api, contract, date)
    finally:
        api.logout()

    session_kbars = [
        b for b in kbars if datetime.time(8, 46) <= b.ts.time() <= DEFAULT_TICK_RANGE_END
    ]
    minute_bars = aggregate_ticks_to_minute_bars(ticks)
    kbar_by_ts = {b.ts: b for b in session_kbars}

    ohlc: list[str] = []
    vol: list[str] = []
    max_vol = 0
    for minute, bar in minute_bars.items():
        kts = _kbar_ts_for_tick_minute(minute)
        if not _in_session_kbar_ts(kts):
            continue
        kbar = kbar_by_ts.get(kts)
        if kbar is None:
            continue
        for name, tv, kv in (
            ("Open", bar.Open, kbar.Open),
            ("High", bar.High, kbar.High),
            ("Low", bar.Low, kbar.Low),
            ("Close", bar.Close, kbar.Close),
        ):
            if abs(tv - kv) > 0.01:
                ohlc.append(f"{kts.strftime('%H:%M')} {name} tick={tv} kbar={kv}")
        if bar.Volume != kbar.Volume:
            d = abs(bar.Volume - kbar.Volume)
            max_vol = max(max_vol, d)
            vol.append(f"{kts.strftime('%H:%M')} tick={bar.Volume} kbar={kbar.Volume} d={d}")

    if ohlc or len(session_kbars) != 300:
        severity = "FAIL"
    elif vol:
        severity = "WARN"
    else:
        severity = "OK"

    return {
        "severity": severity,
        "tick_count": len(ticks),
        "tick_first": ticks[0].datetime if ticks else None,
        "tick_last": ticks[-1].datetime if ticks else None,
        "kbar_count": len(session_kbars),
        "vol_diff_count": len(vol),
        "ohlc_diff_count": len(ohlc),
        "max_vol_abs_diff": max_vol,
        "ohlc_samples": ohlc[:5],
        "vol_samples": vol[:5],
    }


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    code = argv[0] if len(argv) > 0 else "TMFR1"
    date = datetime.date.fromisoformat(argv[1] if len(argv) > 1 else "2026-01-05")

    local = audit_day(code, date, cache_dir=DEFAULT_TICK_CACHE_DIR, max_examples=5)
    print("=== LOCAL CACHE ===")
    print(
        f"severity={local.severity} vol_diff={local.vol_diff_count} "
        f"ohlc_diff={local.ohlc_diff_count} max_vol_d={local.max_vol_abs_diff}"
    )
    if local.ohlc_mismatches:
        print("ohlc samples:", "; ".join(local.ohlc_mismatches[:3]))
    if local.volume_mismatches:
        print("vol samples:", "; ".join(local.volume_mismatches[:3]))

    print("\n=== FRESH API (simulation login) ===")
    api_result = compare_api_ticks_kbars(code, date)
    print(
        f"severity={api_result['severity']} vol_diff={api_result['vol_diff_count']} "
        f"ohlc_diff={api_result['ohlc_diff_count']} max_vol_d={api_result['max_vol_abs_diff']}"
    )
    print(
        f"ticks={api_result['tick_count']} "
        f"{api_result['tick_first']} .. {api_result['tick_last']}"
    )
    print(f"session_kbars={api_result['kbar_count']}")
    if api_result["ohlc_samples"]:
        print("ohlc samples:", "; ".join(api_result["ohlc_samples"][:3]))
    if api_result["vol_samples"]:
        print("vol samples:", "; ".join(api_result["vol_samples"][:3]))

    same_pattern = (
        local.vol_diff_count == api_result["vol_diff_count"]
        and local.ohlc_diff_count == api_result["ohlc_diff_count"]
    )
    print(f"\nconclusion: API reproduces local mismatch pattern = {same_pattern}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
