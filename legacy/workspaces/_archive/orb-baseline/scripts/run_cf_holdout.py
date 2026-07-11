"""Generate FT-009 ORB counterfactual for holdout (v1 May or v2 May+Jun)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "apps" / "trading-app" / "src"
sys.path.insert(0, str(SRC))

from reporting.orb_counterfactual import build_orb_payload  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="FT-009 ORB CF holdout")
    parser.add_argument(
        "--holdout-v2",
        action="store_true",
        help="2026-05-01..2026-06-30 merged holdout (v2 contract)",
    )
    args = parser.parse_args()

    if args.holdout_v2:
        from_date, to_date = "2026-05-01", "2026-06-30"
        out_name = "counterfactual_orb_holdout_v2.json"
    else:
        from_date, to_date = "2026-05-01", "2026-05-31"
        out_name = "counterfactual_orb_holdout.json"

    reports = ROOT / "workspaces" / "orb-baseline" / "reports"
    payload = build_orb_payload(
        from_date=from_date,
        to_date=to_date,
        code="TMFR1",
        cache_dir=ROOT / "tick_cache",
        range_minutes=(15, 30),
        buffer_atr_ks=(0.0, 0.15),
    )
    out = reports / out_name
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    gate = payload["phase0_gate"]
    best = gate.get("best_passing") or {}
    print(f"CF holdout ({from_date}..{to_date}) pass={gate['pass']} best={best}")
    print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
