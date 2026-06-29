"""Entry Lab slug registry and split windows."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

SplitName = Literal["train", "valid"]
SlugName = Literal["gdc", "gudt", "frp", "sfbt"]
TierName = Literal["primary", "secondary", "tertiary"]

SPLITS: dict[SplitName, tuple[str, str]] = {
    "train": ("2025-01-01", "2025-12-31"),
    "valid": ("2026-01-01", "2026-03-31"),
}

BOOTSTRAP_SEED = 42
BOOTSTRAP_N = 10_000
FRICTION_DEFAULT = 5.0
FRICTION_ROBUST = 7.0


@dataclass(frozen=True)
class SlugSpec:
    slug: SlugName
    ft: str
    tier: TierName
    p0_key: str
    baseline_glob: str
    builder_name: str


SLUGS: dict[SlugName, SlugSpec] = {
    "gdc": SlugSpec(
        slug="gdc",
        ft="FT-016",
        tier="secondary",
        p0_key="gk1_rt0p4_ksl1_tp2",
        baseline_glob="workspaces/gdc-baseline/reports/counterfactual_gdc_{split}.json",
        builder_name="gdc",
    ),
    "gudt": SlugSpec(
        slug="gudt",
        ft="FT-018",
        tier="tertiary",
        p0_key="gk1_rt0p4_ksl1_be1_ta2_td0p5_tp4",
        baseline_glob="workspaces/gudt-baseline/reports/counterfactual_gudt_{split}.json",
        builder_name="gudt",
    ),
    "frp": SlugSpec(
        slug="frp",
        ft="FT-015",
        tier="primary",
        p0_key="sl3_age6_vp0p4_ksl1_tp2",
        baseline_glob="workspaces/fvg-baseline/reports/counterfactual_frp_{split}.json",
        builder_name="frp",
    ),
    "sfbt": SlugSpec(
        slug="sfbt",
        ft="FT-019",
        tier="primary",
        p0_key="slb45_sk0p25_rc120_sw3_age6_be1_tar2_taa1p5_td0p5_tp4",
        baseline_glob="workspaces/sfbt-baseline/reports/counterfactual_sfbt_{split}.json",
        builder_name="sfbt",
    ),
}


def repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def entry_lab_root() -> Path:
    return repo_root() / "workspaces" / "entry-lab"


def baseline_path(spec: SlugSpec, split: SplitName) -> Path:
    suffix = "fingerprint" if split == "train" else "valid"
    rel = spec.baseline_glob.format(split=suffix)
    return repo_root() / rel


def expected_n_from_baseline(path: Path, p0_key: str) -> int | None:
    if not path.is_file():
        return None
    import json

    payload = json.loads(path.read_text(encoding="utf-8"))
    counts = payload.get("entry_count_by_param") or {}
    if p0_key in counts:
        return int(counts[p0_key])
    fg = payload.get("fingerprint_gate") or {}
    if fg.get("n") is not None:
        return int(fg["n"])
    return None


def build_payload(
    builder_name: str,
    *,
    code: str,
    cache_dir: Path,
    from_date: str,
    to_date: str,
) -> dict[str, Any]:
    if builder_name == "gdc":
        from reporting.gap_drive_continuation_counterfactual import build_gdc_payload

        return build_gdc_payload(
            code=code,
            cache_dir=cache_dir,
            from_date=from_date,
            to_date=to_date,
            mode="fingerprint",
        )
    if builder_name == "gudt":
        from reporting.gap_up_drive_trail_counterfactual import build_gudt_payload

        return build_gudt_payload(
            code=code,
            cache_dir=cache_dir,
            from_date=from_date,
            to_date=to_date,
            mode="fingerprint",
        )
    if builder_name == "frp":
        from reporting.fvg_retest_pullback_counterfactual import build_frp_payload

        return build_frp_payload(
            code=code,
            cache_dir=cache_dir,
            from_date=from_date,
            to_date=to_date,
            mode="fingerprint",
        )
    if builder_name == "sfbt":
        from reporting.sweep_fvg_breakout_trail_counterfactual import build_sfbt_payload

        return build_sfbt_payload(
            code=code,
            cache_dir=cache_dir,
            from_date=from_date,
            to_date=to_date,
            mode="fingerprint",
        )
    raise ValueError(f"unknown builder: {builder_name}")
