"""Batch retrofit post-entry diagnosis + aggregate corpse atlas."""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Allow running as script from apps/trading-app/src
_SRC = Path(__file__).resolve().parent.parent
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from scripts.retrofit_post_entry_diagnosis import retrofit_payload  # noqa: E402

REPO = Path(__file__).resolve().parents[4]

# Relative to repo root — JSON must contain `entries`
RETROFIT_TARGETS: list[tuple[str, str, str | None]] = [
    # (ft_id, json_path, champion_key_hint for summary)
    ("006", "workspaces/vsf-baseline/reports/counterfactual_v2.1_train2025.json", "2.0"),
    ("006-valid", "workspaces/vsf-baseline/reports/counterfactual_v2.1_valid2026q1_k20.json", "2.0"),
    ("006-legacy", "workspaces/vsf-baseline/reports/counterfactual_vwap_stretch_fade.json", "2.0"),
    ("009-valid", "workspaces/orb-baseline/reports/counterfactual_orb_valid.json", "rm30_bk0p15"),
    ("009-0104", "workspaces/orb-baseline/reports/counterfactual_orb_0104.json", "rm30_bk0p15"),
    ("009-holdout", "workspaces/orb-baseline/reports/counterfactual_orb_holdout.json", "rm30_bk0p15"),
    ("008-valid", "workspaces/sb-baseline/reports/counterfactual_v2_close_1h_valid.json", "lb15_bk0"),
    ("008-0104", "workspaces/sb-baseline/reports/counterfactual_v2_close_1h_0104.json", "lb15_bk0"),
    ("007-pilot", "workspaces/mer-baseline/reports/counterfactual_pilot.json", None),
    ("007-flow", "workspaces/mer-baseline/reports/counterfactual_flow_flip_pilot.json", "all"),
]


def _champion_row(
    diagnosis: dict,
    payload: dict,
    hint: str | None,
) -> tuple[str, dict]:
    by_key = diagnosis.get("post_entry_diagnosis_by_key") or {}
    if not by_key:
        return "?", {}
    if hint and hint in by_key:
        return hint, by_key[hint]
    gate = payload.get("phase0_gate") or {}
    best = gate.get("best_passing")
    if best:
        for c in (best.get("stretch_k"), best.get("param"), best.get("session_bucket")):
            if c is not None and str(c) in by_key:
                return str(c), by_key[str(c)]
    key = max(by_key.keys(), key=lambda k: int((by_key[k] or {}).get("n") or 0))
    return key, by_key[key]


def main() -> int:
    cache_dir = REPO / "tick_cache"
    atlas_rows: list[dict] = []
    errors: list[str] = []

    for ft_id, rel, hint in RETROFIT_TARGETS:
        path = REPO / rel
        if not path.is_file():
            errors.append(f"SKIP missing {rel}")
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            result = retrofit_payload(payload, cache_dir=cache_dir)
            out = path.with_name(f"{path.stem}_post_entry.json")
            out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
            key, champ = _champion_row(result, payload, hint)
            barrier = (champ.get("barrier") or {}) if champ else {}
            w30 = ((champ.get("forward") or {}).get("W1800") or {}) if champ else {}
            w5 = ((champ.get("forward") or {}).get("W300") or {}) if champ else {}
            interp = champ.get("interpretation") or {}
            atlas_rows.append(
                {
                    "ft": ft_id,
                    "file": rel,
                    "champion_key": key,
                    "n": champ.get("n"),
                    "barrier_gross_median": barrier.get("gross_median"),
                    "barrier_net_median": barrier.get("net_median"),
                    "w5_median": w5.get("close_delta_median"),
                    "w30_median": w30.get("close_delta_median"),
                    "w30_net_median": w30.get("net_median"),
                    "mfe_median": (champ.get("barrier_path") or {}).get("MFE_median"),
                    "mae_median": (champ.get("barrier_path") or {}).get("MAE_median"),
                    "verdict": interp.get("verdict"),
                }
            )
            print(f"OK {ft_id} -> {out.name}", flush=True)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"FAIL {ft_id} {rel}: {exc}")
            print(f"FAIL {ft_id}: {exc}", flush=True)

    atlas_path = REPO / "workspaces" / "CORPSE_ATLAS_results.json"
    atlas_path.write_text(
        json.dumps({"rows": atlas_rows, "errors": errors}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Atlas: {atlas_path} ({len(atlas_rows)} ok, {len(errors)} skip/fail)", flush=True)
    return 0 if atlas_rows else 1


if __name__ == "__main__":
    raise SystemExit(main())
