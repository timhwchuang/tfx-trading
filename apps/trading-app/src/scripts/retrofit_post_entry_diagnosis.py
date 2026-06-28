"""Retrofit post-entry diagnosis onto existing CF JSON with stored entries.

One-time corpse atlas — does NOT re-run gate or tune params.
See workspaces/CORPSE_ATLAS.md for corpus list.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from reporting.forward_pnl import load_tick_series
from reporting.post_entry_diagnosis import (
    enrich_rows_with_forward_windows,
    format_gate_report_post_entry_section,
    summarize_post_entry_diagnosis,
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _load_entries(payload: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """Normalize entries keyed by param (stretch_k, orb param, or flat list)."""
    raw = payload.get("entries")
    if raw is None:
        return {}
    if isinstance(raw, list):
        return {"all": raw}
    if isinstance(raw, dict):
        out: dict[str, list[dict[str, Any]]] = {}
        for key, rows in raw.items():
            if isinstance(rows, list):
                out[str(key)] = rows
        return out
    return {}


def _rows_ready(rows: list[dict[str, Any]], *, gross_key: str) -> bool:
    required = ("ts", "entry_price", "direction", gross_key)
    return bool(rows) and all(k in rows[0] for k in required)


def _resolve_gross_keys(row: dict[str, Any]) -> tuple[str, str]:
    if "gross_atr_sim" in row:
        return "gross_atr_sim", "net_atr_sim"
    if "gross_scalp" in row:
        return "gross_scalp", "net_scalp"
    raise KeyError("no gross_atr_sim or gross_scalp in entry row")


def retrofit_payload(
    payload: dict[str, Any],
    *,
    cache_dir: Path,
) -> dict[str, Any]:
    code = str(payload.get("code") or "TMFR1")
    from_date = str(payload["from_date"])
    to_date = str(payload["to_date"])
    friction = float(payload.get("friction_points_per_round_trip") or 5.0)

    entry_map = _load_entries(payload)
    if not entry_map:
        raise ValueError("payload has no entries — re-run CF builder instead")

    from storage.tick_loader import resolve_cli_tick_cache_dates

    dates = resolve_cli_tick_cache_dates(
        explicit=None,
        from_cache=True,
        code=code,
        cache_dir=cache_dir,
        from_date=from_date,
        to_date=to_date,
    )
    if not dates:
        raise ValueError(f"no tick cache for {from_date}..{to_date}")

    series = load_tick_series(code, sorted(dates), cache_dir=cache_dir)
    diagnosis_by_key: dict[str, Any] = {}

    for key, rows in entry_map.items():
        if not rows:
            continue
        try:
            gross_key, net_key = _resolve_gross_keys(rows[0])
        except KeyError:
            continue
        if not _rows_ready(rows, gross_key=gross_key):
            continue
        work = [dict(r) for r in rows]
        enrich_rows_with_forward_windows(work, series)
        diagnosis_by_key[key] = summarize_post_entry_diagnosis(
            work,
            friction_points=friction,
            barrier_gross_key=gross_key,
            barrier_net_key=net_key,
        )

    if not diagnosis_by_key:
        raise ValueError("entries missing ts/entry_price/direction/gross_atr_sim")

    return {
        "source_thesis": payload.get("thesis"),
        "from_date": from_date,
        "to_date": to_date,
        "code": code,
        "friction_points_per_round_trip": friction,
        "post_entry_diagnosis_by_key": diagnosis_by_key,
    }


def _pick_champion_key(diagnosis: dict[str, Any], payload: dict[str, Any]) -> str | None:
    by_key = diagnosis.get("post_entry_diagnosis_by_key") or {}
    if not by_key:
        return None
    gate = payload.get("phase0_gate") or {}
    best = gate.get("best_passing")
    if best:
        for candidate in (best.get("stretch_k"), best.get("param")):
            if candidate is not None and str(candidate) in by_key:
                return str(candidate)
    # fallback: key with most rows
    return max(by_key.keys(), key=lambda k: int((by_key[k] or {}).get("n") or 0))


def main(argv: list[str] | None = None) -> int:
    root = _repo_root()
    parser = argparse.ArgumentParser(description="Retrofit post-entry diagnosis on CF JSON")
    parser.add_argument("json_path", type=Path, help="CF JSON with entries[]")
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=root / "tick_cache",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Default: <json_stem>_post_entry.json beside input",
    )
    parser.add_argument(
        "--markdown",
        type=Path,
        default=None,
        help="Optional gate_report-style appendix .md",
    )
    args = parser.parse_args(argv)

    payload = json.loads(args.json_path.read_text(encoding="utf-8"))
    result = retrofit_payload(payload, cache_dir=args.cache_dir)

    out_path = args.output or args.json_path.with_name(
        f"{args.json_path.stem}_post_entry.json"
    )
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {out_path}", flush=True)

    if args.markdown:
        champ = _pick_champion_key(result, payload)
        if champ:
            lines = format_gate_report_post_entry_section(
                result["post_entry_diagnosis_by_key"][champ],
                param_label=f"retrofit · {champ}",
            )
            args.markdown.write_text("\n".join(lines), encoding="utf-8")
            print(f"Wrote {args.markdown}", flush=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
